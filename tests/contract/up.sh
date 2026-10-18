#!/usr/bin/env bash
# Bring up one seeded qBittorrent container and probe its auth behaviour.
#
#   up.sh <image-tag> <port>      e.g. up.sh 5.1.2-1 18081
#
# The port is used *both* inside and outside the container on purpose:
# validateHostHeader is on by default and rejects any request whose Host header
# carries a port different from the listening port, with a bare 401 that looks
# exactly like bad credentials.
#
# Fixtures live under $HOME because the podman machine on macOS does not mount
# /tmp into the VM.
set -euo pipefail

# podman locally, docker on CI runners that have no podman. Every command below
# is spelled the same in both.
RUNTIME="${QBT_CONTAINER_RUNTIME:-}"
if [ -z "$RUNTIME" ]; then
  for exe in podman docker; do
    if command -v "$exe" >/dev/null 2>&1; then RUNTIME="$exe"; break; fi
  done
fi
: "${RUNTIME:?no container runtime found: install podman or docker, or set QBT_CONTAINER_RUNTIME}"

TAG="${1:?usage: up.sh <image-tag> <port>}"
PORT="${2:?usage: up.sh <image-tag> <port>}"
NAME="qbt-${TAG%%-*}"
NAME="${NAME//./}"
DIR="$HOME/.cache/qbt-harness/$PORT"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE="docker.io/qbittorrentofficial/qbittorrent-nox:$TAG"

rm -rf "$DIR"
mkdir -p "$DIR/config/qBittorrent/config" "$DIR/downloads"
python3 -I "$HERE/seed_config.py" \
  --out "$DIR/config/qBittorrent/config/qBittorrent.conf" \
  --port "$PORT" --username testuser --password testpass123 \
  --salt-hex 00112233445566778899aabbccddeeff >/dev/null

"$RUNTIME" rm -f "$NAME" >/dev/null 2>&1 || true
"$RUNTIME" run -d --name "$NAME" \
  -e QBT_LEGAL_NOTICE=confirm -e QBT_EULA=accept \
  -e "QBT_WEBUI_PORT=$PORT" -e PUID=0 -e PGID=0 \
  -p "127.0.0.1:$PORT:$PORT" \
  -v "$DIR/config:/config" -v "$DIR/downloads:/downloads" \
  "$IMAGE" >/dev/null

for _ in $(seq 1 60); do
  code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 \
    "http://127.0.0.1:$PORT/api/v2/app/version" 2>/dev/null || true)
  [ "$code" != "000" ] && break
  sleep 1
done
if [ "${code:-000}" = "000" ]; then
  echo "  $TAG: WebUI never came up" >&2
  "$RUNTIME" logs "$NAME" 2>&1 | tail -8 >&2
  exit 1
fi

echo "=== $TAG  (container $NAME, port $PORT)"
python3 -I "$HERE/probe_auth.py" --url "http://127.0.0.1:$PORT" \
  -u testuser -p testpass123
