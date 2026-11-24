import all from '../data/seminars.json';

export type Seminar = (typeof all)[number] & { date: string };

// Evaluated at build time; a scheduled daily rebuild keeps "upcoming" current.
const today = new Date().toISOString().slice(0, 10);
const dated = all.filter((s): s is Seminar => Boolean(s.date));

export const upcoming: Seminar[] = dated
  .filter((s) => s.date >= today)
  .sort((a, b) => a.date.localeCompare(b.date));

export const past: Seminar[] = dated
  .filter((s) => s.date < today)
  .sort((a, b) => b.date.localeCompare(a.date));

// Seminar detail pages aren't rebuilt yet; link to the old site's page for now.
export const seminarUrl = (s: Seminar) => `https://redwood.berkeley.edu/seminars/${s.slug}/`;
