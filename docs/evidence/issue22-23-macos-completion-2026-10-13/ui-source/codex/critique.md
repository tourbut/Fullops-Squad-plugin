The change preserves the neutral fixture, visible labels, IDs, existing form behavior, focus styling, and light/dark tokens. New todo exposes Alt+n through aria-keyshortcuts; the handler prevents the default action and focuses the input without calling submission or changing its value.

The shortcut accepts either letter case, excludes Ctrl/Meta combinations and composition, and keeps focus inside the open confirmation dialog. Existing Enter submission remains available. No dependencies, network calls, storage, or additional features were introduced.

ARIA exposes the shortcut to assistive technology without adding visible help text. Browser or operating-system shortcut interception remains outside the page's control. The supplied browser QA and its result.json are the acceptance evidence; canonical file hashes are checked separately.
