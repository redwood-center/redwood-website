// Dry run of a request without Slack or GitHub writes: worktree -> agent -> build -> local preview -> screenshots.
//   node --env-file=.env src/try.ts "Move Alyson Fletcher to alumni, now at UCLA"
// Leaves the worktree and preview in state/ for inspection; removes the branch with --clean <id>.
import path from 'node:path';

import { runAgent } from './agent.ts';
import { log } from './config.ts';
import { changedFiles, diffText, newWorktree, removeWorktree, WORK_DIR } from './git.ts';
import { build, focusTexts, linkDeps, previewUrl, publishPreview, routesFor, screenshots, startPreviewServer } from './site.ts';

const [arg, maybeId] = process.argv.slice(2);
if (arg === '--clean') {
  await removeWorktree(maybeId, `bot/${maybeId}`);
  process.exit(0);
}
const id = `try-${Date.now().toString(36)}`;
const dir = await newWorktree(id, `bot/${id}`);
await linkDeps(dir);
const agent = await runAgent(dir, `Jamie Simon asks on Slack:\n\n${arg}`);
log('agent:', agent.text, `($${agent.costUsd.toFixed(2)})`, agent.error ?? '');
const files = await changedFiles(dir);
log('changed:', files);
if (files.length) {
  const built = await build(dir, id);
  log('build ok:', built.ok, built.log);
  if (built.ok) {
    await publishPreview(dir, id);
    startPreviewServer();
    const shots = await screenshots(id, routesFor(files), focusTexts(await diffText(dir)));
    log('preview:', previewUrl(id), 'screenshots:', shots);
  }
}
log('worktree:', path.join(WORK_DIR, id));
process.exit(0);
