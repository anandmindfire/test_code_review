# Local AI Code Review (Ollama + Qwen2.5-Coder)

Runs a local open model inside a GitHub-hosted runner to review changed Python
files on every push / PR to `main`. No API keys, no external calls — the model
runs on the runner itself.

## Layout

```
.github/workflows/ai-code-review.yml   # the CI job
scripts/review.sh                      # finds changed .py files, asks the model
src/example.py                         # sample file with intentional bugs
src/__init__.py                        # package marker for tests/imports
```

## How to try it

1. Create a new GitHub repo and copy these files in (keep the paths).
2. Push to `main`, or open a PR against `main`.
3. Open the run in the **Actions** tab and expand the "Run AI code review" step.
   Each reviewed file is a collapsible group.

## Why this differs from a naive `ollama run` setup

- **HTTP API instead of `ollama run`.** `ollama run` prints a spinner and ANSI
  escape codes that pollute captured output. The script POSTs to
  `/api/chat` with `stream:false` and pulls `.message.content` with `jq`.
- **`jq` builds the request body**, so code containing quotes/newlines is
  escaped correctly instead of breaking the JSON.
- **Model caching.** `actions/cache` stores `~/.ollama/models` so re-runs skip
  the ~4.4 GB download.
- **Install URL.** The script is `https://ollama.com/install.sh` (piping the
  bare domain `https://ollama.com` to `sh` won't work).
- **Health check has a timeout** so a failed daemon fails the job instead of
  hanging until the 20‑min limit.

## Notes on resources / speed

- Standard GitHub-hosted `ubuntu-latest` runners have 4 vCPUs and ~16 GB RAM,
  so the 4-bit 7B model (~4.4 GB) fits fine.
- Inference is **CPU-only** here, so expect roughly tens of seconds to a couple
  of minutes per file. Keep the set of reviewed files small, or switch to a
  smaller tag (e.g. `qwen2.5-coder:3b`) if runs feel slow.
- `q4_0` is a fine, small quant. `qwen2.5-coder:7b-instruct-q4_K_M` (~4.7 GB) is
  usually a slightly better quality/size tradeoff if you want to compare.

## Making it post PR comments (optional next step)

Right now results only appear in the Actions log. To surface them on the PR,
have `review.sh` write to a file and add a step using `actions/github-script`
or the `gh` CLI to post it as a comment. Ask if you want that wired up.
