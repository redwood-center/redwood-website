// Which papers are in: Jamie's review decisions (papers-db/review.json) win over the automatic ones
// (papers-db/auto-review.json, from scripts/papers/auto_review.py). Read with fs at build time, not imported, so the
// dev server doesn't reload pages when the review tool saves a decision.
import fs from 'node:fs';
import path from 'node:path';

type Decision = { status?: 'in' | 'out'; category?: string };
const read = (f: string) => {
  const p = path.resolve('../papers-db', f);
  return fs.existsSync(p) ? JSON.parse(fs.readFileSync(p, 'utf8')) : {};
};

export function loadDecisions() {
  const review: Record<string, Decision> = read('review.json');
  const auto: Record<string, { status: 'in' | 'out'; why: string }> = read('auto-review.json');
  const status = (id: string) => review[id]?.status ?? auto[id]?.status;
  const category = (id: string, fallback: string | null) => review[id]?.category ?? fallback;
  return { review, auto, status, category };
}
