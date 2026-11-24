import katex from 'katex';

// Abstracts come from arXiv and friends with LaTeX left in. This turns one into HTML at build time: math ($...$,
// $$...$$, \(...\)) goes through KaTeX, text macros (\emph, \textit, {\em ...}) become italics or bold, -- and ---
// become dashes, quotes become curly, and everything else is escaped. Pages that show the result need
// katex/dist/katex.min.css.
const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]!);
const math = (tex: string) => katex.renderToString(tex, { throwOnError: false, output: 'html' });

function text(s: string) {
  return esc(s)
    .replace(/(\d)--(?=\d)/g, '$1–').replace(/\s*-{2,3}\s*/g, '—') // en dash only in number ranges
    .replace(/\\(?:emph|textit|textsl)\{([^{}]*)\}|\{\\(?:em|it)\s+([^{}]*)\}/g, (_, a, b) => `<i>${a ?? b}</i>`)
    .replace(/\\textbf\{([^{}]*)\}|\{\\bf\s+([^{}]*)\}/g, (_, a, b) => `<b>${a ?? b}</b>`)
    // A bare superscript or subscript outside dollars, as in "L^{2} optimal transport".
    .replace(/\b([A-Za-z])([\^_])\{(\w+)\}/g, (_, x, op, e) => math(`${x}${op}{${e}}`));
}

// Curly quotes, from LaTeX ``...'' or paired straight quotes, with the spaces Semantic Scholar sometimes drops
// around them put back ('the"deep bootstrap"of' -> 'the “deep bootstrap” of').
const quotes = (s: string) => s
  .replace(/``(.+?)''|"([^"]+)"/g, (_, a, b) => `“${a ?? b}”`)
  .replace(/([\w$.,;:)])“/g, '$1 “')
  .replace(/”([\w$(])/g, '” $1');

export function texToHtml(s: string) {
  s = quotes(s);
  const out: string[] = [];
  const re = /\$\$([^$]+)\$\$|\$([^$]+)\$|\\\((.+?)\\\)/g;
  let last = 0;
  for (let m; (m = re.exec(s)); last = re.lastIndex) {
    out.push(text(s.slice(last, m.index)), math(m[1] ?? m[2] ?? m[3]));
  }
  out.push(text(s.slice(last)));
  return out.join('');
}
