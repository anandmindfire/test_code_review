# AI Code Review (CodeRabbit-style, local model)

A self-hosted PR reviewer that runs a local open model (Qwen2.5-Coder via
Ollama) inside a GitHub-hosted runner. On every pull request it:

- **Targets the diff** — parses the PR's unified diff and reviews only changed lines.
- **Posts inline comments** anchored to specific lines, tagged 🛑 blocking / ⚠️ warning / 💡 nit.
- **Posts a sticky summary** ("walkthrough") comment with a per-file table and a verdict. It is *updated in place* on each new push, not duplicated.
- **Approves / requests changes** — REQUEST_CHANGES if anything blocking, COMMENT otherwise, APPROVE when clean (see limitation below).

No API keys, no data leaves the runner.

## Layout

```
.github/workflows/ai-code-review.yml   # PR-triggered job
scripts/review.py                      # diff parsing, model calls, PR posting (stdlib only)
scripts/review.sh                      # older push-time log-only version (optional)
src/example.py                         # sample file with planted bugs
```

## Setup

1. Copy the files into your repo (keep paths).
2. Enable write-back: **Settings → Actions → General → Workflow permissions →
   "Read and write permissions."** (The workflow also declares
   `permissions: pull-requests: write`.)
3. Open a PR against `main` that changes a supported file
   (`.py .js .ts .tsx .jsx .go .rb .java .rs .c .cpp .h` by default — edit `REVIEW_EXTS`).
4. Watch the **Actions** tab; comments and the summary appear on the PR.

## Two limitations that matter in production

**1. Actions can't APPROVE by default.** The built-in `GITHUB_TOKEN` is blocked
from submitting *approving* reviews (a security measure so a workflow can't
approve its own code). REQUEST_CHANGES and COMMENT always work. To get real
APPROVE:
- Enable **Settings → Actions → General → "Allow GitHub Actions to create and
  approve pull requests,"** then set `ALLOW_APPROVE: "true"` in the workflow; **or**
- Post the review with a **PAT or GitHub App token** from a bot account instead
  of `GITHUB_TOKEN`.
The script attempts APPROVE and automatically falls back to COMMENT if it's
blocked, so it never fails the run.

**2. Fork PRs get a read-only token.** PRs from forked repos run with a
read-only `GITHUB_TOKEN` and can't post comments. This setup works for
same-repo (branch) PRs out of the box. Supporting fork PRs safely requires the
`pull_request_target` trigger with careful handling — it's deliberately not used
here because it runs with a write token and is easy to misconfigure into a
security hole.

## How inline anchoring stays valid

GitHub rejects the entire review (HTTP 422) if any inline comment points at a
line that isn't part of the diff. So `review.py`:
- parses each hunk to build the set of valid new-file line numbers,
- tells the model exactly which line numbers it may reference,
- keeps only findings on valid lines, **snapping** near-misses (±`SNAP_WINDOW`,
  default 2) to the closest changed line and dropping anything further,
- falls back to a summary-only review if a bad anchor still slips through.

## Tuning (env in the workflow)

| Variable | Default | Purpose |
| --- | --- | --- |
| `MODEL` | `qwen2.5-coder:7b-instruct-q4_0` | Ollama model tag |
| `REVIEW_EXTS` | common code extensions | which files to review |
| `MAX_FILES` | `20` | cap files per PR |
| `MAX_ADDED_LINES` | `400` | cap lines per file (bounds CPU time) |
| `SNAP_WINDOW` | `2` | line-number recovery window |
| `ALLOW_APPROVE` | `false` | allow APPROVE verdict (needs repo setting) |

## Performance

Standard `ubuntu-latest` runners are 4 vCPU / ~16 GB RAM, so the 4-bit 7B model
(~4.4 GB) fits comfortably. Inference is CPU-only: budget tens of seconds to a
couple of minutes per file. `actions/cache` keeps the model between runs so only
the first run pays the download. For faster/cheaper runs use a smaller tag
(`qwen2.5-coder:3b`) or a self-hosted GPU runner; for higher quality at similar
size try `qwen2.5-coder:7b-instruct-q4_K_M`.

## Known gaps vs. CodeRabbit (natural next steps)

- Re-reviews post a fresh review each run rather than incremental/threaded
  follow-ups. (The *summary* is deduped; inline reviews are not.)
- No "resolve on fix" tracking, no chat replies to comments, no config file for
  path filters. Ask if you want any of these wired up.
