// @ts-check
import { defineConfig } from 'astro/config';
import { satteri } from '@astrojs/markdown-satteri';
import fs from 'node:fs';
import path from 'node:path';
import { katexMath } from './src/lib/markdown.mjs';

// Paper review decisions (Papers page, dev only) are saved here, outside src/ so saving doesn't reload the page.
const REVIEW_FILE = path.resolve('../papers-db/review.json');

/** Dev-server endpoint the Papers page posts review decisions to: {id: {status?, category?}}; null clears one. */
function paperReview() {
  return {
    name: 'paper-review',
    /** @param {import('vite').ViteDevServer} server */
    configureServer(server) {
      server.middlewares.use('/__paper-review', (req, res) => {
        const read = () => (fs.existsSync(REVIEW_FILE) ? JSON.parse(fs.readFileSync(REVIEW_FILE, 'utf8')) : {});
        if (req.method === 'GET') {
          res.setHeader('content-type', 'application/json');
          res.end(JSON.stringify(read()));
          return;
        }
        let body = '';
        req.on('data', (c) => (body += c));
        req.on('end', () => {
          const all = read();
          for (const [id, v] of Object.entries(JSON.parse(body))) {
            if (v === null) delete all[id];
            else all[id] = v;
          }
          fs.mkdirSync(path.dirname(REVIEW_FILE), { recursive: true });
          fs.writeFileSync(REVIEW_FILE, JSON.stringify(all, null, 1) + '\n');
          res.setHeader('content-type', 'application/json');
          res.end(JSON.stringify({ saved: Object.keys(all).length }));
        });
      });
    },
  };
}

// For GitHub Pages, set SITE (e.g. https://rctn.github.io) and BASE (e.g. /redwood-website)
// in the deploy workflow. Locally both default to the root.
export default defineConfig({
  site: process.env.SITE ?? 'http://localhost:4321',
  base: process.env.BASE ?? '/',
  trailingSlash: 'ignore',
  devToolbar: { enabled: false },
  // Jekyll (which builds jamiesimon.io, where the draft is hosted) skips `_`-prefixed folders like `_astro`.
  build: { assets: 'assets' },
  // Blog posts: $...$ and $$...$$ math, rendered with KaTeX.
  markdown: { processor: satteri({ features: { math: true }, mdastPlugins: [katexMath] }) },
  vite: { plugins: [paperReview()] },
});
