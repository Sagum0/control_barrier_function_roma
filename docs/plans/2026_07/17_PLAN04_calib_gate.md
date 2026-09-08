---
date: 2026-07-17
task: Fusion 실행 전 ZED360 캘리브레이션을 강제하는 런처/게이트 (scripts/run_fusion.py)
planner: Codex (초안 Claude Code, 사용자 지시)
executor: Codex (사용자 지시 예외 — 저장소 기본 역할은 Claude Code)
status: done
---

# PLAN04 — Fusion 실행 전 ZED360 캘리브레이션 강제 게이트

> 파일: `docs/plans/2026_07/17_PLAN04_calib_gate.md` (식별자 = PLAN04).

## 역할 예외 (사용자 지시)
이 plan 한정: **초안 Claude Code 작성 → Codex 검토·승인·구현(owner/executor)**. 저장소 기본
(Codex plan owner / Claude executor)의 **사용자 승인 예외**. 검토자는 역할 배치를 반려 사유로
삼지 않는다(기술 타당성만 판단).

## 한 줄 결론
새 런처 `scripts/run_fusion.py` 를 만들어 **Fusion 을 켜기 전에 무조건 ZED360 캘리브레이션을 먼저**
돌리게 강제한다. 흐름: **ZED360 실행(사용자가 캘리브·export) → 런처가 '이번 세션에 새로 저장된'
config 검증 → 그 config 로 Fusion 뷰어/파이프라인 실행**. 기존 스크립트는 건드리지 않는다.

## 왜 이 plan이 필요한가
카메라가 **고정이 아니고 사람들이 오가며 충격**을 줘서 카메라 간 상대 위치(extrinsic)가 쉽게 틀어진다.
extrinsic 이 틀어지면 같은 사람이 두 카메라에서 **다른 world 위치**로 찍혀 Fusion 이 **별도 스켈레톤
2개(id 0, id 1)** 로 낸다(실제로 방금 목격됨). 현재 `logs/fusion_manual.json` 은 실측이 아닌 placeholder
pose(좌 0,0,0 / 우 0,-1.5,0, yaw180)라 정합이 안 된다. → **매 세션 ZED360 로 새 extrinsic 을 잡고
그 config 로만 Fusion 을 돌리도록** 절차를 강제해야 한다.

## 지금까지 이어진 맥락 (이미 확정된 사실)
- Fusion 뷰어 `scripts/zed_fusion_viz.py`, 파이프라인 `scripts/zed_fusion_bodytrack.py` 는 모두
  `--config <fusion config json>` 를 입력으로 받고, `sl.read_fusion_configuration_file(path, COORD, UNIT)`
  로 읽는다. COORD=`RIGHT_HANDED_Z_UP_X_FWD`, UNIT=METER.
- ZED360 은 GUI 전용 도구(`/usr/local/zed/tools/ZED360`), **CLI/헤드리스 캘리브 불가**. 사용자가
  카메라 추가 → 사람이 걸어다니며 캘리브 → config 를 파일로 export 해야 한다.
- 현재 config 후보는 `logs/fusion_manual.json`(placeholder) 뿐. ZED360 결과 파일은 아직 없음.
- ZED 카메라 목록은 `sl.Camera.get_device_list()` 로 serial 을 얻는다(2대: 13870389, 19321109).
- USB 는 직결로 정상화됨(연장선 문제 해결) — 별개 이슈, 이 plan 범위 아님.

## 지금 기준 판단
- **새 런처(파이썬) 하나**로 게이트한다. 기존 스크립트 수정 없이, 런처가 ZED360 실행 → config 검증 →
  기존 fusion 스크립트를 subprocess 로 호출.
- 기본 동작은 **무조건 재캘리브레이션**(사용자 요구). 단 "카메라 안 움직였음"이 확실할 때를 위한
  탈출구 `--skip-calib` 를 둔다.
- placeholder(`fusion_manual.json`)는 실사용 금지 대상. 런처는 **ZED360 export 전용 경로**
  `logs/fusion_zed360.json` 를 표준으로 쓰고, 이 파일이 **이번 실행 중에 새로 저장됐는지(mtime)** 로
  '신선함'을 판정한다.

## 이번에 할 것
1. `scripts/run_fusion.py` 신규: ZED360 강제 → config 검증 → fusion 실행 게이트.

## 구현해야 할 것 (파일 단위)
- **신규** `scripts/run_fusion.py` (기존 스크립트 불변):
  - CLI:
    - 위치 인자 `target`(`viz` | `bodytrack`, 기본 `viz`) — 실행할 fusion 스크립트 선택.
    - `--calib PATH`(기본 `logs/fusion_zed360.json`) — ZED360 export 대상 & fusion 입력 config.
    - `--zed360 PATH`(기본 `/usr/local/zed/tools/ZED360`).
    - `--skip-calib` — ZED360 생략하고 기존 `--calib` 재사용(신선도 무시, 경고+나이 출력).
    - `--max-age MIN`(기본 미설정) — 설정 시, calib 가 MIN 분 이내면 신선하다고 보고 ZED360 생략.
    - `--` 이후 나머지 인자는 fusion 스크립트로 **passthrough**(예: `--res`, `--view`, `--save`, `--fps`).
  - 흐름:
    1. **카메라 확인**: `sl.Camera.get_device_list()` 로 연결된 serial 수집. 2대 미만이면 안내 후 exit(1).
    2. **디스플레이 확인**: `DISPLAY` 없으면 ZED360(GUI) 불가 → 안내 후 exit(2). (`--skip-calib` 는 예외로 허용.)
    3. **재캘리브 여부 결정**:
       - `--skip-calib` 또는 (`--max-age` 설정 & calib mtime 이 그 이내) 이고 calib 가 유효하면 → 캘리브 생략.
       - 그 외 → 캘리브 필수.
    4. **캘리브(필수 경로)**:
       - 안내 출력(한국어): "ZED360 이 열립니다. ① 두 카메라 추가 ② 사람이 공간을 걸어 캘리브
         ③ **config 를 `<calib>` 로 Export/Save** ④ ZED360 종료." 시작 시각 기록.
       - `subprocess.run([zed360])` 로 **실행 후 종료까지 대기**.
       - 종료 후 `<calib>` 가 **존재 && mtime >= 시작시각**(이번 세션에 새로 저장됨)인지 확인. 아니면
         exit(3): "새 캘리브 config 가 `<calib>` 로 저장되지 않았습니다. Export 경로 확인."
    5. **config 검증**: `sl.read_fusion_configuration_file(calib, COORD, UNIT)` → 2대 이상인지,
       그리고 config serial 이 **연결된 카메라 serial 과 일치**하는지 확인(불일치 시 경고, 심하면 exit).
    6. **Fusion 실행**: `subprocess.run([sys.executable, "scripts/<viz|bodytrack>.py", "--config", calib, *passthrough])`
       하고 그 exit code 를 그대로 반환. (스크립트 경로는 런처 위치 기준으로 해석.)
  - COORD/UNIT 은 fusion 스크립트와 **동일 상수** 사용(`RIGHT_HANDED_Z_UP_X_FWD`, METER).
  - `logs/fusion_manual.json` 을 `--calib` 로 넘기면 "placeholder 다. ZED360 결과 권장" 경고를 남기되
    막지는 않는다(부트스트랩 점검 여지).

## 참고해야 할 것 (왜 보는지 함께)
- `scripts/zed_fusion_viz.py` / `scripts/zed_fusion_bodytrack.py` — 런처가 호출할 대상. `--config` 입력
  형식, `read_fusion_configuration_file`, COORD/UNIT 확인(런처와 일치시켜야 함).
- `scripts/zed_make_fusion_config.py` — config 파일 포맷/serial 키 방식 참고(검증 로직 작성 시).
- `/usr/local/zed/tools/ZED360` — GUI 전용. 실행/대기 방식(subprocess) 근거.
- `logs/fusion_manual.json` — placeholder 예시(실사용 금지 대상).

## 신경써야 할 것 (가드레일)
- **기존 스크립트 런타임 변경 금지**: `zed_fusion_viz.py` / `zed_fusion_bodytrack.py` /
  `zed_make_fusion_config.py` 수정 없음. **새 파일(run_fusion.py)만 추가.**
- **serial 하드코딩 금지**: 연결된 카메라는 `get_device_list()` 로 읽는다(13870389/19321109 고정 금지).
- **신선도 판정은 mtime 기반**: ZED360 실행 시작 시각보다 새로 저장됐는지로 '이번 세션 캘리브'를 판정.
  (사용자가 예전 파일을 그대로 두고 ZED360 을 닫으면 통과시키지 말 것.)
- **헤드리스**: ZED360 은 디스플레이 필요. `DISPLAY` 없으면 캘리브 불가 → 명확히 안내하고 중단.
- **passthrough 인자**는 fusion 스크립트로 그대로 전달하되 `--config` 는 런처가 주입(중복 주의).
- **샌드박스에 카메라·GPU·디스플레이·ZED360 없음**: Codex 는 실제 실행 불가. 검증은 `py_compile` +
  `--help` + 인자/분기 로직 정적 확인 + 헤드리스/`--skip-calib` 분기까지. **라이브는 사용자 `zed` env.**
- ZED360 이 비정상 종료(exit≠0)해도 config mtime 검증으로 걸러지게 할 것.

## 이번에는 하지 않는 것 (non-scope)
- ZED360 내부 캘리브 자동화(불가능 — GUI 상호작용 필수).
- fusion 스크립트 자체 수정, orbit 뷰(=PLAN03 2단계), ROS2, hand-eye.
- 캘리브 품질 정량 평가/자동 재시도.

## 근거
- 방금 관찰: placeholder config 로 같은 사람이 id0/id1 두 스켈레톤으로 분리 → 정확 extrinsic 필요.
- 카메라 비고정 + 충격 → 매 세션 재캘리브가 안전. 사용자 명시 요구("무조건 ZED360 먼저").

## 검증
- `python3 -m py_compile scripts/run_fusion.py` 통과.
- `python3 scripts/run_fusion.py --help` 에 target/`--calib`/`--skip-calib`/`--max-age`/passthrough 노출.
- 헤드리스(`DISPLAY` 해제)에서 캘리브 필수 경로 → exit(2) 안내 확인.
- `--skip-calib` + calib 없음 → 명확한 실패, calib 있음(유효) → fusion 스크립트 호출까지 진행.
- (사용자, `zed` env, 라이브) 런처 실행 → ZED360 뜸 → 캘리브·export(`logs/fusion_zed360.json`) → 종료
  → 런처가 신선도/serial 검증 통과 → 뷰어 실행 → **두 스켈레톤이 하나(단일 id)로 합쳐지는지** 확인.

## 다음 단계
- 합쳐지면 PLAN03 2단계(orbit 3D) 이어서.
- (선택) 캘리브 품질 로그/재캘리브 주기 알림.
