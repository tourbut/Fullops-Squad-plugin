# Plan: Alt+n focus shortcut on the existing todo fixture

## Brief (locked)

Preserve the accessible neutral todo fixture. Keep every current label, ID, and behavior. Keep light/dark tokens from `tokens.css`. Add Alt+n so it focuses the New todo input without submitting. Expose `aria-keyshortcuts` on that input. No dependencies, network, storage, or extra features. `DESIGN.md`, `tokens.css`, and `qa.py` stay byte-identical.

This is an acceptance fixture, not a restyle. Visual identity stays the existing high-contrast system-ui form.

## Tokens (unchanged)

From `tokens.css`, inlined in `index.html` with `color-scheme`:

- light bg `#fff`
- light fg `#202020`
- light border `#707070`
- dark bg `#161616`
- dark fg `#eee`
- dark border `#999`
- focus ring `#1686df` (existing `:focus-visible`)

Type: 16px system-ui. Layout: left-aligned `main` max-width 640px, 16px padding, flex wrap form/label, 36px control height. Motion only behind `prefers-reduced-motion: no-preference`.

## Principles

1. One additive behavior: document-level Alt+n focuses `#todo` and does not submit `#add`.
2. Announce the shortcut with `aria-keyshortcuts="Alt+n"` on the New todo input.
3. Leave labels, IDs, live status, load/error/retry, dialog focus restore, theme toggle, details, and counters as they are.
4. No fetch, storage, CDN, or new libraries.

## Implementation

Keep the current HTML/CSS/JS body. On `#todo` add `aria-keyshortcuts="Alt+n"`. On `keydown`, if Alt is held, Ctrl/Meta are not, and the key is `n` / `N` or `code` is `KeyN`: `preventDefault()`, then `input.focus()`. Do not call submit, do not increment `window.submits`.

## QA

Run the supplied `qa.py` against this directory. Inspect `qa-evidence/result.json`. Fix only `index.html` if a check fails.
