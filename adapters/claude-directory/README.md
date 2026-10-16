# FullOps Squad

FullOps Squad is an opt-in development harness for Git repositories. It helps a coordinator agent split work across role-based AI workers, write handover instructions, keep planning and design documents current, run lint and test gates, and review changes before they are merged. Nothing is active in a repository until you ask Claude to run the `setup-fullops` skill there, which creates a `.fullops-squad/` folder in that repository.

## Requirements

- Claude Code, with Git and Python 3.10 or later on `PATH`. On Windows, Claude Code runs hooks through Git Bash.
- Orca IDE for multi-worker orchestration (worker dispatch, terminals, messages). Single-session use works without Orca.
- Optional: the GitHub CLI `gh` for issue mode and the board's issue list, the `ocr` CLI (open-code-review) for pre-merge review preparation, and an OpenRouter API key for Jev routing and search.

## Install

From the Claude plugin directory, add **FullOps Squad**. To install from the project's own marketplace instead:

```shell
claude plugin marketplace add tourbut/Fullops-Squad-plugin
claude plugin install fullops-squad@fullops-squad
```

Then start a new session and ask Claude to set up FullOps in your repository.

The directory edition does not install other plugins. You can optionally add the companion plugins `ponytail@ponytail` and `mattpocock-skills@claude-plugins-official`, and the Context7 MCP server (`context7-mcp`). The installed plugin's `scripts/deps.py --host claude-code` installs these tools for you.

## What it includes

- **Skills**: `setup-fullops`, `update-fullops`, `fullops-orca`, `fullops-work`, `fullops-review`, `fullops-test`, `fullops-deliverables`, `fullops-issues`, `fullops-frontend`, `fullops-motion`.
- **Hooks** (Claude Code only). Every hook runs a Python script inside this plugin through `hooks/run.sh`. Hooks do nothing in repositories without `.fullops-squad/fullops.json`.
  - `SessionStart`: `caveman_start` (optional terse-voice hint), `done_gate start` (records the session baseline), `flow_gate start` (role and routing brief).
  - `UserPromptSubmit`: `flow_gate prompt` (routing reminders).
  - `PreToolUse` on shell, edit, and agent tools: `flow_gate tool`. It can block an action that breaks the repository's role, routing, or integration rules.
  - `PostToolUse` on shell tools: `flow_gate post`. It records Orca completion messages.
  - `Stop`: `done_gate stop` (lint and review gate) and `flow_gate stop` (pending-integration gate, board refresh, which may call `gh issue list`).
  - `SessionEnd`: `issue_mode session-end`. It releases an issue-mode lease.

## Where it works

| App | What loads |
|---|---|
| Claude Code | Skills, hooks, and the scripts that skills run |
| Cowork (local) | Skills and scripts. Hook support depends on the app |
| claude.ai chat | Skills only. Hooks and local scripts do not run |

## Data and network use

The plugin writes only inside the repository you set up and inside that repository's Git directory (`.git/fullops-*`). It sends data off your machine only in the cases below:

- **OpenRouter** (`https://openrouter.ai/api/v1/systemone`): Jev routing, context, and search commands send the task text and selected file excerpts. Secret-like values are redacted first. This happens only when you or a skill runs a `jev_*.py` command, and it requires `OPENROUTER_API_KEY` from your environment or a `.env` file you name.
- **GitHub** (`https://api.github.com` and the `gh` CLI): issue mode reads issues and comments and can create branches and draft pull requests, after you turn it on. The board refresh lists the 30 most recently updated issues of the repository's GitHub remote with `gh issue list`. This refresh also runs from the coordinator's `Stop` hook. Both use your existing `gh` login or `GH_TOKEN`/`GITHUB_TOKEN`. Set `FULLOPS_OFFLINE=1` to skip the issue list.
- **Orca IDE** (local): coordination commands call the local `orca` CLI. No data leaves your machine through Orca unless your Orca setup does so.
- **Optional installs**: `scripts/deps.py` runs `npm`, `npx`, and `claude plugin` commands to install the optional tools above. It runs only when you call it.

Apart from that board issue list, the hooks do not use the network.

## License

MIT. See `LICENSE`.
