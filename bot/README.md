# Redwood Website Bot

A Slack bot that turns requests ("move Alyson Fletcher to alumni, now at UCLA") into changes to the website.

Anyone in the Redwood Slack can DM it, or @mention it in a channel. Each Slack thread is one request:

1. A Claude agent (Agent SDK) edits a fresh git worktree of the website on its own branch. It can only read and edit
   files in that worktree, and never sees the bot's credentials. The repo's `CLAUDE.md` tells it where content lives.
2. The bot builds the site, publishes a preview, posts screenshots of the changed pages, and opens a pull request.
3. If the requester is approved (`config.json` → `approved`), the pull request is merged at once and the site
   redeploys; an Undo button reverts it. Otherwise approved people get Publish / Discard buttons.
4. Replies in the thread revise the change (in channels, @mention the bot in the reply).

## Running it

```sh
cd bot
npm install
npx playwright install chromium-headless-shell
npm start            # node --env-file=.env src/main.ts
```

`bot/.env` (never committed) holds `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`, `GITHUB_TOKEN` and `ANTHROPIC_API_KEY`.
The Slack app is defined by `slack-app-manifest.yml` (Socket Mode, so no public URL is needed). Runtime state
(the clone, worktrees, job records, screenshots, local previews) lives in `bot/state/`.

Previews: with `previews.repo` null in `config.json`, they're served from this machine at
`http://localhost:4500/previews/<id>/` (fine for testing); set `previews.repo` and `previews.url` to publish them to a
GitHub Pages repo instead.

`node --env-file=.env src/try.ts "<request>"` runs one request without Slack or GitHub writes (worktree, agent,
build, preview, screenshots) and prints where everything went. `npm run check` type-checks.
