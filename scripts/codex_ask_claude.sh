#!/usr/bin/env bash
# codex_ask_claude.sh — headless codex(네트워크 없는 workspace-write 샌드박스)가 웹 검색·
# 인터넷 자료가 필요할 때 호출한다. 질의를 파일 브리지로 Claude 에 넘기고, Claude 가 검색해
# 써 준 응답을 받아 stdout 으로 출력한다(응답까지 블록).
#
# 사용법 (codex 실행 브리프가 안내):
#   ans="$(scripts/codex_ask_claude.sh '2026년 기준 FAISS 최신 안정 버전과 GPU 인덱스 지원?')"
#
# 동작:
#   1) .codex/bridge/requests/<id>.query 에 질의를 쓴다.
#   2) .codex/bridge/responses/<id>.answer 가 생길 때까지 폴링 대기(기본 1200s).
#   3) 응답 본문을 stdout 으로 출력. 타임아웃/취소 시 비정상 종료코드.
#
# 전제: Claude(오케스트레이터)가 scripts/codex_bridge_watch.sh 로 요청을 감시·응답 중이어야 한다.
# 그렇지 않으면 타임아웃까지 대기 후 실패한다.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRIDGE="$REPO/.codex/bridge"
mkdir -p "$BRIDGE/requests" "$BRIDGE/responses"

QUERY="$*"
[ -n "${QUERY// /}" ] || { echo "usage: $(basename "$0") <웹 질의>" >&2; exit 2; }

ID="req_$(date +%Y%m%d_%H%M%S)_$$_${RANDOM}"
REQ="$BRIDGE/requests/${ID}.query"
RESP="$BRIDGE/responses/${ID}.answer"
ERR="$BRIDGE/responses/${ID}.error"

printf '%s\n' "$QUERY" > "$REQ"
echo "[bridge] Claude 에 웹 질의 전송: $ID — 응답 대기…" >&2

TIMEOUT="${CLAUDE_BRIDGE_TIMEOUT:-1200}"
INTERVAL=5
waited=0
while [ ! -f "$RESP" ]; do
  # Claude 가 처리 불가로 표시하면 즉시 실패
  if [ -f "$ERR" ]; then
    echo "[bridge] Claude 가 처리 불가로 응답: $(cat "$ERR")" >&2
    exit 5
  fi
  sleep "$INTERVAL"
  waited=$((waited + INTERVAL))
  if [ "$waited" -ge "$TIMEOUT" ]; then
    echo "[bridge] 타임아웃 ${TIMEOUT}s — Claude 응답 없음(오케스트레이터가 감시 중인지 확인)." >&2
    exit 4
  fi
done

cat "$RESP"
