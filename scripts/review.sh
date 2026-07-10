#!/usr/bin/env bash
#
# Reviews changed Python files using a local Ollama model.
# Uses the HTTP API (/api/chat) with stream:false so we get clean output
# instead of the spinner/escape-code noise that `ollama run` prints.

set -euo pipefail

MODEL="qwen2.5-coder:7b-instruct-q4_0"
API="http://localhost:11434/api/chat"

# --- Figure out which files to review --------------------------------------
if [ "${GITHUB_EVENT_NAME:-}" = "pull_request" ]; then
  git fetch origin "${GITHUB_BASE_REF}" --depth=1
  FILES=$(git diff --name-only "origin/${GITHUB_BASE_REF}...HEAD" -- '*.py')
else
  # On push: files changed in the last commit; fall back to all .py files.
  FILES=$(git diff --name-only HEAD~1 HEAD -- '*.py' 2>/dev/null || git ls-files '*.py')
fi

if [ -z "${FILES}" ]; then
  echo "No Python files to review. Done."
  exit 0
fi

# --- Review each file -------------------------------------------------------
for file in ${FILES}; do
  [ -f "${file}" ] || continue
  echo "::group::Review: ${file}"

  CODE=$(cat "${file}")
  PROMPT=$(printf 'Review this Python code for bugs, edge cases, and optimization opportunities. Be concise and specific, and use bullet points. File: %s\n\n%s' "${file}" "${CODE}")

  # Build the JSON body with jq so quotes/newlines in the code are escaped safely.
  BODY=$(jq -n --arg model "${MODEL}" --arg content "${PROMPT}" \
    '{model: $model, stream: false, messages: [{role: "user", content: $content}]}')

  RESPONSE=$(curl -s "${API}" -d "${BODY}" | jq -r '.message.content // "No response from model."')
  echo "${RESPONSE}"
  echo "::endgroup::"
done
