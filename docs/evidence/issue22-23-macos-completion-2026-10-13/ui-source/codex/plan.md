1. Preserve existing markup, labels, IDs, behavior, styles, and light/dark tokens; leave DESIGN.md, tokens.css, and qa.py byte-identical.
2. Add aria-keyshortcuts="Alt+n" to New todo and a keydown handler that focuses it and prevents default without submitting. Match Alt+n case-insensitively, exclude Ctrl/Meta combinations and composition, and respect the modal dialog.
3. Write critique.md, run the supplied exact browser QA command, inspect qa-evidence/result.json, and verify canonical file hashes. If QA fails, change only index.html and rerun.
