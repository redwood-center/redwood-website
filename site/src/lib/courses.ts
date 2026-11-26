import all from '../data/courses.json';
import { url } from './url';

// One record per offering (a course in a term); offerings of the same course share `course`. An offering's page
// content is the HTML in data/courses/<slug>.html; one with a `url` lives elsewhere and has no page here.
export type Offering = (typeof all)[number];
export type Course = { key: string; latest: Offering; offerings: Offering[]; instructors: string[] };

const SEASONS = ['Spring', 'Summer', 'Fall'];
const termKey = (term: string) => {
  const [season, year] = term.split(' ');
  return Number(year) * 10 + SEASONS.indexOf(season);
};

export const offerings: Offering[] = [...all].sort((a, b) => termKey(b.term) - termKey(a.term));

/** Courses, most recently taught first; each with its offerings, newest first. */
export const courses: Course[] = [...new Set(offerings.map((o) => o.course))].map((key) => {
  const list = offerings.filter((o) => o.course === key);
  // Instructors of the most recent offering that names any.
  const instructors = list.find((o) => o.instructors.length)?.instructors ?? [];
  return { key, latest: list[0], offerings: list, instructors };
});

const now = new Date();
const month = now.getUTCMonth() + 1;
/** The term in progress at build time (a daily rebuild keeps it current). */
export const currentTerm = `${month <= 5 ? 'Spring' : month <= 7 ? 'Summer' : 'Fall'} ${now.getUTCFullYear()}`;

export const fullTitle = (o: Offering) => (o.code ? `${o.code}: ${o.title}` : o.title);
export const offeringUrl = (o: Offering) => o.url ?? url(`courses/${o.slug}/`);
export const hasPage = (o: Offering) => !o.url;

const pages = import.meta.glob<string>('../data/courses/*.html', { query: '?raw', import: 'default', eager: true });
const base = import.meta.env.BASE_URL.replace(/\/$/, '');

/** The offering's page content, with site links (/courses/..., /media/...) under the deploy base and tables in
 * a scroll box for narrow screens. */
export function pageHtml(o: Offering) {
  const html = pages[`../data/courses/${o.slug}.html`] ?? '';
  return html
    .replace(/(href|src)="\/(?!\/)/g, `$1="${base}/`)
    .replace(/<table>/g, '<div class="table-scroll"><table>')
    .replace(/<\/table>/g, '</table></div>');
}
