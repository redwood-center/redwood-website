// Prefix a site-relative path with the deploy base, so links work under a GitHub Pages subpath.
export function url(path = ''): string {
  const base = import.meta.env.BASE_URL.replace(/\/$/, '');
  return `${base}/${path.replace(/^\//, '')}`;
}

const dateFmt = new Intl.DateTimeFormat('en-US', { month: 'long', day: 'numeric', year: 'numeric', timeZone: 'UTC' });
const shortFmt = new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' });
const weekdayFmt = new Intl.DateTimeFormat('en-US', { weekday: 'long', timeZone: 'UTC' });

export const formatDate = (iso: string) => dateFmt.format(new Date(iso));
export const formatShort = (iso: string) => shortFmt.format(new Date(iso));
export const weekday = (iso: string) => weekdayFmt.format(new Date(iso));
