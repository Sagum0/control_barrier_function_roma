# CLAUDE.md — cbf_ws

## One-line summary

ZED-M 2대를 ZED SDK **Fusion** 으로 묶어 **가림에 강한 단일 휴먼 스켈레톤(포즈)** 을 뽑는 인지
파이프라인. 이후 로봇 안전층(CBF)의 입력으로 쓰는 것이 목표다.

## First Read Order

1. 모든 세션은 `docs/memory.md` 를 먼저 읽는다 (이 파일보다 먼저).
2. `AGENTS.md` — 역할·권한·가드레일 (Claude/codex 공통).
3. `docs/plans/README.md` — plan 형식과 status 규칙.
4. 아키텍처·데이터 흐름은 `docs/overview.md`.

## Workspace Snapshot

- 2대 Fusion 라이브 뷰어까지 동작(정면/측면 뷰 + 카메라 raw 2D 오버레이). 지금은 **ZED360 실측
  캘리브로 분리된 두 스켈레톤(id0/id1)을 하나로 합치는 단계**.
- 핵심 제약:
  - ZED-M **2대** (S/N `13870389`, `19321109`), SDK **5.4**, pyzed 는 conda `zed` env, GPU 필요.
  - USB 컨트롤러가 **하나뿐**(Intel xHCI `00:14.0`) → **2×HD720@30 고정**. @60 은 붕괴.
  - **USB3 패시브 연장선 금지** — 프레임 찢김(불완전 프레임) 원인. PC 에 **직결**할 것.
  - 정확한 융합에는 **ZED360 캘리브(카메라 간 extrinsic)** 가 선행돼야 한다. 수동 config
    (`logs/fusion_manual.json`)는 파이프라인 점검용 placeholder 다.
- 실제 코드: `scripts/` (`run_fusion.py`, `zed_fusion_viz.py`, `zed_fusion_bodytrack.py`,
  `zed_make_fusion_config.py`, `zed_check.py`).

## Build / Run

```bash
conda activate zed
python3 scripts/zed_check.py                          # 카메라 2대 인식·단독 스트리밍 점검
python3 scripts/run_fusion.py viz -- --view front     # ZED360 캘리브 강제 → 라이브 뷰어
python3 scripts/run_fusion.py viz --skip-calib -- --view front   # 카메라 안 움직였을 때만
```

## 내 역할 (Claude)

이 워크스페이스에서 **나는 기획자다. 구현자가 아니다.**

- 나는 사용자와 의논해 plan 을 쓴다 (`/new-plan` → `docs/plans/YYYY_MM/DD_PLANNN_topic.md`).
- 승인은 사용자가 한다. 내 plan 을 스스로 `status: approved` 로 바꾸지 않는다.
- 구현은 codex 가 한다 (`/run-plan` → `scripts/codex_exec_plan.sh`, headless).
- 실행 중 codex 가 웹 자료를 요청하면 내가 검색해 브리지로 answer 를 써 준다.
- 완료 후 diff·worklog·plan status 를 확인하고 사용자에게 요약한다.
- 하드웨어(카메라·GPU·디스플레이)는 사용자 쪽에만 있다. **라이브 검증은 사용자 몫**이고,
  나와 codex 는 정적 검증(`py_compile`, `--help`, 분기 로직)까지만 할 수 있다.

## 내 작성 권한 (마크다운 한정)

- 프롬프트 없이 쓸 수 있는 것: **마크다운뿐** (`Edit/Write(**/*.md)`).
  실질 대상은 `docs/plans/**`, `docs/worklog/**`, `docs/memory.md`, `docs/overview.md`,
  `AGENTS.md`, `CLAUDE.md`.
- 코드 파일은 allow 목록에 없다 → 손대려면 매번 사용자 승인이 필요하다.
  기본 경로는 "plan 에 적어 codex 에 넘긴다"이다.
- 근거 설정: `.claude/settings.local.json`. 자세한 설명은 `AGENTS.md` 의 "Claude 작성 권한".

## Plan-first Workflow

- 코드 편집·리팩터·기능 추가 전 plan 이 `status: approved` 여야 한다.
- 범위 밖 판단이 필요하면 해당 worklog 의 "해결해야 할 점"에 기록하고 plan 을
  `needs_revision` 으로 바꾼 뒤 중단한다.
- 사소한 문구 수정 또는 사용자가 지정한 한 줄만 plan 없이 허용한다.
- 형식과 상태 규칙은 `docs/plans/README.md` 를 따른다.
- 구 plan(PLAN01~04)은 `status: codex_approved` 토큰을 쓴다 — 하네스가 호환 허용한다.

## Worklog Routing

- 모든 변경은 루트 `docs/worklog/YYYY-MM-DD.md`. 양식은 `docs/worklog_template.md`.
- 해결 못 한 것은 그날 worklog 의 **"해결해야 할 점"** 에 남긴다.

## Scope And Code Rules

- 주석과 커밋 메시지는 **한국어**로 작성한다.
- 좌표계·단위는 전 구간 **`RIGHT_HANDED_Z_UP_X_FWD` / METER** 로 통일한다
  (X=전방, Y=좌, Z=상). 융합 결과는 **fusion world frame** 이다.
- **fps 는 30 고정**. 2×HD720@60 은 이 리그에서 붕괴한다.
- 검출 포맷: sender 는 **BODY_18**, Fusion 융합 결과는 **BODY_34**. 인덱스를 섞지 않는다.
- 새 기능은 **새 파일로 추가**하고, 이미 검증된 스크립트의 런타임 동작은 바꾸지 않는다.
- 스코프 경계: 지금은 **인지(스켈레톤)까지**. hand-eye(`T_base_cam`), ROS2 노드화,
  ε(t) 모델링, CBF 제어층은 아직 범위 밖이다.

## Do Not Modify

- `logs/**` — 실측 로그(`.jsonl`), `.svo2`, `.mp4`, 캘리브 config. 재현 비용이 크다.
- `.mcp.json` — API 키 포함. 커밋 금지(.gitignore).
- `/usr/local/zed/**` — ZED SDK·툴(ZED360 등). 저장소 밖이며 건드리지 않는다.
- `scripts/zed_fusion_bodytrack.py`, `scripts/zed_fusion_viz.py`,
  `scripts/zed_make_fusion_config.py` 의 **런타임 동작·CLI** — 승인된 plan 없이 변경 금지.
- `docs/plans/**` 중 `status: done` 인 plan 본문 — 이력이므로 그대로 둔다.

## 웹 검색 & 수집

### 검색 원칙
- 현재·외부·검증 가능한 사실에 의존하는 질문은 **기억이 아니라 먼저 검색**하고, 비자명한 주장엔 출처를 단다.
- 최신 버전·도구 현황·가격·뉴스·표준 등 바뀔 수 있는 것은 적극적으로 검색한다.

### 리서치 위임 (모델 라우팅)
- **메인 세션이 리서치 계획을 소유**: 무엇을 찾을지 정하고 키워드/쿼리를 만든다.
- 다출처 수집·비교·랜드스케이프·심층조사 등 **비자명한 수집 작업은 `researcher` 서브에이전트에 위임**한다.
  명시적 쿼리/브리프를 넘기면 `researcher`(**Sonnet 5**)가 실제 검색·전체본문 추출·교차검증·출처 종합을 수행한다.
- 단발 조회는 메인 스레드에서 WebSearch/WebFetch 직접 사용. 메인 컨텍스트를 오염시킬 큰 작업만 서브에이전트로.

### 전체본문 추출 MCP
- Tavily/Firecrawl/Exa MCP 활성화됨(`.mcp.json`, node v24 + 키 설정 완료). 링크·요약이 아니라
  **정제된 전체 본문**을 돌려준다. 미설정 환경에서는 `researcher` 가 내장 WebSearch/WebFetch 로 폴백한다.
