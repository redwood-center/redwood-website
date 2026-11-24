// Redwood Website Bot. Anyone in the Redwood Slack can DM it (or @mention it in a channel) with a change to the
// website. Each Slack thread is one request: the agent edits a branch, the bot builds the site, publishes a preview,
// posts screenshots and opens a pull request. Requests from approved people are merged (published) right away;
// anyone else's wait until an approved person clicks Publish. Replies in the thread revise the change.
import fs from 'node:fs';
import path from 'node:path';

import { App, LogLevel } from '@slack/bolt';
import type { WebClient } from '@slack/web-api';

import { type AgentResult, runAgent } from './agent.ts';
import { STATE, config, isApproved, log, secret } from './config.ts';
import {
  changedFiles, closePR, commitAndPush, deleteRemoteBranch, diffText, mergePR, newWorktree, openPR, removeWorktree,
  revert, updatePR, WORK_DIR,
} from './git.ts';
import {
  build, focusTexts, linkDeps, previewUrl, publishPreview, removePreview, routesFor, screenshots, startPreviewServer,
} from './site.ts';

type Job = {
  id: string;
  channel: string;
  threadTs: string;
  requester: string; // Slack user ID
  title: string;
  branch: string;
  status: 'working' | 'open' | 'merged' | 'discarded' | 'failed';
  sessionId?: string;
  pr?: { number: number; url: string };
  summary?: string;
  mergeSha?: string; // the commit on main once published, for Undo
};

// --- Job records (state/jobs.json), keyed by "channel:threadTs" ---

const JOBS_FILE = path.join(STATE, 'jobs.json');
const jobs: Record<string, Job> = fs.existsSync(JOBS_FILE) ? JSON.parse(fs.readFileSync(JOBS_FILE, 'utf8')) : {};
for (const j of Object.values(jobs)) if (j.status === 'working') j.status = 'failed'; // interrupted by a restart
const saveJobs = () => {
  fs.mkdirSync(STATE, { recursive: true });
  fs.writeFileSync(JOBS_FILE, JSON.stringify(jobs, null, 1));
};
const byId = (id: string) => Object.values(jobs).find((j) => j.id === id);

// One request at a time: worktrees are independent, but builds and the previews repo are shared.
let queue: Promise<void> = Promise.resolve();
let pending = 0;
function enqueue(task: () => Promise<void>) {
  pending++;
  queue = queue.then(task).catch((e) => log('task failed', e)).finally(() => pending--);
}

const app = new App({
  token: secret('SLACK_BOT_TOKEN'),
  appToken: secret('SLACK_APP_TOKEN'),
  socketMode: true,
  logLevel: LogLevel.WARN,
});

const names = new Map<string, string>();
async function nameOf(client: WebClient, user: string) {
  if (!names.has(user)) {
    const r = await client.users.info({ user }).catch(() => null);
    names.set(user, r?.user?.real_name || r?.user?.name || user);
  }
  return names.get(user)!;
}

const approvedList = () => Object.values(config.approved).join(', ');
const shortTitle = (text: string) => {
  const line = text.split('\n')[0].trim();
  return line.length > 70 ? `${line.slice(0, 67)}…` : line;
};
const slugify = (text: string) => text.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 30) || 'change';

// --- Incoming messages ---

type Incoming = { user: string; text: string; channel: string; ts: string; thread_ts?: string; files?: SlackFile[] };
type SlackFile = { name?: string; mimetype?: string; url_private_download?: string };

app.event('app_mention', async ({ event, client, context }) => {
  const text = event.text.replaceAll(`<@${context.botUserId}>`, '').trim();
  handle(client, { ...(event as unknown as Incoming), text });
});

app.message(async ({ message, client }) => {
  const m = message as unknown as Incoming & { channel_type?: string; subtype?: string; bot_id?: string };
  // Direct messages only; in channels the bot answers @mentions (above).
  if (m.channel_type !== 'im' || m.bot_id || (m.subtype && m.subtype !== 'file_share')) return;
  handle(client, m);
});

function handle(client: WebClient, m: Incoming) {
  if (!m.text?.trim() && !m.files?.length) return;
  const threadTs = m.thread_ts ?? m.ts;
  const key = `${m.channel}:${threadTs}`;
  if (pending > 0) {
    client.chat.postMessage({ channel: m.channel, thread_ts: threadTs, text: "Got it. I'm finishing another request first; this one is next." });
  }
  enqueue(() => work(client, key, m, threadTs));
}

/** One request: edit (or, for Undo, revert the published commit), build, preview, pull request, then publish or
 * offer to. */
async function work(client: WebClient, key: string, m: Incoming, threadTs: string, undo?: Job) {
  const say = (text: string, extra: Record<string, unknown> = {}) =>
    client.chat.postMessage({ channel: m.channel, thread_ts: threadTs, text, ...extra });
  const react = (name: string, remove = false) => {
    const args = { channel: m.channel, timestamp: m.ts, name };
    return (remove ? client.reactions.remove(args) : client.reactions.add(args)).catch(() => {});
  };

  await react('eyes');
  const status = await say('Working on it…');
  const setStatus = (text: string) => client.chat.update({ channel: m.channel, ts: status.ts!, text }).catch(() => {});
  const requester = await nameOf(client, m.user);

  let job = jobs[key];
  const followUp = job?.status === 'open';
  const previous = job && !followUp ? job : undefined;
  try {
    if (!followUp) {
      const id = `${new Date().toISOString().slice(0, 10).replaceAll('-', '')}-${slugify(m.text)}-${Math.random().toString(36).slice(2, 6)}`;
      const title = undo ? `Undo: ${undo.title}` : shortTitle(m.text || 'Website change');
      job = { id, channel: m.channel, threadTs, requester: m.user, title, branch: `bot/${id}`, status: 'working' };
      jobs[key] = job;
      await newWorktree(job.id, job.branch);
    }
    job.status = 'working';
    saveJobs();
    const dir = path.join(WORK_DIR, job.id);
    await linkDeps(dir);
    const attached = await saveAttachments(dir, m.files ?? []);

    // 1. Edit (or revert).
    let prompt = `${requester} asks on Slack:\n\n${m.text}`;
    if (attached.length) prompt += `\n\nThey attached these files, now in the working copy:\n${attached.map((a) => `- ${a}`).join('\n')}`;
    if (previous?.summary) prompt += `\n\n(Earlier in this thread, already published or discarded: "${previous.title}": ${previous.summary})`;
    if (followUp) prompt = `${requester} replies:\n\n${m.text}${attached.length ? `\n\nNew attachments:\n${attached.map((a) => `- ${a}`).join('\n')}` : ''}`;
    let agent: AgentResult;
    if (undo?.mergeSha) {
      await revert(dir, undo.mergeSha);
      agent = { text: `Undid "${undo.title}".`, sessionId: '', costUsd: 0 };
    } else {
      setStatus('Working on it… (editing the site)');
      agent = await runAgent(dir, prompt, job.sessionId);
      job.sessionId = agent.sessionId;
      log(job.id, `agent $${agent.costUsd.toFixed(2)}`, agent.error ?? '');
      if (agent.error) throw new Error(`the editing step stopped early (${agent.error})`);
      await dropUnusedAttachments(dir, attached);
    }

    const files = await changedFiles(dir);
    if (!files.length) {
      // A question back, or nothing to change. Keep the thread open for the answer.
      job.status = 'open';
      saveJobs();
      await setStatus(agent.text || "I didn't find anything to change.");
      await react('eyes', true);
      return;
    }

    // 2. Build; one chance for the agent to fix a failed build.
    setStatus('Working on it… (building the site)');
    let built = await build(dir, job.id);
    if (!built.ok) {
      agent = await runAgent(dir, `The site build failed after your change. Fix it. Build output:\n\n${built.log}`, job.sessionId);
      job.sessionId = agent.sessionId;
      built = await build(dir, job.id);
      if (!built.ok) throw new Error(`the site doesn't build with this change:\n\`\`\`${built.log.slice(-1500)}\`\`\``);
    }
    job.summary = agent.text;

    // 3. Preview, branch, pull request.
    setStatus('Working on it… (publishing a preview)');
    await publishPreview(dir, job.id);
    const preview = previewUrl(job.id);
    await commitAndPush(dir, job.branch, `${job.title}\n\nRequested by ${requester} on Slack.`);
    const body = `Requested by **${requester}** on Slack:\n\n> ${m.text.replaceAll('\n', '\n> ')}\n\n${agent.text}\n\nPreview: ${preview}`;
    if (job.pr) await updatePR(job.pr.number, body);
    else {
      const pr = await openPR(job.branch, job.title, body);
      job.pr = { number: pr.number, url: pr.html_url };
    }
    const routes = routesFor(files);
    const shots = await screenshots(job.id, routes.length ? routes : [''], focusTexts(await diffText(dir))).catch((e) => {
      log(job!.id, 'screenshots failed', e);
      return [] as string[];
    });

    // 4. Publish now (approved requester) or offer buttons.
    const fileList = files.map((f) => `\`${f.replace(/^site\//, '')}\``).join(', ');
    let text: string;
    let blocks: unknown[];
    if (isApproved(m.user)) {
      await publish(job);
      text = `${agent.text}\n\n:white_check_mark: Published; <${config.siteUrl}|the live site> updates in about a minute.`;
      blocks = resultBlocks(text, fileList, job, null, [button('Undo', 'undo', job.id)]);
    } else {
      job.status = 'open';
      text = `${agent.text}\n\nThis needs an approved person (${approvedList()}) to publish it. Reply here to change it.`;
      blocks = resultBlocks(text, fileList, job, preview, [button('Publish', 'publish', job.id, 'primary'), button('Discard', 'discard', job.id)]);
    }
    saveJobs();
    await client.chat.update({ channel: m.channel, ts: status.ts!, text, blocks: blocks as never });
    if (shots.length) {
      await client.files.uploadV2({
        channel_id: m.channel, thread_ts: threadTs,
        file_uploads: shots.map((f) => ({ file: f, filename: path.basename(f) })),
        initial_comment: isApproved(m.user) ? 'How it looks:' : 'How it would look:',
      }).catch((e) => log(job!.id, 'upload failed', e));
    }
    await react('eyes', true);
    await react('white_check_mark');
  } catch (e) {
    log(job?.id, 'failed', e);
    if (job) { job.status = job.pr ? 'open' : 'failed'; saveJobs(); }
    await setStatus(`Sorry, something went wrong: ${(e as Error).message}`);
    await react('eyes', true);
    await react('x');
  }
}

// --- Attachments ---

/** Save Slack attachments into the worktree: images with the people photos, anything else in media/uploads. */
async function saveAttachments(dir: string, files: SlackFile[]) {
  const saved: string[] = [];
  for (const f of files) {
    if (!f.url_private_download) continue;
    const folder = f.mimetype?.startsWith('image/') ? 'site/public/media/people' : 'site/public/media/uploads';
    const base = (f.name ?? 'file').toLowerCase().replace(/[^a-z0-9._-]+/g, '-');
    let rel = path.join(folder, base);
    for (let k = 2; fs.existsSync(path.join(dir, rel)); k++) rel = path.join(folder, base.replace(/(\.\w+)?$/, `-${k}$1`));
    const res = await fetch(f.url_private_download, { headers: { Authorization: `Bearer ${secret('SLACK_BOT_TOKEN')}` } });
    if (!res.ok) continue;
    fs.mkdirSync(path.join(dir, folder), { recursive: true });
    fs.writeFileSync(path.join(dir, rel), Buffer.from(await res.arrayBuffer()));
    saved.push(rel);
  }
  return saved;
}

/** Remove attachments the change doesn't reference, so stray uploads don't end up on the site. */
async function dropUnusedAttachments(dir: string, attached: string[]) {
  if (!attached.length) return;
  const diff = await diffText(dir);
  for (const rel of attached) {
    // Pages refer to public files without the site/public/ prefix, e.g. "media/people/jane.jpg".
    if (!diff.includes(rel.replace(/^site\/public\//, ''))) fs.rmSync(path.join(dir, rel), { force: true });
  }
}

// --- Publishing, discarding, undoing ---

async function publish(job: Job) {
  job.mergeSha = (await mergePR(job.pr!.number, job.title)).sha;
  job.status = 'merged';
  saveJobs();
  await deleteRemoteBranch(job.branch);
  await removeWorktree(job.id, job.branch);
  await removePreview(job.id).catch((e) => log(job.id, 'preview cleanup failed', e));
}

async function discard(job: Job) {
  if (job.pr) await closePR(job.pr.number);
  job.status = 'discarded';
  saveJobs();
  await deleteRemoteBranch(job.branch);
  await removeWorktree(job.id, job.branch);
  await removePreview(job.id).catch((e) => log(job.id, 'preview cleanup failed', e));
}

const section = (text: string) => ({ type: 'section', text: { type: 'mrkdwn', text } });
const button = (text: string, action: string, value: string, style?: 'primary' | 'danger') =>
  ({ type: 'button', text: { type: 'plain_text', text }, action_id: action, value, ...(style ? { style } : {}) });

function resultBlocks(text: string, fileList: string, job: Job, preview: string | null, buttons: unknown[]) {
  const links = [preview && `<${preview}|Preview>`, job.pr && `<${job.pr.url}|Pull request #${job.pr.number}>`].filter(Boolean).join('  ·  ');
  return [
    { type: 'section', text: { type: 'mrkdwn', text } },
    { type: 'context', elements: [{ type: 'mrkdwn', text: `Changed ${fileList}${links ? `  ·  ${links}` : ''}` }] },
    { type: 'actions', elements: buttons },
  ];
}

app.action('publish', async ({ ack, body, action, client }) => {
  await ack();
  const user = body.user.id;
  const job = byId((action as { value: string }).value);
  const channel = body.channel!.id;
  const ts = (body as { message?: { ts: string } }).message!.ts;
  if (!job || job.status !== 'open') return;
  if (!isApproved(user)) {
    await client.chat.postEphemeral({ channel, user, thread_ts: job.threadTs, text: `Only approved people can publish (${approvedList()}). Ask one of them to click Publish.` });
    return;
  }
  enqueue(async () => {
    try {
      await publish(job);
      const text = `${job.summary}\n\n:white_check_mark: Published by <@${user}>; <${config.siteUrl}|the live site> updates in about a minute.`;
      await client.chat.update({ channel, ts, text, blocks: [section(text), { type: 'actions', elements: [button('Undo', 'undo', job.id)] }] as never });
    } catch (e) {
      log(job.id, 'publish failed', e);
      await client.chat.postMessage({ channel, thread_ts: job.threadTs, text: `Couldn't publish: ${(e as Error).message}` });
    }
  });
});

app.action('discard', async ({ ack, body, action, client }) => {
  await ack();
  const user = body.user.id;
  const job = byId((action as { value: string }).value);
  const channel = body.channel!.id;
  if (!job || job.status !== 'open') return;
  if (user !== job.requester && !isApproved(user)) {
    await client.chat.postEphemeral({ channel, user, thread_ts: job.threadTs, text: 'Only the person who asked, or an approved person, can discard this.' });
    return;
  }
  enqueue(async () => {
    await discard(job);
    const text = `Discarded by <@${user}>.`;
    await client.chat.update({ channel, ts: (body as { message?: { ts: string } }).message!.ts, text, blocks: [section(text)] as never });
  });
});

app.action('undo', async ({ ack, body, action, client }) => {
  await ack();
  const user = body.user.id;
  const job = byId((action as { value: string }).value);
  const channel = body.channel!.id;
  if (!job || job.status !== 'merged') return;
  if (!isApproved(user)) {
    await client.chat.postEphemeral({ channel, user, thread_ts: job.threadTs, text: `Only approved people can undo a published change (${approvedList()}).` });
    return;
  }
  // Undo = a new request in the same thread (a git revert of the published commit), so it gets the same build,
  // preview and pull request treatment, and is published at once since the clicker is approved.
  const key = `${job.channel}:${job.threadTs}`;
  enqueue(() => work(client, key, { user, text: `Undo "${job.title}"`, channel, ts: job.threadTs, thread_ts: job.threadTs }, job.threadTs, job));
});

startPreviewServer();
await app.start();
log(`redwood-website-bot running; previews at ${previewUrl('<id>')}`);
