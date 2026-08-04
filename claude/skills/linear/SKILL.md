---
name: linear
description: 'Do anything on Linear via its GraphQL API — read/create/update/comment on issues, projects, cycles, labels, states, users, sub-issues, relations, attachments. Trigger: "linear", an issue id (AOA-###/AO-###/ENGH-###), or any Linear read/write beyond linear-ticket.py''s create/comment/state.'
---

# Linear (GraphQL, no MCP)

Full reach into Linear via one thin passthrough — `~/.dotfiles/scripts/linear-gql.py` runs any
query/mutation. No MCP server means no Linear tool schemas loaded into session context (the
per-session tax MCP charged). Use this for anything beyond the three hardcoded operations in
`linear-ticket.py`.

## Ground rules

Ticket doctrine (Linear = source of truth for tickets/epics, ENGH/AOA/AO teams, AE
retired, `$TICKETS_DIR` = materialization cache only) lives in global CLAUDE.md §Ticket
Lifecycle — it applies unchanged here. The `/ship` hot path still uses `linear-ticket.py`
(`create`/`comment`/`state`); reach for `linear-gql.py` for everything else — reads,
projects, relations, description updates.

## Running operations

Query source: `--query`, `--query-file`, or stdin. Variables: `--variables '<json>'` or
`--variables-file`. Prints the `data` object as pretty JSON (`--compact` for one line, `--raw` for
the full envelope). Exits nonzero + stderr on GraphQL/transport errors.

```bash
G=~/.dotfiles/scripts/linear-gql.py

# inline
"$G" --query 'query { viewer { id name } }'

# stdin heredoc — the safe way to pass a multi-line op (dodges the zsh echo/JSON trap)
"$G" --variables '{"id":"AOA-42"}' <<'GQL'
query($id: String!) { issue(id: $id) { title description state { name } assignee { name } } }
GQL
```

**No `echo` round-trips** for queries or comment bodies (global CLAUDE.md §Shell Gotchas) —
heredoc, `--query-file`, `--variables-file`, or `printf '%s'`. Auth: `$LINEAR_API_KEY`
(standard resolution; the script loads it — don't pass a key).

## API essentials

- Endpoint `https://api.linear.app/graphql`; header `Authorization: <raw key>` (**no** `Bearer`).
- **Issue identifier vs id.** `issue(id: "AOA-42")` accepts the human identifier OR the UUID. But
  mutations wanting a `parentId`/`issueId`/etc. need the **UUID** — fetch it first (`issue(id:
  "AOA-42"){ id }`).
- Mutations return a `{ success, <entity> }` payload — always select `success` and check it.
- Enums: issue `priority` is `0` none · `1` urgent · `2` high · `3` medium · `4` low. Workflow
  `state.type` ∈ `backlog|unstarted|started|completed|canceled` (name is team-specific, e.g. "In
  Progress", "Done").
- Pagination: connections take `first`/`after`, return `pageInfo { hasNextPage endCursor }`.
- Filtering: most connections take a `filter:` (e.g. `issues(filter: { state: { type: { eq:
  "started" } } })`) and `orderBy: createdAt|updatedAt`.

## Recipes

**Find IDs you'll need (team id, state ids, label ids):**
```graphql
query { teams { nodes { id key name
  states { nodes { id name type } }
  labels { nodes { id name } } } } }
```

**Create an issue** (`teamId` required; get it from the teams query above):
```graphql
mutation($input: IssueCreateInput!) { issueCreate(input: $input) {
  success issue { identifier url } } }
```
variables: `{"input":{"teamId":"<uuid>","title":"…","description":"…md…","priority":2,"stateId":"<uuid>","labelIds":["<uuid>"],"assigneeId":"<uuid>","parentId":"<uuid>"}}`

**Comment:** `commentCreate(input: { issueId: "<uuid>", body: "…md…" }) { success comment { url } }`
— body via `--variables-file` to keep markdown intact.

Everything else composes from the schema: `issueUpdate`, `issueRelationCreate`
(`blocks|related|duplicate`), `searchIssues(term)`, `projects`/`cycles`/`projectCreate`,
sub-issues via `parentId`.

**Discover any shape you don't know** — introspect instead of guessing a field name:
```graphql
query { __type(name: "IssueCreateInput") { inputFields { name type { name kind ofType { name } } } } }
```
Swap `IssueCreateInput` for `Issue`, `Comment`, `Project`, any type. When unsure a field exists,
introspect or run a tiny probe query before building the full mutation — never invent field names.

## Extending

If a workflow calls the same op repeatedly, promote it to a named subcommand in `linear-ticket.py`
(the fast path) rather than re-pasting GraphQL. Ad-hoc / one-off / exploratory → `linear-gql.py`.
