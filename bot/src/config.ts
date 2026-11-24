// Settings: bot/config.json (repo, model, approved Slack users, previews) and secrets from bot/.env.
import fs from 'node:fs';
import path from 'node:path';

export const BOT_DIR = path.resolve(import.meta.dirname, '..');
export const STATE = path.join(BOT_DIR, 'state');

type Config = {
  repo: string; // owner/name of the website repo
  siteUrl: string; // the live site, for "published" messages
  model: string;
  maxBudgetUsd: number; // per agent run
  // Previews: a Cloudflare Pages project and its domain (<project>.pages.dev, possibly with a suffix Cloudflare
  // added), and the local port the latest build is served on for screenshots.
  previews: { project: string; domain: string | null; localPort: number };
  approved: Record<string, string>; // Slack user ID -> name: who can publish
};

export const config: Config = JSON.parse(fs.readFileSync(path.join(BOT_DIR, 'config.json'), 'utf8'));

export function secret(name: string): string {
  const v = process.env[name];
  if (!v) throw new Error(`${name} is not set (bot/.env)`);
  return v;
}

export const isApproved = (user: string) => Object.hasOwn(config.approved, user);

const SECRETS = ['SLACK_BOT_TOKEN', 'SLACK_APP_TOKEN', 'GITHUB_TOKEN', 'ANTHROPIC_API_KEY', 'CLOUDFLARE_API_TOKEN'];

/** Remove every credential (raw, or base64 in a git auth header) from text bound for Slack, GitHub or the log. */
export function redact(text: string) {
  let out = text.replace(/(AUTHORIZATION:\s*\w+\s+)\S+/gi, '$1[redacted]');
  for (const name of SECRETS) {
    const v = process.env[name];
    if (!v) continue;
    for (const form of [v, Buffer.from(`x-access-token:${v}`).toString('base64')]) out = out.split(form).join('[redacted]');
  }
  return out;
}

export function log(...parts: unknown[]) {
  const text = parts.map((p) => (p instanceof Error ? p.stack ?? p.message : typeof p === 'string' ? p : JSON.stringify(p)));
  console.log(new Date().toISOString(), redact(text.join(' ')));
}
