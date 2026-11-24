// Git and GitHub: one clone of the website repo in state/repo, and a git worktree per request in state/work/<id>,
// each on its own branch. The GitHub token is passed per command as a header, never written into a git config the
// agent could read.
import { execFile } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { promisify } from 'node:util';

import { STATE, config, redact, secret } from './config.ts';

const exec = promisify(execFile);
export const REPO_DIR = path.join(STATE, 'repo');
export const WORK_DIR = path.join(STATE, 'work');
const BOT_AUTHOR = ['-c', 'user.name=Redwood Website Bot', '-c', 'user.email=redwood-website-bot@users.noreply.github.com'];

function auth() {
  const basic = Buffer.from(`x-access-token:${secret('GITHUB_TOKEN')}`).toString('base64');
  return ['-c', `http.https://github.com/.extraheader=AUTHORIZATION: basic ${basic}`];
}

/** Run a command. On failure, throws an error naming the command without its `-c` settings (which carry the
 * GitHub token) and with any credential scrubbed from its output, so the message is safe to show in Slack. */
export async function run(cmd: string, args: string[], cwd: string, env: Record<string, string> = {}) {
  try {
    const { stdout } = await exec(cmd, args, { cwd, env: { ...process.env, ...env }, maxBuffer: 64 << 20 });
    return stdout;
  } catch (e) {
    const err = e as { stdout?: string; stderr?: string };
    const shown = args.filter((a, i) => a !== '-c' && args[i - 1] !== '-c');
    const failure = new Error(redact(`${cmd} ${shown.join(' ')} failed: ${(err.stderr ?? '').trim()}`)) as Error & { stdout: string; stderr: string };
    failure.stdout = redact(err.stdout ?? '');
    failure.stderr = redact(err.stderr ?? '');
    throw failure;
  }
}

export const git = (cwd: string, ...args: string[]) => run('git', args, cwd);
const gitAuth = (cwd: string, ...args: string[]) => run('git', [...auth(), ...args], cwd);

export async function ensureClone() {
  if (!fs.existsSync(path.join(REPO_DIR, '.git'))) {
    fs.mkdirSync(STATE, { recursive: true });
    await gitAuth(STATE, 'clone', '--quiet', `https://github.com/${config.repo}.git`, REPO_DIR);
  }
  // Each worktree's site/node_modules is a symlink to shared dependencies; the repo's `node_modules/` rule only
  // matches directories, so ignore the link here (info/exclude applies to every worktree, and isn't committed).
  fs.writeFileSync(path.join(REPO_DIR, '.git', 'info', 'exclude'), 'node_modules\n');
}

/** A fresh worktree for request `id` on a new branch from the latest main. */
export async function newWorktree(id: string, branch: string) {
  await ensureClone();
  await gitAuth(REPO_DIR, 'fetch', '--quiet', '--prune', 'origin');
  const dir = path.join(WORK_DIR, id);
  await git(REPO_DIR, 'worktree', 'add', '--quiet', '-b', branch, dir, 'origin/main');
  return dir;
}

export async function removeWorktree(id: string, branch: string) {
  const dir = path.join(WORK_DIR, id);
  if (fs.existsSync(dir)) await git(REPO_DIR, 'worktree', 'remove', '--force', dir).catch(() => {});
  await git(REPO_DIR, 'branch', '-D', branch).catch(() => {});
}

/** Files changed in the worktree since its branch point (committed or not), e.g. ['site/src/data/people.json']. */
export async function changedFiles(dir: string) {
  await git(dir, 'add', '-A');
  const out = await git(dir, 'diff', '--cached', '--name-only', 'origin/main');
  return out.split('\n').filter(Boolean);
}

export async function diffText(dir: string) {
  await git(dir, 'add', '-A');
  return git(dir, 'diff', '--cached', 'origin/main');
}

export const botCommit = (cwd: string, message: string) => run('git', [...BOT_AUTHOR, 'commit', '--quiet', '-m', message], cwd);

/** Commit everything in the worktree (if anything changed). */
export async function commitAll(dir: string, message: string) {
  await git(dir, 'add', '-A');
  const staged = await git(dir, 'diff', '--cached', '--name-only');
  if (staged.trim()) await botCommit(dir, message);
}

/** Push the worktree's branch to GitHub. */
export const pushBranch = (dir: string, branch: string) =>
  gitAuth(dir, 'push', '--quiet', '--force-with-lease', 'origin', `HEAD:refs/heads/${branch}`);

// --- GitHub REST ---

async function gh(method: string, url: string, body?: unknown) {
  const res = await fetch(`https://api.github.com/repos/${config.repo}${url}`, {
    method,
    headers: {
      Authorization: `Bearer ${secret('GITHUB_TOKEN')}`,
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) throw new Error(`GitHub ${method} ${url}: ${res.status} ${data?.message ?? text}`);
  return data;
}

export async function openPR(branch: string, title: string, body: string): Promise<{ number: number; html_url: string }> {
  return gh('POST', '/pulls', { title, body, head: branch, base: 'main' });
}
export const updatePR = (n: number, body: string) => gh('PATCH', `/pulls/${n}`, { body });
export const mergePR = (n: number, title: string): Promise<{ sha: string }> =>
  gh('PUT', `/pulls/${n}/merge`, { merge_method: 'squash', commit_title: `${title} (#${n})` });

/** Revert a commit on the worktree's branch (fetching first, so the commit is known). */
export async function revert(dir: string, sha: string) {
  await gitAuth(REPO_DIR, 'fetch', '--quiet', 'origin');
  await run('git', [...BOT_AUTHOR, 'revert', '--no-edit', sha], dir);
}
export const closePR = (n: number) => gh('PATCH', `/pulls/${n}`, { state: 'closed' });
export const deleteRemoteBranch = (branch: string) => gh('DELETE', `/git/refs/heads/${branch}`).catch(() => {});
