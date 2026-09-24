# FullOps Squad agent guide

When a user asks you to install FullOps Squad, follow the "설치" section of [README.md](README.md). Install from the GitHub marketplace `tourbut/Fullops-Squad-plugin`; do not clone this repository for a normal install.

1. Identify the AI CLI running this conversation: Codex, Claude Code, or grok. If it cannot be identified, ask. For agy, or when the user wants to install a development checkout, follow the checkout install in [docs/development.md](docs/development.md).
2. Run that CLI's marketplace and install commands from the README. For Claude Code, register the ponytail and claude-plugins-official marketplaces first so plugin dependencies resolve.
3. Install external dependencies with the installed plugin's `scripts/deps.py --host <host>` (`codex`, `claude-code`, `grok`), then confirm with `scripts/deps.py --check`.
4. Report the installed version and any failed command. Tell the user that a new agent session is needed before running the `setup-fullops` skill.

Installation is global to the selected CLI. Activate the harness in a service repository only when the user asks for setup there; that separate step creates `.fullops-squad/` in the chosen repository.

For development, edit `plugins/fullops-squad/` (portable source) and `adapters/` (host-specific metadata). Run `python3 scripts/build.py` to regenerate `dist/native/fullops-squad/` and commit the result; never edit generated files by hand. The GitHub marketplace serves the committed `dist/`, and CI fails when it differs from a fresh build. Run `npm ci` and `npm test` for standard-schema and packaging checks. The root marketplace catalogs point to the generated native package, so build before host validation or direct marketplace installation.

With the pinned OCR CLI installed, run `python3 tests/review-check.py` to verify delegate preparation and review-record gates in a temporary repository. `fullops-review` uses the host agent for reasoning; the OCR CLI dependency is a tool, not an MCP server.
