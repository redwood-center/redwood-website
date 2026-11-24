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
  // Where previews go: a GitHub Pages repo (repo + url), or, with repo null, a local server on localPort.
  previews: { repo: string | null; url: string | null; localPort: number };
  approved: Record<string, string>; // Slack user ID -> name; their requests are merged automatically
};

export const config: Config = JSON.parse(fs.readFileSync(path.join(BOT_DIR, 'config.json'), 'utf8'));

export function secret(name: string): string {
  const v = process.env[name];
  if (!v) throw new Error(`${name} is not set (bot/.env)`);
  return v;
}

export const isApproved = (user: string) => Object.hasOwn(config.approved, user);

export function log(...parts: unknown[]) {
  console.log(new Date().toISOString(), ...parts);
}
