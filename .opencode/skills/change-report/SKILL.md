---
name: change-report
description: Use when the user asks for a report of what was changed, what you changed, what was done, or a summary of changes after a task. Generates a token-efficient change report file (files changed, diffs, test status) from git ground truth.
---

# Change Report

Generate a change report **file**. Do NOT paste diffs or test output into your reply, and do not reconstruct changes from memory — the script captures everything from git.

1. Run the generator script from this skill's directory (use the skill base directory path):
   `python "<skill-base-dir>/scripts/make_report.py"`
   It writes `change-report.md` at the repo root, capturing files changed, diffs, and test results verbatim. It prints a one-line confirmation (path, file count, test status).

2. Read ONLY the first ~15 lines of the report (bounded read, `limit: 15`) to reach the `## Summary` placeholder. Never read the diff section into context.

3. Edit the `_To be written by the agent._` placeholder with a concise 2-5 sentence description of what was done and why — based on the session, not the diff.

4. Reply to the user in 1-2 lines: report path, number of files changed, and test PASS/FAIL. Nothing more.

If the script reports "Not a git repository" or "No changes detected", say so briefly and stop.
