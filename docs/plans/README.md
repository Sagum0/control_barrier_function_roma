# Plans

확정·공유 가능한 plan 은 모두 이 디렉토리에 저장한다.
Claude, codex, 기타 에이전트 모두 이 위치를 본다.

## 역할 (이 워크스페이스의 핵심 규칙)

| 단계 | 주체 | 산출물 |
|---|---|---|
| 의논·설계·plan 작성 | **Claude** (사용자와 대화) | `docs/plans/YYYY_MM/DD_PLANNN_topic.md` |
| 승인 | **사용자** | front matter `status: approved` |
| 구현 | **codex** (headless, `scripts/codex_exec_plan.sh`) | 코드 변경 + worklog |
| 확인·커밋 | **사용자 / Claude** | git diff 검토 후 커밋 |

- Claude 는 plan 을 쓰고, 코드는 쓰지 않는다. 구현은 승인된 plan 을 받은 codex 가 한다.
- Claude 의 파일 쓰기 권한은 기본적으로 **마크다운(`**/*.md`)으로 한정**한다.
  근거와 설정은 루트 `AGENTS.md` 의 "Claude 작성 권한" 절을 본다.
- 승인은 사람이 한다. Claude 가 자기 plan 을 스스로 approved 로 바꾸지 않는다.

## 명명 규칙

```
docs/plans/YYYY_MM/DD_PLANNN_topic.md
```

- `YYYY_MM` — 년_월 (zero-padded). 예: `2026_07`
- `DD` — 일 (zero-padded). 예: `17`
- `PLANNN` — 같은 날 plan 번호. 예: `PLAN01`, `PLAN02`
- `topic` — 짧은 영문 식별자 (snake_case). 예: `rag_schema`, `planner_v1`

전체 예: `docs/plans/2026_07/17_PLAN01_rag_schema.md`

## 메타데이터

plan 파일 상단에는 YAML front matter 를 둔다.

```yaml
---
date: 2026-07-17
task: 한 줄 요약
planner: Claude
executor: codex
status: draft
---
```

- `planner: Claude` — 설계·범위·검증·문서 업데이트 결정 주체.
- `executor: codex` — 승인 plan 기반 코드 작성·검증 주체.
- `status` 값:
  `draft | approved | in_progress | done | needs_revision | abandoned`
- 구현 시작 조건은 `status: approved` 이다. 하네스(`scripts/codex_exec_plan.sh`)가
  이 값을 검사해 아니면 실행을 거부한다(`--force` 로 강행 가능하나 비권장).
- 구버전 워크스페이스에서 옮겨온 plan 의 `codex_approved` 도 하네스가 함께 허용한다.

## 작성 원칙 — reader-first

plan 은 **사용자가 바로 읽고 이해할 수 있는** 형식으로 쓴다.

- 첫 화면에서 **한 줄 결론**이 보여야 한다.
- "왜 이 작업을 하나"보다 먼저 "그래서 지금 뭘 하기로 했는가"가 보여야 한다.
- 구현 세부는 뒤로 보내고, 판단/우선순위/다음 액션을 앞에 둔다.
- 긴 bullet 나열보다 "지금 상태 -> 이번 판단 -> 다음 단계" 흐름을 우선한다.
- **다른 plan 파일을 읽지 않아도 이해 가능해야 한다.**
  구현 우선순위, 선행 조건, 이어지는 로직은 해당 plan 안에 다시 적는다.
- 이전 결정이 중요하면 "이전 PLAN05를 보라"가 아니라,
  그 핵심 내용을 3~6줄로 현재 plan 안에 재서술한다.
- 다음 작업도 "PLAN02 재개"처럼 번호만 쓰지 말고,
  "planner V1 구현 재개"처럼 사람이 바로 이해되는 문장으로 먼저 적는다.

self-contained 원칙은 취향이 아니다. codex 는 **stateless** 로 실행되며 하네스가 넘기는
브리프에는 이 plan 전문만 들어간다. plan 이 다른 문서를 참조만 하면 실행자는 그 맥락을 못 본다.

## 권장 섹션

- **한 줄 결론** — 이 plan 의 핵심 판단을 2~4줄로 먼저 쓴다
- **왜 이 plan 이 필요한가** — 질문, 배경, 문제 상황
- **지금까지 이어진 맥락** — 이미 확정된 사실 / 선행 완료 사항
- **지금 기준 판단** — 현재 구조/코드/문서 기준으로 무엇을 결정했는지
- **이번에 할 것** — 이번 작업 범위
- **구현해야 할 것** — 실행자가 실제로 손대야 하는 변경점
- **참고해야 할 것** — 스키마, JSON, 계약 문서, 기존 코드, 상수, 설정 파일
- **신경써야 할 것** — 가드레일, 금지사항, 호환성, 실패 조건, 놓치기 쉬운 포인트
- **이번에는 하지 않는 것** — non-scope / 나중으로 미루는 것
- **근거** — 관련 코드, 문서, 전제
- **검증** — 무엇으로 맞는지 확인할지
- **다음 단계** — 이 plan 다음에 이어질 작업

## codex handoff 기준

codex 로 넘길 plan 은 아래 3가지를 **구체적으로** 포함해야 한다.

- **구현해야 할 것**
  파일/모듈 수준으로 무엇을 바꾸는지 적는다.
  "수집기 개선"처럼 뭉뚱그리지 말고, 어떤 입력을 받고 어떤 출력을 내도록
  바꾸는지까지 적는다.
- **참고해야 할 것**
  단순 링크 나열이 아니라 왜 봐야 하는지 함께 적는다.
  예: `api_schema.md` — request field shape 확인,
  `contract.md` — request_id/status 제약 확인.
- **신경써야 할 것**
  구현자가 실수하기 쉬운 제약을 적는다.
  예: vendor 디렉토리 수정 금지, 기존 스키마 호환 유지, 특정 플래그 기본값 유지.

이 3개가 빠진 plan 은 handoff 품질이 낮다고 보고 보강한다.

## 갱신 규칙

- 같은 plan 을 여러 번 수정해야 하면 **같은 파일을 갱신**한다.
  새 plan 번호를 끊지 않는다 (단, 주제가 완전히 바뀌면 새 파일).
- plan 이 종료되면 `status: done` 또는 `abandoned` 로 표시하고 본문은 그대로 둔다.
- plan 파일은 git 으로 추적된다.
- 구현 중 plan 에 없는 파일·범위·설계 결정이 필요해지면 구현을 중단하고
  `status: needs_revision` 으로 되돌린 뒤 Claude 가 사용자와 재계획한다.

## `.claude/plans/` 와의 관계

- `.claude/plans/`(프로젝트) 및 `~/.claude/plans/`(전역, Plan Mode 빌트인이 자동 생성)는
  임시·탐색용 scratch space 다. **확정 plan 은 작성하지 않는다.**
- 실행 승인 근거는 `docs/plans/` 의 `approved` plan 뿐이다.

## docs/memory.md 와의 관계

- [docs/memory.md](../memory.md) 는 "지금 어디에 있는지" 추적.
- plan 파일은 "어떻게 갈 것인지" 설계.
- plan 이 완료되면 결정 사항을 memory.md 의 `Recent decisions` 에 반영하고,
  plan 파일은 done 상태로 남긴다.

## 강제 메커니즘 (선택)

status 게이트는 `scripts/codex_exec_plan.sh` 가 강제한다 — approved 가 아니면 실행 거부.

plan 없이 코드가 편집되는 것까지 막고 싶으면 `Edit/Write` 에 PreToolUse hook 을 걸어
plan 존재를 검사할 수 있다. 이 템플릿은 hook 을 포함하지 않는다. 기본 설정은
Claude 의 무프롬프트 쓰기를 `**/*.md` 로만 열어 두는 방식(`.claude/settings.local.json`)이라,
코드 파일 편집은 그때그때 사용자 승인을 거치게 된다.
