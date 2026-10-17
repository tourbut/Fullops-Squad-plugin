# fullops-meter

A Claude Code mod for FullOps Squad sessions. It shows the session's model, context and prompt cache in every repository. In a repository with `.fullops-squad/fullops.json`, it also shows the coordinator's workers and reviews.

It works only in Claude Code. It is kept apart from the portable plugin in `plugins/fullops-squad/` and is not part of `dist/`.

## What it shows

- **Hint line** (under the prompt): `opus-5-5 high · ctx 26% · 736k left · cache 94% 59:00`. These are the model and effort, the context used and left, and the last request's cache hit rate with the time until the cache lapses.
- **`/meter`**: the same in detail. It adds the auto-compact point, where the cache lifetime came from and the cache miss reason. `/meter hide` and `/meter show` hide and show the band above the prompt.
- **Notices**: one when the context reaches `warnContextPercent`, and one shortly before a large prompt cache lapses.

In a FullOps repository:

- **`/fullops` pane**, with two tabs (`w` and `r` switch them while the pane has focus):
  - **Workers**: what the coordinator's Orca run sent out. For each running worker it shows:
    - Orca's activity and attention flags
    - the worker's last words
    - its latest tool calls
    - when it last did anything

    These are read every 15 seconds from `orca orchestration worker-read --source transcript`. A finished worker shows one line for 10 minutes.
  - **Reviews**: the newest `.fullops-squad/docs/evaluations/qa-reports/*-review/` folders. Each shows its state (recorded, waived, abandoned, superseded or open), its open findings and the start of its conclusion.
- **Footer label**: `fullops coor`, `fullops dev` and so on. The role comes from the checkout's branch and the `roles` in `fullops.json`.
- **Step cards**: a Bash call that runs a FullOps step draws as one line, such as `FullOps start worker → dev K7 (claude)`, `FullOps review prepare K1` or `FullOps wait for worker reports`. Chained commands keep their own row.
- **Spinner**: `… · 2 workers running · 1 review open` while the coordinator has work out.

The mod reads repository files and runs these read-only `orca orchestration` commands: `run-current`, `worker-list`, `task-list` and `worker-read`. It sends nothing anywhere and changes no Orca state.

## Load it

From a checkout of this repository:

```sh
claude --plugin-dir <path-to-this-repo>/mods/fullops-meter
```

To keep the conversation of a running session, exit it and resume with `claude --resume <session-id> --plugin-dir <path-to-this-repo>/mods/fullops-meter`. Add the session's own flags too, such as `--dangerously-skip-permissions`.

Settings are under `/config`: `cacheTtl` (`auto`, `5m`, `1h`), `warnContextPercent`, `showBand`, `warnSeconds` and `compactAtTokens`.

## Develop

```sh
claude plugin validate mods/fullops-meter
claude plugin test mods/fullops-meter
npx -p typescript@5.6.3 tsc -p mods/fullops-meter --noEmit
```

The engine writes `.claude-plugin/types/` when it loads the mod, and `tsconfig.json` extends the config in that folder. Load the mod once before you type-check it. The folder is not committed.

All strings, tests and comments are in English.
