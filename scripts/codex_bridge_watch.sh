#!/usr/bin/env bash
# codex_bridge_watch.sh — Claude(오케스트레이터) 측 브리지 감시자.
# headless codex 실행 중, codex 가 codex_ask_claude.sh 로 남긴 "처리 안 된 웹 질의"가
# 생기거나 codex 프로세스가 끝나면 즉시 반환한다. Claude 는 반환값을 보고:
#   - REQUEST_PENDING <id> → 그 질의를 WebSearch/WebFetch 또는 researcher 서브에이전트로 처리해
#     .codex/bridge/responses/<id>.answer 에 답을 쓰고, 이 감시자를 다시 실행한다.
#   - CODEX_EXITED        → codex 종료. 감시 종료.
#
# 사용법:
#   scripts/codex_bridge_watch.sh <codex_pid>     # codex 끝날 때까지 요청 감시(권장)
#   scripts/codex_bridge_watch.sh                 # PID 없이 1회 스캔만(수동 점검용)
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRIDGE="$REPO/.codex/bridge"
mkdir -p "$BRIDGE/requests" "$BRIDGE/responses"
PID="${1:-}"
INTERVAL=5

scan_pending() {
  for q in "$BRIDGE"/requests/*.query; do
    [ -e "$q" ] || continue
    local id; id="$(basename "$q" .query)"
    if [ ! -f "$BRIDGE/responses/${id}.answer" ] && [ ! -f "$BRIDGE/responses/${id}.error" ]; then
      echo "REQUEST_PENDING ${id}"
      echo "--- query ---"
      cat "$q"
      return 0
    fi
  done
  return 1
}

# PID 없으면 1회 스캔만.
if [ -z "$PID" ]; then
  scan_pending || echo "NO_PENDING"
  exit 0
fi

# PID 있으면 요청이 뜨거나 codex 가 끝날 때까지 루프.
while :; do
  scan_pending && exit 0
  if ! kill -0 "$PID" 2>/dev/null; then
    # 종료 직전에 막판 요청이 있었을 수 있으니 한 번 더 스캔.
    scan_pending && exit 0
    echo "CODEX_EXITED"
    exit 0
  fi
  sleep "$INTERVAL"
done
