# FullOps Squad agent guide

When a user asks you to install FullOps Squad from this repository, follow the installation section of [README.md](README.md) and use `scripts/install.py` as the installation entry point.

1. Locate an existing checkout of `https://github.com/tourbut/Fullops-Squad-plugin` or clone it to a persistent directory outside the service repository. Keep that checkout: Codex and Claude Code register it as a local marketplace source.
2. Identify the AI CLI running this conversation. Select its `--host` value: `codex`, `claude-code`, `grok`, or `agy`. Use `all` only when the user requests all four. If the current CLI cannot be identified, ask which host to install.
3. From the plugin checkout, run `python3 scripts/install.py --host <host> --dry-run`, then `python3 scripts/install.py --host <host>`. The installer builds the native adapter from the Agent Plugins 1.0.0 source, then installs the plugin and dependencies declared in root `dependencies.json`.
4. Check that the plugin is available in the selected CLI and report the installed host and any failed command. Tell the user that a new agent session is needed before running the `setup-fullops` skill.

Installation is global to the selected CLI. Activate the harness in a service repository only when the user asks for setup there; that separate step creates `.fullops-squad/` in the chosen repository.

For development, edit `plugins/fullops-squad/` (portable source) and `adapters/` (host-specific metadata). Run `python3 scripts/build.py` to regenerate `dist/native/fullops-squad/`; never edit generated files. Run `npm ci` and `npm test` for standard-schema and packaging checks. The root marketplace catalogs point to the generated native package, so build before host validation or direct marketplace installation.

With the pinned OCR CLI installed, run `python3 tests/review-check.py` to verify delegate preparation and review-record gates in a temporary repository. `fullops-review` uses the host agent for reasoning; the OCR CLI dependency is a tool, not an MCP server.
