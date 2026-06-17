#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

ORIGENLAB_API_BASE_URL="${ORIGENLAB_API_BASE_URL:-https://api.origenlab.cl}"
BASE_URL="${ORIGENLAB_API_BASE_URL%/}"

body_file="$(mktemp)"
headers_file="$(mktemp)"
cleanup() {
  rm -f "$body_file" "$headers_file"
}
trap cleanup EXIT

curl_common=(curl -sS --max-time 30)

header_value() {
  local file="$1"
  local name="$2"
  awk -v name="$name" '
    BEGIN { IGNORECASE = 1 }
    $1 ~ (name ":") {
      sub(/^[^:]*:[[:space:]]*/, "")
      gsub(/\r$/, "")
      print
      exit
    }
  ' "$file"
}

echo "remote smoke: ${BASE_URL}"

# --- Check A: unauthenticated protection ---
status_a="$("${curl_common[@]}" -o "$body_file" -D "$headers_file" -w "%{http_code}" "${BASE_URL}/health")"
echo "check A: unauthenticated /health -> HTTP ${status_a}"

case "$status_a" in
  200)
    echo "ok: unauthenticated /health returned 200 (public or local dev)"
    ;;
  302|401|403)
    if [[ "$status_a" == "302" ]]; then
      location="$(header_value "$headers_file" "Location")"
      if [[ "$location" == *cloudflareaccess.com* ]]; then
        echo "ok: Cloudflare Access protects unauthenticated /health"
      else
        echo "ok: unauthenticated /health is protected (HTTP ${status_a})"
      fi
    else
      echo "ok: unauthenticated /health is protected (HTTP ${status_a})"
    fi
    ;;
  *)
    echo "error: unexpected unauthenticated /health status: ${status_a}" >&2
    exit 1
    ;;
esac

# --- Check B: authenticated health (optional without secrets) ---
if [[ -z "${CF_ACCESS_CLIENT_ID:-}" || -z "${CF_ACCESS_CLIENT_SECRET:-}" ]]; then
  echo "skip: authenticated /health (set CF_ACCESS_CLIENT_ID and CF_ACCESS_CLIENT_SECRET)"
  exit 0
fi

status_b="$("${curl_common[@]}" -o "$body_file" -D "$headers_file" -w "%{http_code}" \
  -H "CF-Access-Client-Id: ${CF_ACCESS_CLIENT_ID}" \
  -H "CF-Access-Client-Secret: ${CF_ACCESS_CLIENT_SECRET}" \
  "${BASE_URL}/health")"

if [[ "$status_b" != "200" ]]; then
  echo "error: authenticated /health expected HTTP 200, got ${status_b}" >&2
  exit 1
fi

request_id_b="$(header_value "$headers_file" "X-Request-ID")"
if [[ -z "$request_id_b" ]]; then
  echo "error: authenticated /health missing X-Request-ID response header" >&2
  exit 1
fi

python3 - "$body_file" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    data = json.load(handle)
if data.get("ok") is not True:
    raise SystemExit("error: authenticated /health JSON missing ok:true")
PY

echo "ok: authenticated /health returned 200 with x-request-id"

# --- Optional operator check ---
if [[ "${ORIGENLAB_REMOTE_SMOKE_OPERATOR:-}" != "1" ]]; then
  exit 0
fi

status_op="$("${curl_common[@]}" -o "$body_file" -D "$headers_file" -w "%{http_code}" \
  -H "CF-Access-Client-Id: ${CF_ACCESS_CLIENT_ID}" \
  -H "CF-Access-Client-Secret: ${CF_ACCESS_CLIENT_SECRET}" \
  "${BASE_URL}/operator/status")"

echo "check C: authenticated /operator/status -> HTTP ${status_op}"

if [[ "$status_op" == "302" ]]; then
  echo "error: /operator/status returned redirect (expected JSON API response)" >&2
  exit 1
fi

request_id_op="$(header_value "$headers_file" "X-Request-ID")"
if [[ -z "$request_id_op" ]]; then
  echo "error: /operator/status missing X-Request-ID response header" >&2
  exit 1
fi

python3 - "$body_file" "$status_op" <<'PY'
import json
import sys

body_path, status_text = sys.argv[1], sys.argv[2]
status = int(status_text)
with open(body_path, encoding="utf-8") as handle:
    raw = handle.read()

stripped = raw.lstrip()
if stripped.startswith("<"):
    raise SystemExit("error: /operator/status returned HTML, not JSON")

try:
    data = json.loads(raw)
except json.JSONDecodeError as exc:
    raise SystemExit(f"error: /operator/status response is not JSON: {exc}") from exc

if status == 200:
    sys.exit(0)
if isinstance(data.get("error"), dict):
    sys.exit(0)
raise SystemExit(
    f"error: /operator/status HTTP {status} without documented error envelope"
)
PY

echo "ok: authenticated /operator/status returned API JSON with x-request-id"
