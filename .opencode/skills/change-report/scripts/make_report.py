#!/usr/bin/env python3
"""Generate a change report from git ground truth (files, diffs, test results).

Everything factual is captured verbatim from git and the test runner. The
LLM writes only the Summary section. Stdlib only, no dependencies.
"""
import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys

TEST_TIMEOUT = 600


def run(cmd, cwd=None):
    return subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=TEST_TIMEOUT)


def git(*args, cwd=None):
    return run(["git", *args], cwd=cwd)


def detect_test_command(root):
    candidates = ["pytest.ini", "tox.ini"]
    if any(os.path.exists(os.path.join(root, name)) for name in candidates):
        return ["python", "-m", "pytest"]
    pyproject = os.path.join(root, "pyproject.toml")
    if os.path.exists(pyproject):
        with open(pyproject, encoding="utf-8") as fh:
            if "[tool.pytest.ini_options]" in fh.read():
                return ["python", "-m", "pytest"]
    package_json = os.path.join(root, "package.json")
    if os.path.exists(package_json):
        try:
            with open(package_json, encoding="utf-8") as fh:
                scripts = json.load(fh).get("scripts", {})
            if scripts.get("test"):
                return ["npm", "test"]
        except (json.JSONDecodeError, OSError):
            pass
    return None


def main():
    parser = argparse.ArgumentParser(description="Generate a change report file.")
    parser.add_argument("--output", default="change-report.md",
                        help="Report filename (written to the repo root).")
    args = parser.parse_args()

    root = git("rev-parse", "--show-toplevel")
    if root.returncode != 0:
        print("Not a git repository.", file=sys.stderr)
        sys.exit(1)
    root = root.stdout.strip()

    out = os.path.join(root, args.output)
    branch = git("rev-parse", "--abbrev-ref", "HEAD", cwd=root).stdout.strip()

    status = git("status", "--short", "--untracked-files=all", cwd=root).stdout
    name_only = git("diff", "--name-only", cwd=root).stdout.strip()
    untracked = [
        line[3:]
        for line in status.splitlines()
        if line.startswith("??")
    ]
    if git("rev-parse", "--verify", "HEAD", cwd=root).returncode == 0:
        stat = git("diff", "--stat", "HEAD", cwd=root).stdout.strip()
        diff = git("diff", "HEAD", cwd=root).stdout
    else:
        stat = git("diff", "--stat", cwd=root).stdout.strip()
        diff = git("diff", cwd=root).stdout
    # git diff never includes untracked files; capture them as new-file diffs.
    # (exit code 1 is expected here -- differences found -- stdout is still valid)
    for path in untracked:
        diff += git("diff", "--no-index", "/dev/null", path, cwd=root).stdout

    test_cmd = detect_test_command(root)
    if test_cmd:
        result = run(test_cmd, cwd=root)
        test_output = (result.stdout + "\n" + result.stderr).strip()
        if result.returncode == 0:
            test_status = "PASS"
        else:
            test_status = "FAIL (exit {})".format(result.returncode)
        test_command_display = " ".join(test_cmd)
    else:
        test_output = ""
        test_status = "NO TEST COMMAND DETECTED"
        test_command_display = "(none detected)"

    lines = []
    lines.append("# Change Report")
    lines.append("")
    lines.append("Generated: {}".format(datetime.datetime.now().isoformat(timespec="seconds")))
    lines.append("Repository: `{}` (branch `{}`)".format(root, branch))
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("_To be written by the agent._")
    lines.append("")
    lines.append("## Files changed")
    lines.append("")
    if name_only:
        lines.append("```")
        lines.append(status.rstrip())
        lines.append("```")
    else:
        lines.append("No changes detected.")
    lines.append("")
    lines.append("## Diff")
    lines.append("")
    if diff.strip():
        lines.append("```diff")
        lines.append(diff.rstrip())
        lines.append("```")
    else:
        lines.append("No diff against HEAD.")
    lines.append("")
    lines.append("## Tests")
    lines.append("")
    lines.append("Command: `{}`".format(test_command_display))
    lines.append("Result: **{}**".format(test_status))
    lines.append("")
    if test_output:
        lines.append("```")
        lines.append(test_output)
        lines.append("```")

    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    tracked_files = [l for l in name_only.splitlines() if l.strip()]
    num_files = len(tracked_files) + len(untracked)
    print("Report written to {}".format(out))
    print("Files changed: {}".format(num_files))
    print("Tests: {}".format(test_status))


if __name__ == "__main__":
    main()
