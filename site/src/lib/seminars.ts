import all from '../data/seminars.json';
import { url } from './url';

export type Seminar = (typeof all)[number] & { date: string };

// Evaluated at build time; a scheduled daily rebuild keeps "upcoming" current.
export const today = new Date().toISOString().slice(0, 10);
export const seminars: Seminar[] = all.filter((s): s is Seminar => Boolean(s.date));

export const upcoming: Seminar[] = seminars
  .filter((s) => s.date >= today)
  .sort((a, b) => a.date.localeCompare(b.date));

export const past: Seminar[] = seminars
  .filter((s) => s.date < today)
  .sort((a, b) => b.date.localeCompare(a.date));

export const seminarUrl = (s: Seminar) => url(`seminars/${s.slug}/`);

// Abstracts (`summary`) are plain text: paragraphs separated by a blank line, links written as [text](url) or as a
// bare URL or email address.

const LINK = /\[([^\]]+)\]\((\S+?)\)|(https?:\/\/[^\s<]*[^\s<.,;:!?)\]'"’”])|([\w.+-]+@[\w-]+(?:\.[\w-]+)+)/g;
const esc = (t: string) => t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const link = (href: string, text: string) => (/^(https?:|mailto:)/.test(href) ? `<a href="${esc(href)}">${text}</a>` : text);

function inline(text: string) {
  let out = '';
  let last = 0;
  for (const m of text.matchAll(LINK)) {
    out += esc(text.slice(last, m.index));
    if (m[1]) out += link(m[2], esc(m[1]));
    else if (m[3]) out += link(m[3], esc(m[3]));
    else out += link(`mailto:${m[4]}`, esc(m[4]));
    last = m.index + m[0].length;
  }
  return (out + esc(text.slice(last))).replace(/\n/g, '<br>');
}

/** The abstract as HTML paragraphs (each a string of escaped text and links). */
export const abstractParagraphs = (s: Seminar) =>
  (s.summary ?? '').split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean).map(inline);

/** The abstract's first paragraph as plain text, cut at a word near `limit` characters. */
export function abstractExcerpt(s: Seminar, limit = 320) {
  const first = (s.summary ?? '').split(/\n\s*\n/)[0].replace(/\[([^\]]+)\]\(\S+?\)/g, '$1').replace(/\s+/g, ' ').trim();
  if (first.length <= limit) return first;
  return `${first.slice(0, first.lastIndexOf(' ', limit)).replace(/[\s,;:.]+$/, '')}…`;
}

/** Lowercase without accents, for matching names ("Tošić" ~ "tosic"). */
export const searchable = (t: string) => t.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
