#!/usr/bin/env bash
# Deploy the committed code (git HEAD) to the server. Run from anywhere inside the repo:
#
#   ./deploy/deploy.sh
#
# First run: installs Docker, creates the server .env with random secrets, copies the active AI
# provider keys from your LOCAL database (or from SEED_*_API_KEY env vars), builds, migrates and
# seeds the demo data once.
# Later runs: ship new code, back up the database, run migrations, restart. Server data, the .env
# and the seed are left alone.
#
# Overrides: SERVER_HOST, SERVER_PORT, SERVER_USER, PUBLIC_DOMAIN, ALLOW_DIRTY=1
set -Eeuo pipefail

SERVER_HOST="${SERVER_HOST:-59.153.246.116}"
SERVER_PORT="${SERVER_PORT:-234}"
SERVER_USER="${SERVER_USER:-stackops}"
PUBLIC_DOMAIN="${PUBLIC_DOMAIN:-59-153-246-116.sslip.io}"   # used only when the server .env is created

REPO="$(git rev-parse --show-toplevel)"
cd "$REPO"

log()  { printf '\n\033[1;32m>>> %s\033[0m\n' "$*"; }
die()  { printf '\033[1;31mxx  %s\033[0m\n' "$*" >&2; exit 1; }

SSH_OPTS=(-p "$SERVER_PORT" -o ConnectTimeout=15 -o ServerAliveInterval=30 -o StrictHostKeyChecking=accept-new)
remote() { ssh "${SSH_OPTS[@]}" "$SERVER_USER@$SERVER_HOST" "$@"; }

# ---------------------------------------------------------------------------
log "Kiểm tra code sẽ deploy"
if [[ -n "$(git status --porcelain)" && "${ALLOW_DIRTY:-0}" != "1" ]]; then
  git status --short
  die "Còn thay đổi chưa commit. Script chỉ deploy commit HEAD — commit trước, hoặc ALLOW_DIRTY=1 để bỏ qua các thay đổi đó."
fi
REV="$(git rev-parse --short HEAD)"
echo "Commit: $REV  $(git log -1 --pretty=%s)"
if git rev-parse --abbrev-ref '@{u}' >/dev/null 2>&1 && [[ -n "$(git log '@{u}..HEAD' --oneline)" ]]; then
  echo "Lưu ý: commit này chưa push lên GitHub."
fi

remote true || die "Không SSH được tới $SERVER_USER@$SERVER_HOST:$SERVER_PORT"

# ---------------------------------------------------------------------------
log "Đóng gói commit $REV và gửi lên server"
TMP="$(mktemp -t querion-deploy.XXXXXX)"
trap 'rm -f "$TMP"' EXIT
git archive --format=tar.gz -o "$TMP" HEAD
remote "mkdir -p ~/querion"
scp -q -P "$SERVER_PORT" -o StrictHostKeyChecking=accept-new "$TMP" "$SERVER_USER@$SERVER_HOST:querion/incoming.tar.gz"
scp -q -P "$SERVER_PORT" -o StrictHostKeyChecking=accept-new deploy/remote.sh "$SERVER_USER@$SERVER_HOST:querion/remote.sh"
echo "$(du -h "$TMP" | cut -f1) đã gửi"

# ---------------------------------------------------------------------------
provider_env() {
  # Prints SEED_* lines for the first deploy. Never echoed to the terminal: piped straight to ssh.
  if [[ -n "${SEED_LLM_API_KEY:-}" || -n "${SEED_EMBEDDING_API_KEY:-}" ]]; then
    env | grep -E '^SEED_(LLM|EMBEDDING)_(PROVIDER|MODEL|BASE_URL|API_KEY)=' || true
    return
  fi
  # Copy the active providers from the local database (decrypted with the local ENCRYPTION_KEY).
  local py=python3
  [[ -x apps/api/.venv/bin/python ]] && py=apps/api/.venv/bin/python   # has `cryptography`
  [[ -f .env ]] || return 0
  "$py" - <<'PY'
import subprocess, sys
from pathlib import Path

key = next((l.split("=", 1)[1].strip() for l in Path(".env").read_text().splitlines()
            if l.startswith("ENCRYPTION_KEY=")), "")
if not key:
    sys.exit(0)
from cryptography.fernet import Fernet
q = ("select purpose, provider_name, model_name, coalesce(base_url,''), api_key_encrypted "
     "from ai_providers where is_active order by created_at")
try:
    out = subprocess.run(["docker", "exec", "querion-postgres", "psql", "-U", "querion", "-d", "querion",
                          "-At", "-F", "\t", "-c", q], capture_output=True, text=True, check=True).stdout
except Exception:
    sys.exit(0)
seen = set()
for line in out.splitlines():
    purpose, provider, model, base_url, enc = line.split("\t")
    if purpose in seen:
        continue
    seen.add(purpose)
    prefix = "SEED_LLM" if purpose == "llm" else "SEED_EMBEDDING"
    print(f"{prefix}_PROVIDER={provider}")
    print(f"{prefix}_MODEL={model}")
    if base_url:
        print(f"{prefix}_BASE_URL={base_url}")
    print(f"{prefix}_API_KEY={Fernet(key.encode()).decrypt(enc.encode()).decode()}")
PY
}

if remote "test -f ~/querion/shared/.env"; then
  log "Server đã có .env — giữ nguyên (không đổi secret, không đổi dữ liệu)"
else
  log "Lần deploy đầu: tạo .env trên server, domain $PUBLIC_DOMAIN"
  provider_env | remote "bash ~/querion/remote.sh init-env '$PUBLIC_DOMAIN'"
fi

# ---------------------------------------------------------------------------
log "Deploy trên server"
remote "bash ~/querion/remote.sh deploy"

log "Xong: commit $REV đã chạy trên server"
