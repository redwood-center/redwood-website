// Building a worktree's site and publishing it as a preview.
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';

import { BOT_DIR, STATE, config, log, secret } from './config.ts';
import { run } from './git.ts';

const DEPS = path.join(STATE, 'site-deps'); // one shared node_modules for every worktree
const WRANGLER = path.join(BOT_DIR, 'node_modules', '.bin', 'wrangler');

/** Link the worktree's site/node_modules to the shared install, reinstalling when the lockfile changes. */
export async function linkDeps(dir: string) {
  const site = path.join(dir, 'site');
  const lock = fs.readFileSync(path.join(site, 'package-lock.json'));
  const hash = crypto.createHash('sha256').update(lock).digest('hex');
  const stamp = path.join(DEPS, '.lock-hash');
  if (!fs.existsSync(stamp) || fs.readFileSync(stamp, 'utf8') !== hash) {
    log('installing site dependencies');
    fs.mkdirSync(DEPS, { recursive: true });
    for (const f of ['package.json', 'package-lock.json']) fs.copyFileSync(path.join(site, f), path.join(DEPS, f));
    await run('npm', ['ci', '--no-audit', '--no-fund'], DEPS);
    fs.writeFileSync(stamp, hash);
  }
  const link = path.join(site, 'node_modules');
  if (!fs.existsSync(link)) fs.symlinkSync(path.join(DEPS, 'node_modules'), link);
}

// Previews: each request's build is uploaded to Cloudflare Pages as a branch deployment of one project, at
// https://<alias>.<previews.domain>/ (a stable URL per request).

/** Cloudflare's name for a request's preview: date and random suffix of the id ("20261124-rav9"), well under
 * Pages' 28-character limit for branch aliases. */
const alias = (id: string) => `${id.slice(0, 8)}-${id.slice(-4)}`.toLowerCase();

export const previewUrl = (id: string) => `https://${alias(id)}.${config.previews.domain}/`;

/** Build the site for its preview URL. Returns the build log's tail on failure. */
export async function build(dir: string, id: string): Promise<{ ok: boolean; log: string }> {
  try {
    await run('npx', ['astro', 'build'], path.join(dir, 'site'), { SITE: previewUrl(id), BASE: '/', PUBLIC_NOINDEX: 'true' });
    return { ok: true, log: '' };
  } catch (e) {
    const err = e as { stdout?: string; stderr?: string; message: string };
    const text = `${err.stdout ?? ''}\n${err.stderr ?? ''}`.trim() || err.message;
    return { ok: false, log: text.split('\n').slice(-60).join('\n') };
  }
}

/** Upload the build to Cloudflare. Returns the preview URL. */
export async function publishPreview(dir: string, id: string) {
  secret('CLOUDFLARE_API_TOKEN');
  secret('CLOUDFLARE_ACCOUNT_ID');
  await run(WRANGLER, ['pages', 'deploy', path.join(dir, 'site', 'dist'), '--project-name', config.previews.project,
    '--branch', alias(id), '--commit-dirty=true', '--commit-message', id], STATE, { WRANGLER_SEND_METRICS: 'false', CI: 'true' });
  return previewUrl(id);
}

/** Delete the request's deployments (newest first; a busy month has far fewer than 100 previews). */
export async function removePreview(id: string) {
  for (let page = 1; page <= 4; page++) {
    const list = await pagesApi('GET', `/deployments?env=preview&per_page=25&page=${page}`);
    for (const d of list as { id: string; deployment_trigger?: { metadata?: { branch?: string } } }[]) {
      if (d.deployment_trigger?.metadata?.branch === alias(id)) await pagesApi('DELETE', `/deployments/${d.id}?force=true`);
    }
    if ((list as unknown[]).length < 25) break;
  }
}

async function pagesApi(method: string, rest: string): Promise<unknown> {
  const url = `https://api.cloudflare.com/client/v4/accounts/${secret('CLOUDFLARE_ACCOUNT_ID')}/pages/projects/${config.previews.project}${rest}`;
  const res = await fetch(url, { method, headers: { Authorization: `Bearer ${secret('CLOUDFLARE_API_TOKEN')}` } });
  const data = (await res.json().catch(() => null)) as { success?: boolean; result?: unknown; errors?: unknown } | null;
  if (!data?.success) throw new Error(`Cloudflare ${method} ${rest}: ${res.status} ${JSON.stringify(data?.errors ?? null)}`);
  return data.result;
}
