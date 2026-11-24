// Dry run of a request without Slack or GitHub writes: worktree -> talk -> (if it proposes) edit -> build ->
// Cloudflare preview. The proposal is confirmed automatically.
//   node --env-file=.env src/try.ts "Move Alyson Fletcher to alumni, now at UCLA"
// Leaves the worktree and preview in state/ for inspection; removes the branch with --clean <id>.
import path from 'node:path';

import { runAgent } from './agent.ts';
import { log } from './config.ts';
import { changedFiles, newWorktree, removeWorktree, WORK_DIR } from './git.ts';
import { build, linkDeps, publishPreview } from './site.ts';

const [arg, maybeId] = process.argv.slice(2);
if (arg === '--clean') {
  await removeWorktree(maybeId, `bot/${maybeId}`);
  process.exit(0);
}
const id = `${new Date().toISOString().slice(0, 10).replaceAll('-', '')}-try-${Math.random().toString(36).slice(2, 6)}`;
const dir = await newWorktree(id, `bot/${id}`);
await linkDeps(dir);
const talk = await runAgent(dir, `[Talking] Jamie Simon says:\n\n${arg}`, 'talk');
log('talk:', talk.text, `($${talk.costUsd.toFixed(2)})`, talk.error ?? '');
if (!/\[proposal:/.test(talk.text)) process.exit(0);
const agent = await runAgent(dir, '[Editing] Jamie Simon confirmed. Make the change you proposed.', 'edit', talk.sessionId);
log('edit:', agent.text, `($${agent.costUsd.toFixed(2)})`, agent.error ?? '');
const files = await changedFiles(dir);
log('changed:', files);
if (files.length) {
  const built = await build(dir, id);
  log('build ok:', built.ok, built.log);
  if (built.ok) log('preview:', await publishPreview(dir, id));
}
log('worktree:', path.join(WORK_DIR, id));
process.exit(0);
