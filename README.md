# Redwood Center website

The website of the [Redwood Center for Theoretical Neuroscience](https://redwood.berkeley.edu) at UC Berkeley.

- `site/`: the site itself, built with [Astro](https://astro.build). People, seminars and news are JSON files in
  `site/src/data/`; blog posts are Markdown files in `site/src/content/blog/`.
- `papers-db/` and `scripts/papers/`: the pipeline that collects the Center's papers (Semantic Scholar, arXiv,
  OpenAlex, Crossref), decides which are in, and lays out the paper map.
- `scripts/figures/`: how the homepage's receptive-field grids were chosen.

Every push to `main` rebuilds the site and publishes it with GitHub Pages (`.github/workflows/deploy.yml`).

To work on it locally:

```sh
cd site
npm install
npm run dev      # http://localhost:4321
```
