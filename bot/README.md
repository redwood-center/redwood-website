# Redwood Website Bot

A Slack bot that turns requests ("move Alyson Fletcher to alumni, now at UCLA") into changes to the website.

Anyone in the Redwood Slack can DM it, or @mention it in a channel. Each Slack thread is one request:

1. **Talk.** A Claude agent (Agent SDK) works out the change with the requester, reading (not editing) a fresh git
   worktree of the website. When it knows the change, it describes it and asks them to confirm. The repo's
   `CLAUDE.md` tells it where content lives.
2. **Preview.** On confirmation (a reply like "go ahead", or the Build preview button) the agent edits the worktree.
   The bot builds the site, uploads a preview to Cloudflare Pages and posts its link. Replies
   go back to step 1 for a revision. In channels, a request starts with an @mention; replies in its thread don't
   need one.
3. **Merge or submit.** The preview message has Open preview, Submit a PR (anyone: opens a pull request for review),
   Merge to main (only on requests from people with merge access, `config.json` → `approved`: opens the pull request
   if needed and merges it, and the site redeploys) and Discard. Each button gets a reply in the thread: the pull
   request, the merged commit, a link to the deploy. An Undo button reverts a merged change, through a preview.
   `everyoneCanPublishUntil` in `config.json` gives everyone merge access until that time (a trial period).

Nothing goes live from a message: only Merge to main, or merging the pull request on GitHub. The agent can only read and edit files in its worktree (editing only after
confirmation), and never sees the bot's credentials.

## Running it

```sh
cd bot
npm install
npm start            # node --env-file=.env src/main.ts
```

`bot/.env` (never committed) holds `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`, `GITHUB_TOKEN`, `ANTHROPIC_API_KEY`,
`CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN` (a token with Account → Cloudflare Pages → Edit). The Slack app is
defined by `slack-app-manifest.yml` (Socket Mode, so no public URL is needed). Runtime state (the clone, worktrees,
job records) lives in `bot/state/`.

Previews: each request's build is uploaded with wrangler as a branch deployment of the Cloudflare Pages project
`previews.project`, at `https://<date>-<suffix>.<previews.domain>/`, and deleted when the request is published or
discarded.

`node --env-file=.env src/try.ts "<request>"` runs one request without Slack or GitHub writes (worktree, talk, edit
with the proposal confirmed automatically, build, preview) and prints where everything went.
`npm run check` type-checks.
