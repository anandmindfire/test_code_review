#!/usr/bin/env python3

import json
import os
import re
import sys
import urllib.error
import urllib.request

# --------------------------------------------------------------------------- #
# Config (override via env in the workflow)
# --------------------------------------------------------------------------- #
MODEL           = os.environ.get("MODEL", "qwen2.5-coder:7b-instruct-q4_0")
OLLAMA_URL      = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/chat")
REVIEW_EXTS     = tuple(os.environ.get("REVIEW_EXTS", ".py,.js,.ts,.tsx,.jsx,.go,.rb,.java,.rs,.c,.cpp,.h").split(","))
MAX_FILES       = int(os.environ.get("MAX_FILES", "20"))
MAX_ADDED_LINES = int(os.environ.get("MAX_ADDED_LINES", "400"))   # per file, keeps CPU inference bounded
ALLOW_APPROVE   = os.environ.get("ALLOW_APPROVE", "false").lower() == "true"
SNAP_WINDOW     = int(os.environ.get("SNAP_WINDOW", "2"))          # recover near-miss line numbers

MARKER = "<!-- ai-code-review:summary -->"

GITHUB_API   = os.environ["GITHUB_API_URL"] if "GITHUB_API_URL" in os.environ else "https://api.github.com"
TOKEN        = os.environ["GITHUB_TOKEN"]
REPO         = os.environ["GITHUB_REPOSITORY"]              # "owner/name"
EVENT_PATH   = os.environ["GITHUB_EVENT_PATH"]


# --------------------------------------------------------------------------- #
# Small HTTP helpers
# --------------------------------------------------------------------------- #
def gh_request(method, path, body=None, accept="application/vnd.github+json"):
    url = path if path.startswith("http") else f"{GITHUB_API}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Accept", accept)
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read().decode()
            if accept == "application/vnd.github+json" and raw:
                return resp.status, json.loads(raw)
            return resp.status, raw
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def ollama_chat(prompt):
    body = {
        "model": MODEL,
        "stream": False,
        "format": "json",                 # force valid JSON out of the model
        "messages": [{"role": "user", "content": prompt}],
        "options": {"temperature": 0.2},
    }
    req = urllib.request.Request(
        OLLAMA_URL, data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=600) as resp:
        payload = json.loads(resp.read().decode())
    return payload.get("message", {}).get("content", "")


# --------------------------------------------------------------------------- #
# Diff parsing
# --------------------------------------------------------------------------- #
HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def parse_unified_diff(diff_text):
    """
    Returns { filepath: {"added": {lineno: code, ...}} }
    `added` maps NEW-file line numbers (valid RIGHT-side comment anchors) to code.
    """
    files, cur, new_ln = {}, None, 0
    for line in diff_text.splitlines():
        if line.startswith("diff --git"):
            cur = None
        elif line.startswith("+++ "):
            path = line[4:]
            path = path[2:] if path.startswith("b/") else path
            if path == "/dev/null":
                cur = None
            else:
                cur = path
                files.setdefault(cur, {"added": {}})
        elif line.startswith("@@"):
            m = HUNK_RE.match(line)
            new_ln = int(m.group(1)) if m else 0
        elif cur is not None and line and line[0] in " +-":
            if line.startswith("+"):
                files[cur]["added"][new_ln] = line[1:]
                new_ln += 1
            elif line.startswith("-"):
                pass                      # removed line: no new-file number
            else:
                new_ln += 1               # context line advances new-file counter
    return files


# --------------------------------------------------------------------------- #
# Model prompt / response handling
# --------------------------------------------------------------------------- #
def build_prompt(path, added):
    numbered = "\n".join(f"{ln}: {code}" for ln, code in sorted(added.items()))
    valid = ", ".join(str(ln) for ln in sorted(added))
    return f"""You are a senior software engineer performing a code review on a pull request.
Below are the ADDED/CHANGED lines of `{path}`, each prefixed with its real line number.

Only these line numbers may be referenced: {valid}

Review for real bugs, security issues, error handling, edge cases, and clear
optimizations. Ignore pure style unless it causes bugs. Do NOT invent problems.

Respond with ONLY a JSON object of this exact shape (no prose, no markdown):
{{
  "summary": "1-3 sentence plain-English summary of what this file's changes do",
  "findings": [
    {{
      "line": <one of the allowed line numbers>,
      "severity": "blocking" | "warning" | "nit",
      "comment": "specific, actionable feedback"
    }}
  ]
}}
If the code looks correct, return an empty findings array.

Code:
{numbered}
"""


def review_file(path, added):
    if not added:
        return {"summary": "", "findings": []}
    # bound the payload for CPU inference
    if len(added) > MAX_ADDED_LINES:
        keep = dict(sorted(added.items())[:MAX_ADDED_LINES])
        added = keep
    try:
        content = ollama_chat(build_prompt(path, added))
        data = json.loads(content)
    except (json.JSONDecodeError, urllib.error.URLError, KeyError) as e:
        print(f"  ! model/parse error for {path}: {e}", file=sys.stderr)
        return {"summary": f"_(review skipped: {type(e).__name__})_", "findings": []}

    valid_lines = sorted(added.keys())
    valid_set = set(valid_lines)
    clean = []
    for f in data.get("findings", []):
        try:
            ln = int(f["line"])
        except (KeyError, ValueError, TypeError):
            continue
        if not f.get("comment"):
            continue
        # Recover off-by-one/two: snap to the nearest changed line within window.
        if ln not in valid_set:
            near = min(valid_lines, key=lambda v: abs(v - ln))
            if abs(near - ln) <= SNAP_WINDOW:
                ln = near
            else:
                continue  # too far from any changed line -> drop rather than 422
        sev = f.get("severity", "warning").lower()
        sev = sev if sev in ("blocking", "warning", "nit") else "warning"
        clean.append({"line": ln, "severity": sev, "comment": f["comment"].strip()})
    return {"summary": data.get("summary", "").strip(), "findings": clean}


# --------------------------------------------------------------------------- #
# Posting
# --------------------------------------------------------------------------- #
SEV_EMOJI = {"blocking": "🛑", "warning": "⚠️", "nit": "💡"}


def post_review(pr_number, head_sha, all_findings, event):
    comments = [
        {
            "path": path,
            "line": f["line"],
            "side": "RIGHT",
            "body": f"{SEV_EMOJI[f['severity']]} **{f['severity']}** — {f['comment']}",
        }
        for path, f in all_findings
    ]
    total = len(comments)
    blocking = sum(1 for _, f in all_findings if f["severity"] == "blocking")
    body = (
        f"### 🤖 AI Code Review\n\n"
        f"Model: `{MODEL}` · {total} inline comment(s), {blocking} blocking.\n\n"
        + ("Requesting changes — see blocking comments below."
           if event == "REQUEST_CHANGES"
           else "Looks good." if event == "APPROVE"
           else "Non-blocking feedback below.")
    )
    payload = {"commit_id": head_sha, "body": body, "event": event, "comments": comments}
    status, resp = gh_request("POST", f"/repos/{REPO}/pulls/{pr_number}/reviews", payload)

    if status >= 400:
        print(f"  ! review POST failed ({status}): {resp}", file=sys.stderr)
        # Fallback 1: APPROVE not allowed for Actions -> downgrade to COMMENT.
        if event == "APPROVE":
            print("  -> retrying as COMMENT (Actions cannot approve here)", file=sys.stderr)
            payload["event"] = "COMMENT"
            status, resp = gh_request("POST", f"/repos/{REPO}/pulls/{pr_number}/reviews", payload)
        # Fallback 2: an invalid inline anchor -> post summary-only review.
        if status >= 400:
            print("  -> retrying summary-only (dropping inline comments)", file=sys.stderr)
            payload["comments"] = []
            payload["event"] = "COMMENT"
            status, resp = gh_request("POST", f"/repos/{REPO}/pulls/{pr_number}/reviews", payload)
    print(f"  review submitted: HTTP {status}")


def upsert_summary(pr_number, per_file_summaries, all_findings, event):
    blocking = sum(1 for _, f in all_findings if f["severity"] == "blocking")
    warn = sum(1 for _, f in all_findings if f["severity"] == "warning")
    nit = sum(1 for _, f in all_findings if f["severity"] == "nit")
    verdict = {"REQUEST_CHANGES": "🛑 Changes requested",
               "APPROVE": "✅ Approved",
               "COMMENT": "💬 Commented"}[event]

    lines = [
        MARKER,
        "## 🤖 AI Code Review — Summary",
        "",
        f"**Verdict:** {verdict}  ",
        f"**Findings:** {blocking} blocking · {warn} warning · {nit} nit  ",
        f"**Model:** `{MODEL}`",
        "",
        "### Walkthrough",
        "",
        "| File | Summary |",
        "| --- | --- |",
    ]
    for path, summary in per_file_summaries:
        lines.append(f"| `{path}` | {summary or '—'} |")
    lines += ["", "<sub>Automated review by a local open model. Verify before merging.</sub>"]
    body = "\n".join(lines)

    # find an existing sticky comment to update
    status, comments = gh_request("GET", f"/repos/{REPO}/issues/{pr_number}/comments?per_page=100")
    existing = None
    if status < 400 and isinstance(comments, list):
        existing = next((c for c in comments if MARKER in (c.get("body") or "")), None)

    if existing:
        gh_request("PATCH", f"/repos/{REPO}/issues/comments/{existing['id']}", {"body": body})
        print("  summary comment updated")
    else:
        gh_request("POST", f"/repos/{REPO}/issues/{pr_number}/comments", {"body": body})
        print("  summary comment created")


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main():
    with open(EVENT_PATH) as fh:
        event = json.load(fh)
    pr = event.get("pull_request")
    if not pr:
        print("Not a pull_request event; nothing to do.")
        return
    pr_number = pr["number"]
    head_sha = pr["head"]["sha"]

    status, diff = gh_request(
        "GET", f"/repos/{REPO}/pulls/{pr_number}",
        accept="application/vnd.github.v3.diff",
    )
    if status >= 400:
        print(f"Failed to fetch diff: HTTP {status}", file=sys.stderr)
        sys.exit(1)

    files = parse_unified_diff(diff)
    targets = [p for p in files if p.endswith(REVIEW_EXTS)][:MAX_FILES]
    if not targets:
        print("No reviewable files changed.")
        upsert_summary(pr_number, [], [], "COMMENT")
        return

    per_file_summaries, all_findings = [], []
    for path in targets:
        print(f"Reviewing {path} ...")
        result = review_file(path, files[path]["added"])
        per_file_summaries.append((path, result["summary"]))
        for f in result["findings"]:
            all_findings.append((path, f))

    has_blocking = any(f["severity"] == "blocking" for _, f in all_findings)
    if has_blocking:
        verdict = "REQUEST_CHANGES"
    elif all_findings:
        verdict = "COMMENT"
    else:
        verdict = "APPROVE" if ALLOW_APPROVE else "COMMENT"

    post_review(pr_number, head_sha, all_findings, verdict)
    upsert_summary(pr_number, per_file_summaries, all_findings, verdict)
    print(f"Done. Verdict: {verdict}, {len(all_findings)} inline comment(s).")


if __name__ == "__main__":
    main()
