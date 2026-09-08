# AGENTS.md — cbf_ws

Claude, codex 등 모든 코딩 에이전트가 같은 규칙에서 시작한다.

## First Read Order

1. 모든 세션은 루트 `docs/memory.md` 를 먼저 읽는다 — 지금 어디에 있는지.
2. 이 파일(`AGENTS.md`) — 역할·권한·가드레일.
3. `docs/plans/README.md` — plan 형식과 status 규칙.
4. 아키텍처·데이터 흐름은 `docs/overview.md`.

단일 프로젝트 워크스페이스다 — 하위 `projects/` 분리 구조는 쓰지 않는다.

## Agent Roles And Workflow

이 워크스페이스는 **기획과 구현을 분리**한다.

| 단계 | 주체 | 산출물 |
|---|---|---|
| 의논·설계·plan 작성 | **Claude** (사용자와 대화, `/new-plan`) | `docs/plans/YYYY_MM/DD_PLANNN_topic.md` (`status: draft`) |
| 승인 | **사용자** | `status: approved` |
| 구현 | **codex** (headless, `/run-plan`) | 코드 변경 + worklog + `status: done` |
| 확인·커밋 | **사용자 / Claude** | git diff 검토 후 커밋 |

- Claude 는 plan 을 쓰고 코드는 쓰지 않는다. 구현은 승인된 plan 을 받은 codex 가 한다.
- 승인은 사람이 한다. Claude 가 자기 plan 을 스스로 approved 로 바꾸지 않는다.
- codex 는 `status: approved` 인 plan 만 실행한다(하네스가 강제).
- 범위 밖 결정이 필요하면 해당 worklog 의 "해결해야 할 점"에 기록하고 plan status 를
  `needs_revision` 으로 바꾼 뒤 중단한다. 스스로 범위를 넓히지 않는다.
- 동작·스키마·구조 변경 시 관련 문서를 같은 변경셋에서 동기화한다.

## Claude 작성 권한 (마크다운 한정)

**Claude 가 프롬프트 없이 쓸 수 있는 파일은 마크다운뿐이다.** 위 역할 분담을 설정으로
뒷받침한 것이며, `.claude/settings.local.json` 의 allow 목록이 근거다.

- 자동 허용(무프롬프트): `Edit(**/*.md)`, `Write(**/*.md)`, `Edit/Write(**/*.markdown)`,
  `Read` / `Glob` / `Grep`, 읽기 전용 bash(`ls`, `find`, `grep`, `rg`, `git status|diff|log|show` 등),
  그리고 codex 하네스 실행(`scripts/codex_exec_plan.sh`, `scripts/codex_bridge_watch.sh`).
- 따라서 Claude 가 스스로 쓰는 대상은 사실상 이것들이다:
  `docs/plans/**`, `docs/worklog/**`, `docs/memory.md`, `docs/overview.md`, `AGENTS.md`, `CLAUDE.md`.
- **코드 파일(.py/.sh/.ts/…)은 allow 목록에 없다.** 금지(deny)는 아니라 매번 사용자 승인을
  요구하는 상태다. 즉 기본 경로는 "Claude 가 plan 을 쓰고 codex 가 구현한다"이고,
  사용자가 명시적으로 승인할 때만 Claude 가 코드에 직접 손댄다.
- 이 경계를 더 세게 걸려면 `.claude/settings.local.json` 에 deny 규칙을 추가한다
  (예: `"deny": ["Edit(**/*.py)", "Write(**/*.py)"]`). 기본값은 allow-only 다.
- `.claude/settings.local.json` 은 개인 설정이라 git 추적 대상이 아니다. 팀과 공유하려면
  같은 내용을 `.claude/settings.json` 에 두고 추적한다.

## Project Routing

| 범위 | memory | worklog | plan |
|---|---|---|---|
| 전체(단일 프로젝트) | `docs/memory.md` | `docs/worklog/` | `docs/plans/` |

## Workspace Snapshot

- **ZED-M 2대를 ZED SDK Fusion 으로 묶어 가림에 강한 단일 휴먼 스켈레톤을 뽑는 인지 파이프라인.**
  이후 로봇 안전층(CBF)의 입력으로 쓰는 것이 목표. 현재는 라이브 뷰어까지 동작하고,
  **ZED360 실측 캘리브로 분리된 두 스켈레톤(id0/id1)을 하나로 합치는 단계**.
- 핵심 제약:
  - ZED-M **2대**(S/N `13870389`, `19321109`), SDK **5.4**, pyzed 는 conda `zed` env, **GPU 필요**.
  - USB 컨트롤러가 **하나뿐**(Intel xHCI `00:14.0`) → **2×HD720@30 고정**(@60 붕괴).
  - **USB3 패시브 연장선 금지** — 불완전 프레임(찢김) 원인. PC 직결 필수.
  - 정확한 융합엔 **ZED360 캘리브(extrinsic)** 선행 필수. `logs/fusion_manual.json` 은 placeholder.
  - **하드웨어·디스플레이는 사용자 환경에만 있다.** codex 샌드박스에는 카메라·GPU·디스플레이가
    없으므로 라이브 실행 불가 → 검증은 `py_compile` / `--help` / 분기 로직까지. 라이브는 사용자.
- 실제 코드: `scripts/` (`run_fusion.py`, `zed_fusion_viz.py`, `zed_fusion_bodytrack.py`,
  `zed_make_fusion_config.py`, `zed_check.py`, `viz_pose_log.py`).

## Headless Plan Execution

- 승인 plan 은 `scripts/codex_exec_plan.sh <plan>` 또는 `/run-plan` 으로 background 실행한다.
- 하네스가 승인 게이트, 실행 전 git 스냅샷, self-contained 브리프와 `.codex/runs/` 로그를 관리한다.
- 실행자는 plan 범위의 작업 트리 변경과 검증만 수행한다. 완료 후 커밋 방식은 해당 plan 을 따른다.
- codex 는 **git 을 쓰지 않는다**(이 환경에서 `.git` 은 read-only). 스냅샷·커밋은 하네스와 사용자 몫.
- codex 는 **네트워크가 없다**. 웹·인터넷 자료가 필요하면 `scripts/codex_ask_claude.sh '<질의>'` 로
  Claude 에 위임하고, Claude 가 `scripts/codex_bridge_watch.sh <pid>` 로 감시·응답한다
  (웹 브리지, `.codex/bridge/`).

## Build And Verification

```bash
conda activate zed                                    # pyzed 는 이 env 에만 있다

# 정적 검증 (카메라·GPU 없이 가능 — codex 는 여기까지)
python3 -m py_compile scripts/<파일>.py
python3 scripts/<파일>.py --help

# 라이브 (사용자 환경, 카메라 2대 + 디스플레이 필요)
python3 scripts/zed_check.py                          # 카메라 인식·단독 스트리밍 점검
python3 scripts/run_fusion.py viz -- --view front     # ZED360 캘리브 강제 → 라이브 뷰어
```

## Code And Architecture Guardrails

- 주석과 커밋 메시지는 **한국어**로 작성한다.
- 좌표계·단위는 전 구간 **`RIGHT_HANDED_Z_UP_X_FWD` / METER** 통일(X=전방, Y=좌, Z=상).
  융합 결과는 **fusion world frame** 이다.
- **fps 30 고정.** 2×HD720@60 은 이 리그에서 붕괴한다. 60 은 거부하도록 둔다.
- 검출 포맷: sender = **BODY_18**, Fusion 융합 결과 = **BODY_34**. 인덱스를 섞지 않는다.
- **새 기능은 새 파일로 추가**한다. 이미 검증된 스크립트의 런타임 동작·CLI 는 바꾸지 않는다.
  공통 헬퍼는 기존 모듈에서 import 해 재사용하되(모듈은 `__main__` 가드), 그 모듈을 개조하지 않는다.
- 카메라 serial 을 하드코딩하지 않는다 — `sl.Camera.get_device_list()` 로 읽는다.
- 스코프 경계: 지금은 **인지(스켈레톤)까지**. hand-eye(`T_base_cam`), ROS2 노드화, ε(t) 모델링,
  CBF 제어층은 범위 밖이다. 필요해지면 별도 승인 plan 을 끊는다.

## Do Not Modify

실행자(codex)가 절대 건드리면 안 되는 것 — 하네스 브리프가 이 목록을 그대로 인용한다.

- `logs/**` — 실측 로그(`.jsonl`), `.svo2` 녹화, `.mp4`, 캘리브 config(`fusion_*.json`).
  재현 비용이 크다. 새 산출물 쓰기는 허용하되 **기존 파일 수정·삭제 금지**.
- `.mcp.json` — API 키 포함. 읽기·수정·커밋 금지.
- `/usr/local/zed/**` — ZED SDK·툴(ZED360 등). 저장소 밖. 수정 금지.
- `scripts/zed_fusion_bodytrack.py`, `scripts/zed_fusion_viz.py`,
  `scripts/zed_make_fusion_config.py`, `scripts/run_fusion.py` 의 **런타임 동작·CLI** —
  해당 plan 이 명시적으로 지시하지 않는 한 변경 금지.
- `scripts/codex_exec_plan.sh`, `scripts/codex_ask_claude.sh`, `scripts/codex_bridge_watch.sh` —
  하네스 자신. 수정 금지.
- `docs/plans/**` 중 `status: done` 인 plan 본문 — 이력이므로 그대로 둔다.
