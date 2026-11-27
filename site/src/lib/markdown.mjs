// @ts-check
// Plugins for the Sätteri Markdown processor (astro.config.mjs). They run on blog posts at build time.
import katex from 'katex';

// Margin notes: each footnote reference ([^label]) becomes a numbered label, a checkbox and the note's text,
// and the footnote list at the end of the post goes away. CSS in the blog template floats the note into the
// right margin on wide screens; on narrow ones the label toggles it open below the line. Notes hold inline
// content only, so a note with several paragraphs is joined with line breaks.
export const marginNotes = () => {
  /** @type {Map<string, any[]>} */
  const notes = new Map();
  let n = 0;
  return {
    name: 'margin-notes',
    before(root) {
      /** @param {any} node */
      const walk = (node) => {
        for (const child of node.children ?? []) {
          if (child.type === 'footnoteDefinition') {
            const blocks = child.children.map((/** @type {any} */ b) => (b.type === 'paragraph' ? b.children : [b]));
            notes.set(child.identifier, blocks.flatMap((/** @type {any[]} */ b, /** @type {number} */ i) => (i ? [{ type: 'break' }, ...b] : b)));
          } else walk(child);
        }
      };
      walk(root);
    },
    footnoteReference(node, ctx) {
      const note = notes.get(node.identifier);
      if (!note) return;
      n += 1;
      const id = `sn-${n}`;
      // Element nodes rather than raw HTML, which MDX can't take.
      /** @param {string} type @param {string} tag @param {object} props @param {any[]} [children] */
      const el = (type, tag, props, children) => ({ type, data: { hName: tag, hProperties: props }, children });
      ctx.replaceNode(node, [
        el('marginNoteRef', 'label', { className: ['sn-ref'], htmlFor: id }, [{ type: 'text', value: `${n}` }]),
        el('marginNoteToggle', 'input', { type: 'checkbox', className: ['sn-toggle'], id }),
        el('marginNote', 'span', { className: ['sidenote'] }, [
          el('marginNoteNum', 'span', { className: ['sn-num'] }, [{ type: 'text', value: `${n}` }]),
          ...note,
        ]),
      ]);
    },
    footnoteDefinition(node, ctx) {
      ctx.removeNode(node);
    },
  };
};

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
