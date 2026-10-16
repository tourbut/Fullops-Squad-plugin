# FullOps Squad privacy policy

Last updated: 2026-10-16

FullOps Squad is an open-source plugin for Claude Code, Codex and grok. This page describes what the plugin does with data. The project is maintained by tourbut. Source: https://github.com/tourbut/Fullops-Squad-plugin

## Summary

- The plugin runs on your machine. It does not run a server and has no telemetry, analytics, or account system of its own.
- It writes files only inside the repository you set it up in (`.fullops-squad/`), inside that repository's Git directory (`.git/fullops-*`), and in a local response cache (`~/.cache/fullops-squad/jev`). It also keeps hook runtime files under `~/.fullops-squad/runtime` in the own-marketplace edition.
- It sends data to other services only in the cases below, and only when the matching feature runs. Each service handles that data under its own terms and privacy policy.
- It is not directed at people under 18.

## Data sent to other services

| Service | When | What is sent | Credential |
|---|---|---|---|
| Jev through TypeSafe (`https://api.typesafe.ai/v1/systemone`) or OpenRouter (`https://openrouter.ai/api/v1/systemone`) | You or a skill runs a `jev_*.py` command (routing, search, classification, web and Unity test loops) | The task description and selected file excerpts from your repository. Values that look like secrets are blocked before sending | `TYPESAFE_API_KEY` or `OPENROUTER_API_KEY` that you provide |
| GitHub (`https://api.github.com`, `gh` CLI) | Issue mode is switched on, the board refreshes its issue list, or a draft pull request is created | Issue and comment text you already have on GitHub, status comments, branches, pull requests. The board reads the latest 30 issues of the repository's GitHub remote | Your `gh` login or `GH_TOKEN` / `GITHUB_TOKEN` |
| Context7 (`https://mcp.context7.com/mcp`), directory edition only | Claude uses the Context7 documentation tools | The library name and the documentation question | Optional `context7_api_key` plugin setting |

Set `FULLOPS_OFFLINE=1` to stop Jev calls and the board's issue list. Set `FULLOPS_JEV_ENABLED=0` to stop Jev calls only.

## Data stored locally

- Handover instructions, planning documents, review and test records, and board data are written to your repository. You own them and decide whether to commit them.
- Jev responses are cached by request content in `~/.cache/fullops-squad/jev` so the same request is not sent twice. Delete the folder to clear it.
- Your API keys stay in your environment or in `.fullops-squad/.env`, which the plugin's generated `.gitignore` excludes from Git. A key is passed to the service through a request header on standard input, not on a command line. The Context7 key, if you set one, is stored by Claude Code in your operating system's credential store.

## What we do not do

- We do not collect, receive, or store your code, prompts, keys, or usage on any server we operate. There is none.
- We do not sell or share data.
- We do not read credentials other than the ones named above.

## Your choices

- Do not set the API keys and the matching features stay off or fall back to local behavior. See `CREDENTIALS.md` in the plugin for each key.
- Uninstall the plugin and delete `.fullops-squad/` in your repositories, `~/.cache/fullops-squad`, and `~/.fullops-squad` to remove its files.

## Changes and contact

Changes to this policy are made in this file, and the date above changes. Questions and reports: https://github.com/tourbut/Fullops-Squad-plugin/issues
