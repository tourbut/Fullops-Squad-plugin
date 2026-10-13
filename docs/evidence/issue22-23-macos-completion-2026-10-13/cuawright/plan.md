# Task
Select dark theme, add milk exactly once, then complete it.

# Parameters
| name | type | source phrase from task | default | allowed / format |
|---|---|---|---|---|
| url | str | isolated fixture | http://127.0.0.1:57186/healthy | ALLOWED four explicit loopback URLs |
| todo | str | add milk | milk | nonempty todo text |

# Critical Points
- [ ] CP1: dark theme visibly selected.
- [ ] CP2: exactly one submission and one row with exact todo text.
- [ ] CP3: checkbox checked.
- [ ] CP4: actual theme/submissions/rows/text/checked independently captured.
