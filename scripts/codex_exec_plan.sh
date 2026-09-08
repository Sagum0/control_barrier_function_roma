#!/usr/bin/env bash
# codex_exec_plan.sh — 승인된(approved) plan 을 codex 로 headless(백그라운드) 실행한다.
#
# 거버넌스(역할 분담):
#   - plan 은 Claude 가 사용자와 의논해 작성한다(docs/plans/YYYY_MM/DD_PLANNN_topic.md).
#   - 사용자가 승인하면 front matter 를 status: approved 로 바꾼다. 승인 주체는 사람이다.
#   - 이 스크립트는 그 승인된 plan 을 codex exec 로 background 실행하는 "실행 하네스"다.
#   - codex 는 workspace-write 샌드박스로 저장소 안에서만 파일을 수정한다(밖은 못 건드림).
#   - 실행 전 git 스냅샷을 찍어 롤백 지점을 남긴다.
#
# 사용법:
#   scripts/codex_exec_plan.sh docs/plans/2026_07/17_PLAN01_topic.md
#   scripts/codex_exec_plan.sh --force <plan.md>      # approved 아니어도 강행(비권장)
#
# 환경변수(선택):
#   CODEX_EFFORT   : model_reasoning_effort (기본 high)
#   CODEX_SANDBOX  : read-only|workspace-write|danger-full-access (기본 workspace-write)
#   CODEX_MODEL    : 모델 강제 (기본: ~/.codex/config.toml 값)
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

FORCE=0
PLAN=""
for a in "$@"; do
  case "$a" in
    --force) FORCE=1 ;;
    -*) echo "unknown option: $a" >&2; exit 2 ;;
    *)  PLAN="$a" ;;
  esac
done

# --- plan 확인 ---
if [ -z "$PLAN" ]; then
  {
    echo "usage: scripts/codex_exec_plan.sh [--force] <docs/plans/YYYY_MM/DD_PLANNN_topic.md>"
    echo "후보 plan:"
    ls -1 docs/plans/*/*.md 2>/dev/null | sed 's/^/  /' || echo "  (없음)"
  } >&2
  exit 2
fi
[ -f "$PLAN" ] || { echo "plan 파일 없음: $PLAN" >&2; exit 2; }

# --- 거버넌스 게이트: approved 필수 ---
# codex_approved 는 구버전 워크스페이스 호환용으로 함께 허용한다.
if ! grep -Eq '^status:[[:space:]]*(approved|codex_approved)' "$PLAN"; then
  if [ "$FORCE" -ne 1 ]; then
    {
      echo "거부: '$PLAN' 의 status 가 approved 가 아닙니다."
      echo "      사용자 승인 후 status: approved 로 바꾸거나, 정말 강행하려면 --force 를 붙이세요."
    } >&2
    exit 3
  fi
  echo "경고: approved 아님 — --force 로 강행합니다." >&2
fi

# --- 안전망: 실행 전 git 스냅샷(롤백 지점) ---
# 대용량 산출물이 있다면 .gitignore 로 먼저 제외해 둘 것(스냅샷이 비대해진다).
if [ ! -d .git ]; then
  echo "git repo 아님 → 롤백용 최초 스냅샷 생성(git init)…" >&2
  git init -q
  git add -A && git commit -q -m "chore: codex 실행 전 스냅샷 (plan: $(basename "$PLAN"))" || true
elif [ -n "$(git status --porcelain 2>/dev/null)" ]; then
  git add -A && git commit -q -m "chore: codex 실행 전 스냅샷 (plan: $(basename "$PLAN"))" || true
fi
SNAP="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"

# --- 실행 로그 위치 (.codex 는 .gitignore 됨) ---
TS="$(date +%Y%m%d_%H%M%S)"
TODAY="$(date +%Y-%m-%d)"
SLUG="$(basename "$PLAN" .md)"
RUNDIR="$REPO/.codex/runs"
mkdir -p "$RUNDIR"
LOG="$RUNDIR/${TS}_${SLUG}.log"
BRIEF="$RUNDIR/${TS}_${SLUG}.brief.md"

# --- self-contained 실행 브리프 (codex 는 stateless — 필요한 맥락을 전부 담는다) ---
cat > "$BRIEF" <<BRIEF_EOF
# Codex headless 실행 브리프 — $(basename "$PLAN")

너는 이 저장소($REPO)의 백그라운드 실행자(executor)다. 아래 승인된 plan 을 그대로 실행한다.

## 반드시 지킬 규칙
- 저장소 루트의 AGENTS.md / CLAUDE.md 규칙을 따른다. 특히 "Do Not Modify" 목록과
  주석·커밋 메시지 언어 규칙을 그대로 지킨다.
- plan 의 goal / scope / execution steps 범위 안에서만 작업한다. 임의 확장 금지.
- plan 에 없는 파일·설계 결정이 필요해지면 즉시 중단하고, 이유를
  docs/worklog/${TODAY}.md 의 "해결해야 할 점"에 적은 뒤 plan 의 status 를
  needs_revision 으로 바꾼다. 스스로 판단해서 범위를 넓히지 마라.
- 웹 검색·인터넷 자료가 필요하면 **직접 접속하지 마라(이 샌드박스는 네트워크 없음)**. 대신
  scripts/codex_ask_claude.sh '<질의>' 를 실행하면 Claude 가 검색해 결과를 stdout 으로 돌려준다
  (응답까지 블록). 그 결과를 근거로 쓰고 인용 출처를 남겨라. 여러 건이면 질의를 나눠 각각 호출.
- 파일 이동은 일반 mv/mkdir 로 한다. **git 명령(add/mv/commit/init 등)은 절대 실행하지 마라**
  — 이 환경에서 codex 는 .git 을 못 쓴다(read-only). git init/스냅샷은 하네스가 이미 실행했고,
  작업 완료 후 커밋도 하네스 밖(사용자/Claude)이 담당한다. 너는 작업트리 파일만 다룬다.
- 작업 완료 시 docs/worklog/${TODAY}.md 에 변경 요약·검증 결과를 남기고,
  plan 의 status 를 done 으로 바꾼다.
- 되돌리기 스냅샷: git 커밋 ${SNAP} (문제가 생기면 여기로 reset 가능).

## 실행할 plan (전문)
$(cat "$PLAN")
BRIEF_EOF

# --- codex 실행 (background, detached; 브리프는 stdin 으로 전달해 ARG 길이 제한 회피) ---
MODEL_ARG=()
[ -n "${CODEX_MODEL:-}" ] && MODEL_ARG=(-m "$CODEX_MODEL")

echo "plan     : $PLAN"
echo "snapshot : git $SNAP"
echo "log      : $LOG"
echo "brief    : $BRIEF"
echo "codex    : sandbox=${CODEX_SANDBOX:-workspace-write} effort=${CODEX_EFFORT:-high} model=${CODEX_MODEL:-<config>}"

nohup codex exec \
  --skip-git-repo-check \
  -s "${CODEX_SANDBOX:-workspace-write}" \
  -c model_reasoning_effort="${CODEX_EFFORT:-high}" \
  "${MODEL_ARG[@]}" \
  - < "$BRIEF" > "$LOG" 2>&1 &

PID=$!
echo "$PID" > "$RUNDIR/${TS}_${SLUG}.pid"
echo "started  : codex pid=$PID (background)"
echo
echo "진행 보기 : tail -f $LOG"
echo "중단      : kill $PID"
echo "롤백      : git reset --hard $SNAP"
echo
echo "웹 브리지 : codex 가 웹 필요시 scripts/codex_ask_claude.sh 로 질의 → Claude 가 응답."
echo "감시(권장): scripts/codex_bridge_watch.sh $PID  # 실행 중 요청을 감지→응답→재감시"
