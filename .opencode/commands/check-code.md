---
description: Full pre-commit pipeline - runs all checks, then stages, commits, and pushes to the current branch. Usage: /check-code <commit message>
---

You are running a full pre-commit pipeline. The commit message is "$1". Follow every step in order. If any step fails, stop immediately, report the failure in detail, and do NOT proceed to the next step.

---

## Step 1: Branch Verification
Run: `git branch --show-current`

Confirm the current branch is `custom_agent_implementation`. If it is not, abort and warn the user.

---

## Step 2: Backend Lint
Run using the .venv Python (not system Python):
```
.venv/Scripts/python.exe -m ruff check apps/api/app tests scripts/w1_arq_smoke_enqueue.py --select E9,F63,F7,F82
```

If there are any lint errors, stop and report them. Do not proceed.

---

## Step 3: Backend Compile Sanity
Run using the .venv Python:
```
.venv/Scripts/python.exe -m compileall apps/api/app scripts
```

If there are any compile errors, stop and report them. Do not proceed.

---

## Step 4: Backend Tests
Run using the .venv Python:
```
.venv/Scripts/python.exe -m unittest discover -s tests -p "test_*.py" -v
```

If any tests fail, stop and report which tests failed and why. Do not proceed.

---

## Step 5: Frontend Lint
First, ensure Node.js 22 is active using fnm:
```
eval "$(fnm env)" && fnm use 22
```

Then run from `apps/web`: `npm run lint`

If there are any lint errors, stop and report them. Do not proceed.

---

## Step 6: Frontend Build + Typecheck
First, ensure Node.js 22 is active using fnm:
```
eval "$(fnm env)" && fnm use 22
```

Then run from `apps/web`: `npm run build`

If the build or typecheck fails, stop and report the errors. Do not proceed.

---

## Step 7: Git Status Summary
Run: `git status`

Display the list of staged and unstaged changes to the user before proceeding.

---

## Step 8: Stage All Changes
Run: `git add .`

---

## Step 9: Commit
Run: `git commit -m "$1"`

Use the commit message provided by the user. If no message was provided, infer a concise conventional commit message (e.g. `feat: ...`, `fix: ...`) based on the staged changes.

---

## Step 10: Push
Run: `git push origin custom_agent_implementation`

---

## Step 11: Final Report
Output a clear summary:
- List each step and whether it passed.
- Confirm the commit hash and branch that was pushed to.
- Remind the user to check the CI/CD pipeline on GitHub.
