# /run-plan — 승인된 plan 을 codex 로 headless(백그라운드) 실행

Claude 가 작성하고 **사용자가 승인한** plan(front matter `status: approved`)을
`scripts/codex_exec_plan.sh` 로 background 실행한다. `$ARGUMENTS` 가 있으면 plan 경로,
없으면 최신 approved plan 을 찾는다.

## 역할 (거버넌스)
- plan 작성·의논 = **Claude** (`/new-plan`). 승인 = **사용자**.
- 이 명령은 "승인된 plan 을 실행"만 한다.
- 실행 주체 = **codex exec**(workspace-write 샌드박스, 저장소 안에서만 수정).
  Claude 는 오케스트레이션·감시·검증만 한다. 직접 구현하지 않는다.
- approved 아닌 plan 은 하네스가 **거부**한다(강행은 `--force`, 비권장).

## 절차
1. **plan 결정**: `$ARGUMENTS` 있으면 그 경로. 없으면 `docs/plans/*/*.md` 중
   `status: approved` 인 최신 파일. 애매하면 사용자에게 확인.
2. **scope 브리핑**: plan 의 한 줄 결론 / 이번에 할 것 / 검증을 3~5줄로 사용자에게 요약.
   실행 전 git 스냅샷이 찍혀 롤백 지점이 생긴다는 점을 알린다.
3. **실행**: `scripts/codex_exec_plan.sh <plan>`.
   - ⚠ codex 는 모델 API **네트워크가 필요**하다. Claude 가 대신 실행할 때는 이 호출만
     샌드박스를 해제한다(아니면 사용자 터미널에서 직접 실행).
   - 하네스가 background PID + 로그 경로를 출력한다.
4. **감시 + 웹 브리지 서빙** (codex 종료까지 루프):
   - `scripts/codex_bridge_watch.sh <pid>` 를 background 로 실행해 codex 를 감시한다. 반환값이:
     - `REQUEST_PENDING <id>` → codex 가 웹 정보를 요청한 것. `.codex/bridge/requests/<id>.query`
       를 읽어 그 질의를 **WebSearch/WebFetch 또는 `researcher` 서브에이전트**로 처리하고(간단
       조회는 직접, 다출처·심층은 researcher), 출처 포함 결과를 `.codex/bridge/responses/<id>.answer`
       에 쓴다. 처리 불가면 `.codex/bridge/responses/<id>.error` 에 사유를 쓴다. 그다음 감시자를 재실행.
     - `CODEX_EXITED` → 루프 종료.
   - 병행해 `tail -n 40 <log>` 로 진행을 확인한다(로그 끝 "tokens used" = codex 종료).
5. **검증**: 완료 후
   - `git diff --stat <snapshot> HEAD` / `git status` 로 실제 변경 확인.
   - plan status 가 `done`(또는 `needs_revision`)으로 바뀌었는지 확인.
   - 오늘 worklog 에 codex 가 기록을 남겼는지 확인.
   - 핵심 결과를 사용자에게 요약. 문제 시 `git reset --hard <snapshot>` 롤백 안내.

## 실패 / 중단
- codex 가 범위 밖 이슈로 멈추면 plan status = `needs_revision`,
  worklog "해결해야 할 점"에 사유가 남는다 → Claude 가 사용자와 재계획(`/new-plan` 또는 기존 plan 갱신).
- 강제 중단: `kill <pid>`. 실행 전 상태 복구: `git reset --hard <snapshot>`.

## 참고
- 하네스: `scripts/codex_exec_plan.sh` — approved 게이트 / 실행 전 git 스냅샷 /
  self-contained 브리프 / `codex exec -s workspace-write` background / `.codex/runs/` 로그.
- 환경변수: `CODEX_EFFORT`(기본 high), `CODEX_SANDBOX`(기본 workspace-write), `CODEX_MODEL`.
- 로그·브리프는 `.codex/runs/` (gitignore 됨).
- **웹 브리지**: codex 는 네트워크가 없어 웹이 필요하면 `scripts/codex_ask_claude.sh '<질의>'` 로
  Claude 에 위임한다(응답까지 블록). Claude 는 위 4번처럼 `scripts/codex_bridge_watch.sh <pid>` 로
  요청을 감시·응답한다. 브리지 파일은 `.codex/bridge/{requests,responses}/` (gitignore). Claude 가
  감시 중이 아니면 codex 는 타임아웃(기본 1200s, `CLAUDE_BRIDGE_TIMEOUT`)까지 대기 후 실패한다.
