// Read-only git history for the agent, as two tools (mcp__git__log and mcp__git__show). The agent can't run
// commands or read .git, so these are its only view of past changes: who changed what and when, and the diffs,
// e.g. to undo a change by editing the files back. Arguments are validated and passed to git without a shell.
import { execFile } from 'node:child_process';
import path from 'node:path';
import { promisify } from 'node:util';

import { createSdkMcpServer, tool } from '@anthropic-ai/claude-agent-sdk';
import { z } from 'zod';

const exec = promisify(execFile);
const LIMIT = 40_000; // characters of output per call

export const HISTORY_TOOLS = new Set(['mcp__git__log', 'mcp__git__show']);

export function historyServer(cwd: string) {
  const text = (t: string) => ({ content: [{ type: 'text' as const, text: t.length > LIMIT ? `${t.slice(0, LIMIT)}\n[truncated]` : t || '(nothing)' }] });
  const fail = (t: string) => ({ ...text(t), isError: true });
  // A path inside the working copy, relative to it ('' for the whole site).
  const rel = (p?: string) => {
    if (!p) return '';
    const r = path.relative(cwd, path.resolve(cwd, p));
    return r.startsWith('..') || path.isAbsolute(r) ? null : r;
  };
  const git = async (...args: string[]) => (await exec('git', args, { cwd, maxBuffer: 16 << 20 })).stdout;

  return createSdkMcpServer({
    name: 'git',
    tools: [
      tool(
        'log',
        "The website's change history, newest first: short commit id, date, author and title of each change (titles end in the pull request number, e.g. (#12)). Optionally only changes touching one file or folder, by one author, or since a date.",
        {
          path: z.string().optional().describe('A file or folder in the working copy, e.g. site/src/data/people.json'),
          author: z.string().max(100).optional().describe('Part of an author name'),
          since: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).optional().describe('YYYY-MM-DD'),
          max: z.number().int().min(1).max(100).optional().describe('How many changes (default 30)'),
        },
        async ({ path: p, author, since, max }) => {
          const r = rel(p);
          if (r === null) return fail(`${p} is outside the website's files.`);
          const args = ['log', `-n${max ?? 30}`, '--date=short', '--format=%h %ad %an: %s'];
          if (author) args.push(`--author=${author}`);
          if (since) args.push(`--since=${since}`);
          args.push('HEAD', '--');
          if (r) args.push(r);
          return text(await git(...args).catch((e) => `git log failed: ${(e as Error).message}`));
        },
        { annotations: { readOnlyHint: true } },
      ),
      tool(
        'show',
        'One change from the history: its id, author, date, full message and diff (optionally only for one file or folder).',
        {
          commit: z.string().regex(/^[0-9a-f]{4,40}$/).describe('Commit id from the log, e.g. 72a1f63'),
          path: z.string().optional().describe('Limit the diff to this file or folder'),
        },
        async ({ commit, path: p }) => {
          const r = rel(p);
          if (r === null) return fail(`${p} is outside the website's files.`);
          const args = ['show', '--stat', '--patch', '--format=fuller', commit, '--'];
          if (r) args.push(r);
          return text(await git(...args).catch((e) => `git show failed: ${(e as Error).message}`));
        },
        { annotations: { readOnlyHint: true } },
      ),
    ],
  });
}
