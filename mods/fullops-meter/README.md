# fullops-meter

A Claude Code mod for FullOps Squad sessions. It shows the session's model, context and prompt cache in every repository. In a repository with `.fullops-squad/fullops.json`, it also shows the coordinator's workers and reviews.

It works only in Claude Code. It is kept apart from the portable plugin in `plugins/fullops-squad/` and is not part of `dist/`.

## What it shows

- **Hint line** (under the prompt): `opus-5-5 high · ctx 26% · 736k left · cache 94% 59:00`. These are the model and effort, the context used and left, and the last request's cache hit rate with the time until the cache lapses.
- **`/meter`**: the same in detail. It adds the auto-compact point, where the cache lifetime came from and the cache miss reason. `/meter hide` and `/meter show` hide and show the band above the prompt.
- **Notices**: one when the context reaches `warnContextPercent`, and one before a large prompt cache lapses (`warnSeconds`, 5 minutes by default, and at most half the cache lifetime: 2.5 minutes for a 5-minute cache). Above `compactAtTokens`, the notice and the band suggest `/compact` while the cache is still warm. After it lapses, `/compact` would reread the whole conversation at full price too, so the band then only says so and suggests `/clear` when done.

In a FullOps repository:

- **`/fullops` pane**, with two tabs (`w` and `r` switch them while the pane has focus):
  - **Workers**: what the coordinator's Orca run sent out, drawn as animated cards. A summary row counts running, done and failed workers. Each running worker is a card with:
    - a badge in its role's colour, its task key (cut to fit) and a live clock
    - a flag when Orca says it waits on you (`⚠ needs you`), when its agent is gone, or when it has been silent for 5 minutes (`⏸ idle`)
    - a stage rail, `explore → build → verify → report → done`. The current stage spins and the next link flows. In a pane too narrow for the labels, the rail shows icons only, followed by the current stage's name.

    The stage comes from two sources, read every 15 seconds, and never goes back:
    - the harness records in the worker's checkout, which are certain: `lint-result.json` or `pass.json` in its git folder's `fullops-gate/` means verify, and a `_to_<role>.md` log under `.fullops-squad/handovers/logs/` means report. Only files newer than the dispatch count, as the role worktree is reused across tasks.
    - its latest tool calls, from `orca orchestration worker-read --source transcript`: Edit and Write mean build; a Bash call that names a test, lint, gate, check, validate or make step means verify; `worker_done`, `work.py finish` or `orca_wait` mean report; anything else means explore. These are word rules, so a worker that runs undescribed commands can sit at explore until a record proves more.

    A finished worker shows one coloured line for 10 minutes. Surfaces that cannot run the card module (mobile) show the same as a text list.
  - **Reviews**: the independent reviews `review.py` runs before a merge, read from the newest `.fullops-squad/docs/evaluations/qa-reports/*-review/` folders. Each is a block: an icon in the state's colour, the task key, the state in words (`reviewing`, `2 open · high`, `3 resolved`, `no findings`, `waived`, `abandoned`, `superseded`) and how long ago it changed, then the first line of the reviewer's conclusion. Reviews with open findings come first, then the ones under way, then the newest.
  - The Workers tab ends with `queued: K8, K9` for tasks the coordinator has not sent out yet.
- **Footer label**: `fullops coor`, `fullops dev` and so on. The role comes from the checkout's branch and the `roles` in `fullops.json`.
- **Step cards**: a Bash call that runs a FullOps step draws as one line, such as `FullOps start worker → dev K7 (claude)`, `FullOps review prepare K1` or `FullOps wait for worker reports`. Chained commands keep their own row.
- **Spinner**: `… · 2 workers running · 1 review open` while the coordinator has work out.

The mod reads repository files and runs these read-only `orca orchestration` commands: `run-current`, `worker-list`, `task-list` and `worker-read`. It sends nothing anywhere and changes no Orca state.

## Install

In Claude Code 2.1.275 or later:

```
/plugin install fullops-meter --marketplace tourbut/Fullops-Squad-plugin
```

If the FullOps Squad marketplace is already added (as it is after installing FullOps Squad), run `/plugin install fullops-meter@fullops-squad` instead. It loads in sessions started after the install, in every repository. In a repository with `.fullops-squad/fullops.json` it adds `/fullops` and the FullOps views. Elsewhere it shows only the hint line.

## Load it from a checkout

To try a working copy without installing it:

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
