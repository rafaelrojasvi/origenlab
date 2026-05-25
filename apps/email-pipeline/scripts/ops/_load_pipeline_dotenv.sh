# Load apps/email-pipeline/.env into the current shell (safe quoting via Python dotenv).
# Usage: load_pipeline_dotenv "$PIPE_ROOT"
# Does nothing if .env is missing. Does not override variables already exported.

load_pipeline_dotenv() {
  local pipe_root="${1:?pipe_root required}"
  local env_file="${pipe_root}/.env"
  if [[ ! -f "$env_file" ]]; then
    return 0
  fi

  local exports
  if ! exports="$(
    cd "$pipe_root" && uv run python -c "
from dotenv import dotenv_values
import os
import shlex

for key, value in dotenv_values('.env').items():
    if not key or value is None:
        continue
    s = str(value).strip()
    if not s:
        continue
    if os.environ.get(key, '').strip():
        continue  # keep explicit shell exports
    print(f'export {key}={shlex.quote(s)}')
"
  )"; then
    echo "ERROR: failed to parse ${env_file}" >&2
    return 2
  fi

  if [[ -n "$exports" ]]; then
    # shellcheck disable=SC1090
    eval "$exports"
  fi
}
