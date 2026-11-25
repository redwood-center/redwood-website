// Redwood Website Bot. Anyone in the Redwood Slack can DM it (or @mention it in a channel) about a change to the
// website. Each Slack thread is one request, in four steps:
//   1. Talk: the agent (read-only) works out the change with the requester, then describes it and asks to confirm.
//   2. Build: on confirmation (a reply, or the Build preview button) it edits a branch; the bot builds the site,
//      uploads a preview and posts its link. Replies after that go back to step 1 for a revision.
//   3. Submit a PR (anyone): opens a pull request for review. Merge to main (people with merge access, the
//      `approved` list; shown only on their own requests): opens the pull request if needed and merges it, and
//      the live site redeploys.
//   4. Undo (merge access) reverts a merged change, through the same preview.
// Nothing goes live from a message: only the Merge to main button (or merging the pull request on GitHub) does.
import fs from 'node:fs';
import path from 'node:path';

import { App, LogLevel } from '@slack/bolt';
import type { WebClient } from '@slack/web-api';

import { type AgentResult, runAgent } from './agent.ts';
import { STATE, config, isApproved, log, redact, secret } from './config.ts';
import {
  changedFiles, closePR, commitAll, deleteRemoteBranch, mergePR, newWorktree, openPR, pushBranch, unusedNewMedia,
  removeWorktree, revert, updatePR, WORK_DIR,
} from './git.ts';
import { build, linkDeps, publishPreview, removePreview } from './site.ts';

type Status =
  | 'discussing' // talking it over; nothing proposed yet (or a question was answered)
  | 'proposed' // the agent described a change and asked to confirm
  | 'working' // editing and building
  | 'preview' // a preview is up, waiting for Merge to main / Submit a PR / a reply
  | 'submitted' // pull request open, waiting to be merged
  | 'merged' | 'discarded' | 'failed';
const ACTIVE = new Set<Status>(['discussing', 'proposed', 'preview', 'submitted']); // a reply continues the request

type Job = {
  id: string;
  channel: string;
  threadTs: string;
  requester: string; // Slack user ID
  title: string;
  branch: string;
  status: Status;
  sessionId?: string;
  attached?: string[]; // attachments saved into the worktree, not yet used or dropped
  proposal?: string; // the change as the agent described it, for the pull request
  previewUrl?: string;
  pr?: { number: number; url: string };
  summary?: string; // what the agent says it changed
  mergeSha?: string; // the commit on main once published, for Undo
};

// --- Job records (state/jobs.json), keyed by "channel:threadTs" ---

const JOBS_FILE = path.join(STATE, 'jobs.json');
const jobs: Record<string, Job> = fs.existsSync(JOBS_FILE) ? JSON.parse(fs.readFileSync(JOBS_FILE, 'utf8')) : {};
for (const j of Object.values(jobs)) {
  const status = j.status as string;
  if (status === 'open') j.status = j.pr ? 'submitted' : 'discussing'; // records from before the talk step
  if (status === 'working') j.status = fs.existsSync(path.join(WORK_DIR, j.id)) ? 'discussing' : 'failed'; // interrupted by a restart
}
const saveJobs = () => {
  fs.mkdirSync(STATE, { recursive: true });
  fs.writeFileSync(JOBS_FILE, JSON.stringify(jobs, null, 1));
};
const byId = (id: string) => Object.values(jobs).find((j) => j.id === id);

// One request at a time: worktrees are independent, but builds and the local preview server are shared.
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
// Error text for Slack: credentials scrubbed (again; run() already does) and kept short. Details go to the log.
const failure = (e: unknown) => {
  const text = redact(e instanceof Error ? e.message : String(e));
  return text.length > 600 ? `${text.slice(0, 600)}…` : text;
};
const shortTitle = (text: string) => {
  const line = text.split('\n')[0].trim();
  return line.length > 70 ? `${line.slice(0, 67)}…` : line;
};
const slugify = (text: string) => text.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 30) || 'change';
const newId = (text: string) =>
  `${new Date().toISOString().slice(0, 10).replaceAll('-', '')}-${slugify(text)}-${Math.random().toString(36).slice(2, 6)}`;

// --- Slack message helpers ---

const section = (text: string) => ({ type: 'section', text: { type: 'mrkdwn', text } });
const context = (text: string) => ({ type: 'context', elements: [{ type: 'mrkdwn', text }] });
const actions = (...buttons: unknown[]) => ({ type: 'actions', elements: buttons });
const button = (text: string, action: string, value: string, style?: 'primary' | 'danger') =>
  ({ type: 'button', text: { type: 'plain_text', text }, action_id: action, value, ...(style ? { style } : {}) });

/** A message in a thread that can be rewritten in place (the "Working on it…" status becomes the reply). */
type Post = { channel: string; ts: string };
const update = (client: WebClient, post: Post, text: string, blocks?: unknown[]) =>
  client.chat.update({ channel: post.channel, ts: post.ts, text, ...(blocks ? { blocks: blocks as never } : {}) })
    .then(() => {}, (e) => log('update failed', e));
async function postIn(client: WebClient, job: { channel: string; threadTs: string }, text: string): Promise<Post> {
  const r = await client.chat.postMessage({ channel: job.channel, thread_ts: job.threadTs, text });
  return { channel: job.channel, ts: r.ts! };
}

// --- Incoming messages ---

type Incoming = { user: string; text: string; channel: string; ts: string; thread_ts?: string; files?: SlackFile[] };
type SlackFile = { name?: string; mimetype?: string; url_private_download?: string };

app.event('app_mention', async ({ event, client, context: ctx }) => {
  const text = event.text.replaceAll(`<@${ctx.botUserId}>`, '').trim();
  handle(client, { ...(event as unknown as Incoming), text });
});

app.message(async ({ message, client, context: ctx }) => {
  const m = message as unknown as Incoming & { channel_type?: string; subtype?: string; bot_id?: string };
  if (m.bot_id || (m.subtype && m.subtype !== 'file_share')) return;
  if (m.channel_type === 'im') return handle(client, m);
  // In channels: replies in a thread with a request in progress, without needing an @mention. Messages that do
  // mention the bot arrive as app_mention events (above), so skip them here to avoid answering twice.
  const job = m.thread_ts ? jobs[`${m.channel}:${m.thread_ts}`] : undefined;
  if (job && ACTIVE.has(job.status) && !m.text?.includes(`<@${ctx.botUserId}>`)) handle(client, m);
});

// "[no bot reply]" anywhere in a message lets people talk in a bot thread without the bot answering (or seeing it).
const NO_REPLY = /\[\s*no[\s-]*bot[\s-]*reply\s*\]/i;

function handle(client: WebClient, m: Incoming) {
  if (!m.text?.trim() && !m.files?.length) return;
  if (NO_REPLY.test(m.text ?? '')) return;
  const threadTs = m.thread_ts ?? m.ts;
  if (pending > 0) {
    client.chat.postMessage({ channel: m.channel, thread_ts: threadTs, text: "Got it. I'm finishing another request first; this one is next." });
  }
  enqueue(() => talk(client, `${m.channel}:${threadTs}`, m, threadTs));
}

const react = (client: WebClient, m: { channel: string; ts: string }, name: string, remove = false) => {
  const args = { channel: m.channel, timestamp: m.ts, name };
  return (remove ? client.reactions.remove(args) : client.reactions.add(args)).catch(() => {});
};

/** Step 1: pass a message to the agent (read-only) and post its reply: an answer, a question, or a proposal to
 * confirm. If the message confirms the latest proposal, go on to build it. */
async function talk(client: WebClient, key: string, m: Incoming, threadTs: string) {
  await react(client, m, 'eyes');
  let job = jobs[key];
  const previous = job && !ACTIVE.has(job.status) ? job : undefined;
  const status = await postIn(client, { channel: m.channel, threadTs }, 'Working on it…');
  const name = await nameOf(client, m.user);
  try {
    if (!job || previous) {
      const id = newId(m.text);
      job = { id, channel: m.channel, threadTs, requester: m.user, title: shortTitle(m.text || 'Website change'), branch: `bot/${id}`, status: 'discussing' };
      jobs[key] = job;
      saveJobs();
      await newWorktree(job.id, job.branch);
    }
    const dir = path.join(WORK_DIR, job.id);
    const attached = await saveAttachments(dir, m.files ?? []);
    job.attached = [...(job.attached ?? []), ...attached];
    saveJobs();

    let prompt = `[Talking] ${name} says:\n\n${m.text}`;
    if (attached.length) prompt += `\n\nThey attached these files, now in the working copy:\n${attached.map((a) => `- ${a}`).join('\n')}`;
    if (previous?.summary) prompt += `\n\n(Earlier in this thread, already ${previous.status}: "${previous.title}": ${previous.summary})`;
    const agent = await runAgent(dir, prompt, 'talk', job.sessionId);
    job.sessionId = agent.sessionId;
    saveJobs();
    log(job.id, `talk $${agent.costUsd.toFixed(2)}`, agent.error ?? '');
    if (agent.error) throw new Error(`I stopped early (${agent.error})`);

    if (/^\s*\[confirmed\]\s*$/.test(agent.text) || (agent.text.endsWith('[confirmed]') && job.status === 'proposed')) {
      await buildPreview(client, job, status, name);
    } else {
      const proposal = agent.text.match(/\n?\[proposal:\s*(.+?)\]\s*$/);
      const text = (proposal ? agent.text.slice(0, proposal.index).trim() : agent.text) || "I'm not sure what to change. Could you say more?";
      if (proposal) {
        job.status = 'proposed';
        job.title = shortTitle(proposal[1]);
        job.proposal = text;
        saveJobs();
        await update(client, status, text, [
          section(text),
          context('Reply to change it, or say go ahead.'),
          actions(button('Build preview', 'build', job.id, 'primary'), button('Discard', 'discard', job.id)),
        ]);
      } else {
        await update(client, status, text);
      }
    }
    await react(client, m, 'eyes', true);
  } catch (e) {
    log(job?.id, 'talk failed', e);
    await update(client, status, `Sorry, something went wrong: ${failure(e)}`);
    await react(client, m, 'eyes', true);
    await react(client, m, 'x');
  }
}

/** Step 2: make the confirmed change (or, for Undo, revert a published one), build, preview. `status`
 * is the thread message that shows progress and becomes the result. */
async function buildPreview(client: WebClient, job: Job, status: Post, name: string, undo?: Job) {
  const dir = path.join(WORK_DIR, job.id);
  const progress = (step: string) => update(client, status, `Working on it… (${step})`);
  job.status = 'working';
  saveJobs();
  try {
    await linkDeps(dir);
    let agent: AgentResult;
    if (undo?.mergeSha) {
      await revert(dir, undo.mergeSha);
      agent = { text: `This undoes "${undo.title}".`, sessionId: '', costUsd: 0 };
      job.proposal = agent.text;
    } else {
      await progress('editing the site');
      agent = await runAgent(dir, `[Editing] ${name} confirmed. Make the change you proposed.`, 'edit', job.sessionId);
      job.sessionId = agent.sessionId;
      log(job.id, `edit $${agent.costUsd.toFixed(2)}`, agent.error ?? '');
      if (agent.error) throw new Error(`the editing step stopped early (${agent.error})`);
      await dropUnusedMedia(dir);
      job.attached = [];
    }

    const files = await changedFiles(dir);
    if (!files.length) {
      job.status = 'discussing';
      saveJobs();
      await update(client, status, agent.text || "I didn't find anything to change.");
      return;
    }

    // One chance for the agent to fix a failed build.
    await progress('building the site');
    let built = await build(dir, job.id);
    if (!built.ok && !undo) {
      agent = await runAgent(dir, `[Editing] The site build failed after your change. Fix it. Build output:\n\n${built.log}`, 'edit', job.sessionId);
      job.sessionId = agent.sessionId;
      built = await build(dir, job.id);
    }
    if (!built.ok) throw new Error(`the site doesn't build with this change:\n\`\`\`${built.log.slice(-1500)}\`\`\``);
    job.summary = agent.text;

    await progress('uploading the preview');
    job.previewUrl = await publishPreview(dir, job.id);
    const requester = await nameOf(client, job.requester);
    await commitAll(dir, `${job.title}\n\nRequested by ${requester} on Slack.`);
    if (job.pr) { // already submitted for review: keep the pull request in step with the preview
      await pushBranch(dir, job.branch);
      await updatePR(job.pr.number, prBody(job, requester));
    }

    job.status = job.pr ? 'submitted' : 'preview';
    saveJobs();
    const { text, blocks } = previewMessage(job, files);
    await update(client, status, text, blocks);
  } catch (e) {
    log(job.id, 'build failed', e);
    // Keep the thread's work if there is any, so a reply like "try again" picks up where this stopped.
    job.status = fs.existsSync(dir) ? (job.pr ? 'submitted' : 'discussing') : 'failed';
    saveJobs();
    await update(client, status, `Sorry, something went wrong: ${failure(e)}${job.status === 'failed' ? '' : '\nReply here to try again.'}`);
  }
}

/** The preview's message: what changed, and the buttons: Open preview, Submit a PR (until one is open), Merge to
 * main (only on requests from people with merge access), Discard. */
function previewMessage(job: Job, files: string[]) {
  const fileList = files.map((f) => `\`${f.replace(/^site\//, '')}\``).join(', ');
  const submitted = job.status === 'submitted';
  const admin = isApproved(job.requester);
  const next = submitted
    ? admin
      ? 'The pull request is open. Merge to main to publish it. Reply here to change it.'
      : `The pull request is open; someone with merge access (${approvedList()}) will merge it. Reply here to change it.`
    : admin
      ? 'Open the preview. If it looks right, Merge to main to publish it, or Submit a PR to have it reviewed first. Reply here to change it.'
      : `Open the preview. If it looks right, Submit a PR and someone with merge access (${approvedList()}) will merge it. Reply here to change it.`;
  const text = `${job.summary}\n\n${next}`;
  const links = [`Changed ${fileList}`, job.pr && `<${job.pr.url}|Pull request #${job.pr.number}>`].filter(Boolean).join('  ·  ');
  const buttons = [
    { ...button('Open preview', 'open_preview', job.id), url: job.previewUrl },
    !submitted && button('Submit a PR', 'submit', job.id, admin ? undefined : 'primary'),
    admin && button('Merge to main', 'publish', job.id, 'primary'),
    button('Discard', 'discard', job.id),
  ].filter(Boolean);
  return {
    text: `${text}\nPreview: ${job.previewUrl}`, // notification fallback
    blocks: [section(text), context(links), actions(...buttons)],
  };
}

const prBody = (job: Job, requester: string) =>
  `Requested by **${requester}** on Slack.\n\n${job.proposal ?? ''}\n\n${job.summary ?? ''}\n\nPreview: ${job.previewUrl}`;

/** Push the branch and open (or update) its pull request. */
async function ensurePR(client: WebClient, job: Job) {
  const dir = path.join(WORK_DIR, job.id);
  await pushBranch(dir, job.branch);
  const body = prBody(job, await nameOf(client, job.requester));
  if (job.pr) await updatePR(job.pr.number, body);
  else {
    const pr = await openPR(job.branch, job.title, body);
    job.pr = { number: pr.number, url: pr.html_url };
    saveJobs();
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

/** Remove new images (attachments, downloads) the change doesn't use, so they don't end up on the site. */
async function dropUnusedMedia(dir: string) {
  for (const rel of await unusedNewMedia(dir)) fs.rmSync(path.join(dir, rel), { force: true });
}

// --- Buttons ---

type ActionArgs = { ack: () => Promise<void>; body: unknown; action: unknown; client: WebClient };
/** The job a button refers to, the clicker, and the message the button is on. */
function clicked({ body, action }: ActionArgs) {
  const b = body as { user: { id: string }; channel?: { id: string }; message?: { ts: string; text?: string } };
  const job = byId((action as { value: string }).value);
  return { job, user: b.user.id, post: { channel: b.channel!.id, ts: b.message!.ts }, text: b.message?.text ?? '' };
}
const deny = (client: WebClient, job: Job, user: string, text: string) =>
  client.chat.postEphemeral({ channel: job.channel, user, thread_ts: job.threadTs, text }).then(() => {}, () => {});

// A link button: the browser opens the preview; Slack still sends the click, which must be acknowledged.
app.action('open_preview', async ({ ack }) => { await ack(); });

app.action('build', async (args) => {
  await args.ack();
  const { job, user, post, text } = clicked(args);
  if (!job || job.status !== 'proposed') return;
  if (user !== job.requester && !isApproved(user)) return deny(args.client, job, user, 'Only the person who asked, or someone with merge access, can build this.');
  await update(args.client, post, text, [section(text), context(`<@${user}> confirmed.`)]);
  enqueue(async () => {
    const status = await postIn(args.client, job, 'Working on it…');
    await buildPreview(args.client, job, status, await nameOf(args.client, user));
  });
});

app.action('submit', async (args) => {
  await args.ack();
  const { job, user, post } = clicked(args);
  if (!job || job.status !== 'preview') return;
  if (user !== job.requester && !isApproved(user)) return deny(args.client, job, user, 'Only the person who asked, or someone with merge access, can submit this.');
  const status = await postIn(args.client, job, 'Opening a pull request…');
  enqueue(async () => {
    try {
      await ensurePR(args.client, job);
      job.status = 'submitted';
      saveJobs();
      const { text, blocks } = previewMessage(job, await changedFiles(path.join(WORK_DIR, job.id)));
      await update(args.client, post, text, blocks);
      await update(args.client, status, `:inbox_tray: <@${user}> opened <${job.pr!.url}|pull request #${job.pr!.number}>. Nothing is live yet; it goes live when someone with merge access (${approvedList()}) merges it.`);
    } catch (e) {
      log(job.id, 'submit failed', e);
      await update(args.client, status, `Couldn't open the pull request: ${failure(e)}`);
    }
  });
});

app.action('publish', async (args) => {
  await args.ack();
  const { job, user, post } = clicked(args);
  if (!job || (job.status !== 'preview' && job.status !== 'submitted')) return;
  if (!isApproved(user)) return deny(args.client, job, user, `Only people with merge access can merge to main (${approvedList()}).`);
  const status = await postIn(args.client, job, 'Merging to main…');
  enqueue(async () => {
    try {
      await ensurePR(args.client, job);
      job.mergeSha = (await mergePR(job.pr!.number, job.title)).sha;
      job.status = 'merged';
      saveJobs();
      await update(args.client, post, job.summary ?? job.title, [section(job.summary ?? job.title), context(`Merged to main by <@${user}>; see below.`)]);
      const repo = `https://github.com/${config.repo}`;
      const text = [
        `:white_check_mark: Merged to main by <@${user}>.`,
        `• <${job.pr!.url}|Pull request #${job.pr!.number}> is merged into main as commit <${repo}/commit/${job.mergeSha}|${job.mergeSha.slice(0, 7)}>.`,
        `• <${config.siteUrl}|The live site> updates in a few minutes (<${repo}/actions|deploy progress>).`,
      ].join('\n');
      await update(args.client, status, text, [section(text), actions(button('Undo', 'undo', job.id))]);
      await cleanUp(job).catch((e) => log(job.id, 'cleanup failed', e));
    } catch (e) {
      log(job.id, 'publish failed', e);
      await update(args.client, status, `Couldn't merge: ${failure(e)}${job.status === 'merged' ? '' : '\nNothing went live.'}`);
    }
  });
});

app.action('discard', async (args) => {
  await args.ack();
  const { job, user, post } = clicked(args);
  if (!job || !ACTIVE.has(job.status)) return;
  if (user !== job.requester && !isApproved(user)) return deny(args.client, job, user, 'Only the person who asked, or someone with merge access, can discard this.');
  enqueue(async () => {
    if (job.pr) await closePR(job.pr.number).catch((e) => log(job.id, 'close failed', e));
    job.status = 'discarded';
    saveJobs();
    await cleanUp(job).catch((e) => log(job.id, 'cleanup failed', e));
    const original = (args.body as { message?: { text?: string } }).message?.text ?? '';
    await update(args.client, post, original, [section(original), context(`Discarded by <@${user}>.`)]);
    await postIn(args.client, job, `:wastebasket: Discarded by <@${user}>. Nothing was published${job.pr ? ` and <${job.pr.url}|pull request #${job.pr.number}> is closed` : ''}. Message me again to start over.`);
  });
});

app.action('undo', async (args) => {
  await args.ack();
  const { job: published, user } = clicked(args);
  if (!published || published.status !== 'merged') return;
  if (!isApproved(user)) return deny(args.client, published, user, `Only people with merge access can undo a merged change (${approvedList()}).`);
  // Undo is a new request in the same thread (a git revert of the published commit) with its own preview, then Merge to main.
  enqueue(async () => {
    const status = await postIn(args.client, published, 'Working on it… (undoing)');
    const id = newId(`undo ${published.title}`);
    const job: Job = { id, channel: published.channel, threadTs: published.threadTs, requester: user, title: `Undo: ${published.title}`, branch: `bot/${id}`, status: 'working' };
    jobs[`${job.channel}:${job.threadTs}`] = job;
    saveJobs();
    try {
      await newWorktree(job.id, job.branch);
    } catch (e) {
      job.status = 'failed';
      saveJobs();
      return update(args.client, status, `Sorry, something went wrong: ${failure(e)}`);
    }
    await buildPreview(args.client, job, status, await nameOf(args.client, user), published);
  });
});

async function cleanUp(job: Job) {
  await deleteRemoteBranch(job.branch);
  await removeWorktree(job.id, job.branch);
  await removePreview(job.id).catch((e) => log(job.id, 'preview cleanup failed', e));
}

await app.start();
log('redwood-website-bot running');
