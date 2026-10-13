# Critique

## Scope

The page remains the isolated acceptance fixture. Tokens, copy, IDs, and existing flows are unchanged. The only product change is Alt+n focusing New todo without submit, plus `aria-keyshortcuts="Alt+n"` on `#todo`.

## What holds

- Labels and roles still match the QA script: Dark theme, New todo, Add, Toggle {text}, status, load/retry, dialog Cancel/Confirm clear, Restricted disabled, Details/Back.
- Light/dark CSS variables match `tokens.css`. Theme toggle still sets `data-theme` and `aria-pressed`.
- Form still `preventDefault`s on submit; Add still increments `window.submits` once per click.
- Alt+n calls `focus()` only. It does not dispatch submit, does not fill, does not increment the counter.
- `aria-keyshortcuts` is on the input that the shortcut targets.
- `:focus-visible` outline remains 3px `#1686df`. Reduced-motion still skips the body transition when the QA context sets `reduce`.
- No extra scripts, network, or storage.

## Risks

- Some OS/layout combos map Alt+n to a composed character. The handler also matches `e.code === 'KeyN'` so Playwright `Alt+n` still focuses the field.
- `preventDefault` on Alt+n can block a browser access-key menu. That is required so the shortcut focuses instead of submitting or opening chrome.
- Dialog, load, and history-back behavior were not restyled; history-back remains unexamined in `qa.py` by design.

## Verdict

Accept. The fixture stays accessible and neutral; the shortcut is discoverable and non-submitting. Confirm with the supplied `qa.py` run and `qa-evidence/result.json`.
