// Building a worktree's site, publishing it as a preview, and screenshotting the pages a change touched.
import crypto from 'node:crypto';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';

import { chromium } from 'playwright';

import { STATE, config, log } from './config.ts';
import { botCommit, git, run } from './git.ts';

const DEPS = path.join(STATE, 'site-deps'); // one shared node_modules for every worktree
const LOCAL = path.join(STATE, 'previews-local'); // served at http://localhost:<localPort>/previews/<id>/
const PREVIEWS_CLONE = path.join(STATE, 'previews');

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

export const previewBase = (id: string) => `/previews/${id}`;

export function previewUrl(id: string) {
  return config.previews.repo && config.previews.url
    ? `${config.previews.url}/${id}/`
    : `http://localhost:${config.previews.localPort}${previewBase(id)}/`;
}

/** Build the site with the preview's base path. Returns the build log's tail on failure. */
export async function build(dir: string, id: string): Promise<{ ok: boolean; log: string }> {
  const site = config.previews.url ? new URL(config.previews.url).origin : `http://localhost:${config.previews.localPort}`;
  try {
    await run('npx', ['astro', 'build'], path.join(dir, 'site'), { SITE: site, BASE: previewBase(id), PUBLIC_NOINDEX: 'true' });
    return { ok: true, log: '' };
  } catch (e) {
    const err = e as { stdout?: string; stderr?: string; message: string };
    const text = `${err.stdout ?? ''}\n${err.stderr ?? ''}`.trim() || err.message;
    return { ok: false, log: text.split('\n').slice(-60).join('\n') };
  }
}

/** Copy the build to the local preview server, and to the previews repo if one is configured. */
export async function publishPreview(dir: string, id: string) {
  const dist = path.join(dir, 'site', 'dist');
  const local = path.join(LOCAL, 'previews', id);
  fs.rmSync(local, { recursive: true, force: true });
  fs.mkdirSync(path.dirname(local), { recursive: true });
  fs.cpSync(dist, local, { recursive: true });
  if (!config.previews.repo) return;
  if (!fs.existsSync(path.join(PREVIEWS_CLONE, '.git'))) {
    await run('git', ['clone', '--quiet', `https://github.com/${config.previews.repo}.git`, PREVIEWS_CLONE], STATE);
  }
  await git(PREVIEWS_CLONE, 'pull', '--quiet', '--rebase');
  const target = path.join(PREVIEWS_CLONE, id);
  fs.rmSync(target, { recursive: true, force: true });
  fs.cpSync(dist, target, { recursive: true });
  await git(PREVIEWS_CLONE, 'add', '-A');
  await botCommit(PREVIEWS_CLONE, `Preview ${id}`).catch(() => {}); // nothing to commit if the build is unchanged
  await git(PREVIEWS_CLONE, 'push', '--quiet');
}

export async function removePreview(id: string) {
  fs.rmSync(path.join(LOCAL, 'previews', id), { recursive: true, force: true });
  if (!config.previews.repo || !fs.existsSync(path.join(PREVIEWS_CLONE, id))) return;
  await git(PREVIEWS_CLONE, 'pull', '--quiet', '--rebase');
  await git(PREVIEWS_CLONE, 'rm', '-r', '--quiet', id);
  await botCommit(PREVIEWS_CLONE, `Remove preview ${id}`);
  await git(PREVIEWS_CLONE, 'push', '--quiet');
}

// --- Local preview server (also what the screenshots are taken from) ---

const TYPES: Record<string, string> = {
  '.html': 'text/html; charset=utf-8', '.css': 'text/css', '.js': 'text/javascript', '.json': 'application/json',
  '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp',
  '.woff2': 'font/woff2', '.ico': 'image/x-icon', '.txt': 'text/plain', '.pdf': 'application/pdf',
};

export function startPreviewServer() {
  fs.mkdirSync(LOCAL, { recursive: true });
  http.createServer((req, res) => {
    const rel = decodeURIComponent(new URL(req.url ?? '/', 'http://x').pathname);
    let file = path.join(LOCAL, path.normalize(rel));
    if (!file.startsWith(LOCAL)) { res.writeHead(403).end(); return; }
    if (fs.existsSync(file) && fs.statSync(file).isDirectory()) file = path.join(file, 'index.html');
    if (!fs.existsSync(file)) { res.writeHead(404).end('Not found'); return; }
    res.writeHead(200, { 'content-type': TYPES[path.extname(file).toLowerCase()] ?? 'application/octet-stream' });
    fs.createReadStream(file).pipe(res);
  }).listen(config.previews.localPort, '127.0.0.1');
}

// --- Which pages to screenshot ---

/** Pages (paths relative to the site root) that a set of changed files shows up on, most specific first. */
export function routesFor(files: string[]) {
  const routes: string[] = [];
  const add = (...r: string[]) => r.forEach((x) => routes.includes(x) || routes.push(x));
  for (const f of files) {
    const blog = f.match(/^site\/src\/content\/blog\/(.+)\.md$/);
    const page = f.match(/^site\/src\/pages\/(.+)\.astro$/);
    if (f.endsWith('data/people.json') || f.startsWith('site/public/media/people/')) add('people/');
    else if (f.endsWith('data/seminars.json')) add('seminars/', '');
    else if (f.endsWith('data/research.ts')) add('research/', '');
    else if (blog) add(`blog/${blog[1]}/`, 'blog/');
    else if (page && !page[1].includes('[')) add(page[1] === 'index' ? '' : `${page[1].replace(/\/index$/, '')}/`);
    else if (f.startsWith('site/src/')) add('');
  }
  return routes.slice(0, 3);
}

/** Names or titles near the change (in the changed lines or the context just above them), to scroll the
 * screenshot to: an edited alumnus's affiliation isn't shown on the page, but their name is. */
export function focusTexts(diff: string) {
  const out: string[] = [];
  let near = '';
  for (const line of diff.split('\n')) {
    if (line.startsWith('+++') || line.startsWith('---') || line.startsWith('@@')) { near = ''; continue; }
    const json = line.match(/"(?:name|speaker|title)":\s*"([^"]{3,80})"/);
    if (json && !line.startsWith('-')) near = json[1];
    if (line.startsWith('+') && near && !out.includes(near)) out.push(near);
  }
  return out.slice(0, 3);
}

export async function screenshots(id: string, routes: string[], focus: string[]) {
  const shots: string[] = [];
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 }, deviceScaleFactor: 2 });
    for (const route of routes) {
      await page.goto(`http://127.0.0.1:${config.previews.localPort}${previewBase(id)}/${route}`, { waitUntil: 'networkidle' });
      await page.waitForTimeout(route.startsWith('papers') ? 5000 : 1500); // let the hero grids and paper map settle
      for (const t of focus) {
        const hit = page.getByText(t, { exact: false }).first();
        if (await hit.count()) {
          await hit.evaluate((el) => el.scrollIntoView({ block: 'center' }));
          await page.waitForTimeout(300);
          break;
        }
      }
      const file = path.join(STATE, 'shots', `${id}-${route.replace(/\W+/g, '-') || 'home'}.png`);
      fs.mkdirSync(path.dirname(file), { recursive: true });
      await page.screenshot({ path: file });
      shots.push(file);
    }
  } finally {
    await browser.close();
  }
  return shots;
}
