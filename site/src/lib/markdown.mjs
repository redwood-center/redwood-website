// @ts-check
// Plugins for the Sätteri Markdown processor (astro.config.mjs). They run on blog posts at build time.
import katex from 'katex';

// Math: Sätteri parses $...$ and $$...$$ (features.math) into math nodes; this renders them with KaTeX. In .md
// the HTML goes in as an inline html node; MDX can't take those, so there it goes in as `raw`, which Sätteri
// parses into JSX. Pages need katex/dist/katex.min.css.
/** @param {{ sourceFormat: string }} doc */
export const katexMath = ({ sourceFormat }) => {
  /** @param {any} node @param {any} ctx @param {boolean} displayMode */
  const render = (node, ctx, displayMode) => {
    const html = katex.renderToString(node.value, { displayMode, throwOnError: false });
    ctx.replaceNode(node, sourceFormat === 'mdx' ? { raw: html, mdxExpressions: false } : { type: 'html', value: html });
  };
  return {
    name: 'katex-math',
    /** @param {any} node @param {any} ctx */
    inlineMath: (node, ctx) => render(node, ctx, false),
    /** @param {any} node @param {any} ctx */
    math: (node, ctx) => render(node, ctx, true),
  };
};
