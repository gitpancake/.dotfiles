---
name: ordinal
description: 'Draft, schedule, list, and publish Henry''s LinkedIn posts through Ordinal (tryordinal.com) over its REST API — no MCP. Trigger: "ordinal", "schedule a linkedin post", "what''s queued on linkedin", "draft this week''s posts", "push this to linkedin", any LinkedIn scheduling or Ordinal API work.'
---

# Ordinal (REST API, no MCP)

One thin passthrough — `~/.dotfiles/scripts/ordinal.py`. Every LinkedIn post Henry
publishes goes through Ordinal; nothing posts to LinkedIn directly.

## Ground rules

- **Drafts by default.** `create` lands a post as `ForReview`. Only `schedule <id>` makes it
  go live. Never call `schedule` or create with `--status Scheduled` unless Henry said
  "publish" / "schedule it" for that specific post, or the weekly job runs with
  `LINKEDIN_AUTOPUBLISH=1`.
- **Content rules** (same as the `linkedin-card` skill): success only, no customer names or
  domains, no repo names, PR numbers, ticket ids, incident ids, or internal metrics.
- **Key:** `$ORDINAL_API_KEY` in `~/.claude/.env` (the script loads it). Pro plan only.
  Never echo it.
- Posts are personal-brand content in Henry's voice. Write Simply: short sentences, plain
  words, one idea per sentence, no hashtag walls.

## Running operations

```bash
O=~/.dotfiles/scripts/ordinal.py

"$O" workspace                               # key sanity check
"$O" profiles --channel LinkedIn             # profile id posts publish from
"$O" posts --status ForReview                # drafts waiting on Henry
"$O" posts --status Scheduled                # what is queued to go out
"$O" post <id>

# draft (does not publish)
"$O" create --title "Agents that ship" --publish-at "2026-10-28 09:00" --copy-file post.md

# with an image from the linkedin-card skill
ASSET=$("$O" upload ~/Desktop/cartage-post.png | jq -r .assetId)
"$O" create --title "..." --publish-at "2026-10-30 09:00" --copy-file post.md --asset "$ASSET"

# publish a draft at its publishAt, or move it
"$O" schedule <id>
"$O" schedule <id> --publish-at "2026-10-31 10:00"
"$O" unschedule <id>
"$O" update <id> --copy-file revised.md
"$O" raw GET /labels
```

`--publish-at` takes ISO; a naive value is local time and is sent as UTC.

## Weekly drafting job

`~/.dotfiles/scripts/weekly-linkedin.sh` runs every Monday 08:30 via launchd
(`ai.henry.linkedin-weekly`). It reads the prompt in `weekly-linkedin.prompt.md`, mines the
last 7 days (merged PRs, Linear issues Henry completed, Granola/Pocket digests), drafts three
posts for Tue / Thu / Sat 09:00, creates them in Ordinal as `ForReview`, and writes the
digest to `~/.claude/linkedin-logs/summary-<date>.md`.

- Henry approves in the Ordinal calendar (status → Scheduled) or runs `schedule <id>`.
- `LINKEDIN_AUTOPUBLISH=1` in `~/.claude/.env` → the job schedules them itself.
- `DRY_RUN=1 ~/.dotfiles/scripts/weekly-linkedin.sh` → drafts to the log dir only, no
  Ordinal writes, no key needed.
- Days that already have a `ForReview`/`Scheduled` post are skipped, so re-running is safe.

## API essentials (from docs.tryordinal.com, 2026-10-26)

- Base `https://app.tryordinal.com/api/v1`; `Authorization: Bearer ord_…`. 100 req/min per
  workspace → `429`.
- `POST /posts` body: `title`, `publishAt` (UTC ISO), `status` (`Tentative|ToDo|InProgress|
  ForReview|Blocked|Finalized|Scheduled|Posted`), optional `labelIds`, `notes`, and a channel
  block `linkedIn: { profileId, copy, assets: [{assetId}], poll?, linkPreview? }`.
- `POST /posts/{id}/schedule` body `{publishAt?}` → status `Scheduled`. `unschedule`,
  `archive`, `unarchive` are bare POSTs.
- `GET /posts?limit&cursor&status&channel` → `{posts: [...]}`; cursor = last post id.
- Uploads: `POST /uploads/prepare {filename,mimetype,size}` → multipart POST of
  `params`+`signature`+`file` to `uploadUrl` → poll `GET /uploads/{id}` until `ready` →
  `assetId`. Images ≤10 MB, PDF (LinkedIn carousel) ≤100 MB.
- Mentions in copy: `@[Display Name](urn)`; resolve a urn with `GET /linkedin/mention`.
- `PATCH /posts/{id}` field shape is assumed to mirror create (unverified live).
