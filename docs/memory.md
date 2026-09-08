# memory.md — cbf_ws

매 세션 첫 액션으로 읽는다 (Claude·codex·기타 에이전트 공통). CLAUDE.md 보다 먼저.
이 파일은 "지금 우리가 어디에 있는지"를 추적하는 단일 source of truth.
"어떻게 갈 것인지"는 `docs/plans/` 가 담당한다.

---

## Current Stage

**ZED-M 2대 Fusion 휴먼 포즈 파이프라인 — 라이브 뷰어까지 동작. 지금은 ZED360 실측 캘리브로
"분리된 두 스켈레톤을 하나로 합치는" 단계.**

- **PLAN01 (done)** — 2대 sender → SDK Fusion → 융합 스켈레톤 + JSONL 로그
  (`scripts/zed_fusion_bodytrack.py`), 수동 config 생성기(`scripts/zed_make_fusion_config.py`).
  하드웨어에서 2×HD720@30 ~28fps 실동작 확인.
- **PLAN02 (done)** — 라이브 뷰어 `scripts/zed_fusion_viz.py`: 창 2개
  (좌/우 카메라 raw 2D BODY_18 오버레이 + 융합 BODY_34 world 뷰), `--save` 합성 MP4, headless 가드.
- **PLAN03 (done)** — 다시점. `--view {top,front,side,orbit}`, 실행 중 숫자키 `1/2/3/4` 전환,
  기본 front, orbit 자유 회전(`j/l` az, `i/k` el, `u` 리셋)까지 구현.
- **PLAN04 (done)** — `scripts/run_fusion.py`: Fusion 실행 전 **ZED360 캘리브를 강제**하는 게이트
  (ZED360 실행 → 이번 세션에 새로 export 됐는지 mtime 검증 → serial 대조 → 뷰어 실행).
- **PLAN06 (done)** — ArUco 큐브 데이텀으로 `base→zed1_link`, `base→zed2_link`,
  `base→fusion_world`를 측정·저장하고 ROS2 `/tf_static`으로 발행하는 도구와 패키지 구현.
  측정(pyzed/conda)과 발행(ROS2/system)은 YAML 파일로 완전히 분리했다.
- **PLAN07 (done)** — `scripts/base_tf_live.py`: 라이브 LEFT 영상에 base 원점 좌표축을 오버레이하는
  뷰어. 시작 시 큐브 1회 측정(또는 `--from-yaml` 복원)으로 `base_T_cam` 고정 후 `drawFrameAxes`.
  헤드리스는 `--save-frame`. PLAN06 측정 헬퍼를 import 재사용(수정 없음).
- **PLAN08 (done)** — 같은 뷰어에 `base_T_cam` 거리(xyz+총거리)·자세(RPY도 + quaternion) 판독을
  HUD/stdout에 추가.
- **라이브 검증 완료(2026-07-24)**: 두 카메라 모두 base 좌표축 정합 통과. zed1=앞-우측(1.95m),
  zed2=앞-좌측(1.83m), 높이 3mm 일치, 각자 큐브를 ~11°/~14°로 조준(자기일관적). 상세는
  `docs/worklog/2026-07-24.md`. **각 카메라↔base 검증까지 됨.**
- **★ id0/id1 분리 해소 확인(2026-07-24)**: `run_fusion.py viz --skip-calib --view top --save`로
  사람 1명을 40초 촬영 → **내내 `fused=1`, 단일 스켈레톤(id 0)**. 기존 `fusion_zed360.json`(7/17)이
  융합에 충분히 정확하다는 뜻. **milestone(단일 스켈레톤) 사실상 달성.**
- **PLAN09 (done, 2026-08-03)** — `scripts/fusion_ros2_bridge.py`: 융합 BODY_34 를
  `frame_id: fusion_world` 그대로 ROS2 로 실시간 발행(`/human/skeleton_markers` MarkerArray,
  `/human/skeleton_poses` PoseArray, `/human/body_count`). **base 변환은 코드로 안 짜고 tf2 위임.**
  `scripts/run_bridge.sh`(conda+ROS2 격리 런처), `scripts/check_tf_to_base.py`(검증 도구) 추가.
  `cbf_base_tf` 최초 colcon build 완료. 정적/합성 검증 전부 통과(아래 In-flight 참조).
- **PLAN11 (done, 2026-09-03)** — `scripts/zed_fusion_fulllog.py`: SDK 전 필드 JSONL 로거
  (fused/raw 바디 전 필드·SDK timestamp·FusionMetrics), 카메라별 LEFT MP4 기본 저장
  (`frame_idx` 가 JSONL↔MP4 join 키), 선택적 SVO2 녹화. `run_fusion.py` 에 `fulllog` 타깃 추가.
- **PLAN12 (done, 2026-09-04)** — fulllog 에 매 프레임 `record:"frame"` 하트비트
  (frame_idx·타임스탬프·`n_bodies`·`body_ids`) 추가 — 사람 없음 구간도 명시 기록돼
  30Hz 연속 타임라인 성립. 더미 바디 대신 분석 시 outer join. 정적 검증 통과,
  라이브 확인(빈 방 5초 + 사람 5초)만 사용자 몫.
- **PLAN13 (done, 2026-09-04)** — fulllog 산출물을 실행마다 `logs/fulllog_<stamp>/` 하위
  디렉터리에 묶어 저장(파일 이름 불변, meta 에 `run_dir` 추가). SIGTERM 도 SIGINT 와 같은
  stop 핸들러에 연결해 `kill` 로 끊어도 MP4 가 닫힘. 17:02 실측분으로 Ctrl-C 종료 MP4 의
  무결성(ffprobe 640f/30fps, 전체 디코드 무에러)과 `received_fps` 29.998 확인 — PLAN12 라이브
  판정도 사실상 통과(frame 628 / fused 626 / `n_bodies=0` 2).
- **PLAN14 (done, 2026-09-04)** — fulllog 카메라 MP4 를 시스템 ffmpeg(libx264) 파이프로
  **H.264** 저장. 배경: cv2 `mp4v`(MPEG-4 Part 2)는 파일은 무결하지만 VS Code/브라우저에서
  재생 불가였고, conda `zed` 의 cv2 5.0.0 은 H.264 인코더를 열지 못함(avc1/H264/x264 전부 실패).
  ffmpeg 부재 시 `mp4v` 폴백 + 경고, 탈출구 `--video-mp4v`, meta `video_paths[].codec` 추가.
  단위 검증(90프레임 → h264/nb_frames=90, 폴백) 통과. 라이브(`received_fps`≈30, `nb_frames`
  = 마지막 `frame_idx`+1)만 사용자 몫.
- **★ 정반 고정 전략 확정(2026-09-03)** — 카메라를 정반에 고정하고 **"ZED360 1회 →
  measure_base_cam 1회 → 둘 다 동결"** 로 전환. 두 측정 모두 카메라 비접촉이라 코드 변경
  없이(`--skip-calib` 기존 플래그) 가능. 절차·근거는 `docs/worklog/2026-09-03.md`.
- 다음: **고정 세션(사용자)** — 정반 체결 → ZED360 → measure_base_cam(게이트 실험 병행) →
  PLAN09 라이브 검증까지 **한 세션에서** 수행. 그 뒤 다인 id 데이터 토픽(커스텀 msg),
  로봇 URDF 연결.

---

## In-flight tasks

> `logs/base_cam_extrinsics.yaml`(현재 쓰는 실측값)은 2026-07-24 `measure_base_cam.py` 실행
> 산출물이다. `logs/fusion_zed360.json`(융합 캘리브)은 **7/17** 것이다.
> **정반 고정 세션에서 둘 다 새로 뜨고 동결한다** — 그 전까지 낡은 값으로도 조용히 돈다.
> ⚠ 순서 커플링: `measure_base_cam.py` 가 `fusion_zed360.json` 을 소비하고 ZED360 재캘리브는
> fusion_world 원점을 옮기므로, **ZED360 을 다시 돌리면 base YAML 도 반드시 다시 뜬다.**

**정반 고정 세션(사용자 하드웨어)** — 유일한 잔여 블로커. 절차 6단계는
`docs/worklog/2026-09-03.md` 참조: 체결·케이블 클램프 → 예열 → ZED360 →
measure_base_cam(게이트 실험 병행) → 검증. 마지막 검증 단계가 아래 PLAN09 라이브 검증이다.

**PLAN09 라이브 검증(고정 세션의 마지막 단계)** —
**전체 절차·RViz2 설정·트러블슈팅은 [docs/ros2_bridge_runbook.md](ros2_bridge_runbook.md) 참조.**
요약하면 터미널 3개:

```bash
# A) static TF — ★ 실측 YAML 절대경로 필수 (기본값은 전부 0인 placeholder)
source /opt/ros/humble/setup.bash && source ros2_ws/install/setup.bash
ros2 launch cbf_base_tf base_tf.launch.py \
     extrinsics:=/home/pc/cbf_ws/logs/base_cam_extrinsics.yaml
# B) 브리지 — conda activate·source 하지 말 것. 런처가 서브셸에서 결합한다
./scripts/run_bridge.sh --config logs/fusion_zed360.json
# C) rviz2 → Fixed Frame = base, Add > By topic > /human/skeleton_markers (MarkerArray)
```

판정: 스켈레톤이 실제 사람 자리에 서는가, 프레임 밖으로 나가면 잔상 없이 사라지는가,
Fixed Frame 을 `fusion_world`↔`base` 토글 시 **점프하는가**(안 하면 placeholder 함정에 걸린 것).
카메라 없이도 `python3 scripts/check_tf_to_base.py` 로 TF 정확성만 따로 채점할 수 있다.

**PLAN10 (draft, 미승인)** — extrinsics 기본값 하드코딩 + 항등변환 거부 가드.
`docs/plans/2026_08/03_PLAN10_extrinsics_default_and_guard.md`.
launch 기본값을 `/home/pc/cbf_ws/logs/base_cam_extrinsics.yaml` 절대경로로 바꾸고,
**세 transform 이 전부 항등이면 발행 거부 + exit 2**(`allow_placeholder:=true` 만 탈출구),
패키지 placeholder 는 `.example.yaml` 로 rename. 항등 판정은 `check_tf_to_base.py:is_placeholder()`
와 같은 임계값을 쓰고, **`all()` 이지 `any()` 가 아니다**(하나만 항등인 건 정상일 수 있음).
→ **라이브 테스트를 먼저 하고**, 거기서 나온 것을 묶어 한 번에 정리하기로 사용자와 합의.

**게이트 실험(사용자 하드웨어, 라이브 테스트와 같은 세션 권장)** — `--ambiguity-ratio` 가
base 정확도에 미치는 영향 확인. 코드 수정 불필요, 카메라만 있으면 됨.

```bash
conda activate zed && cd ~/cbf_ws
python3 scripts/measure_base_cam.py --out /tmp/gate_on_1.yaml    # 기본값으로 3회
python3 scripts/measure_base_cam.py --ambiguity-ratio 0.99 --out /tmp/gate_off_1.yaml  # 3회
```

각 실행의 **채택 프레임 수**와 `base_T_world 교차검증` 숫자를 적어 요동 폭을 비교한다.
`--out /tmp/...` 로 현재 `logs/base_cam_extrinsics.yaml` 을 보호한다.

- **다양한 포즈 재확인(선택)**: 걷기/가림/여러 위치에서도 `fused=1` 유지되는지 추가 촬영.
- **PLAN03 orbit 3D**: 구현 완료. `--view orbit` 라이브 육안 확인만 남음.
- **다운스트림**: 다인 id 포함 데이터 토픽(커스텀 msg), 로봇 URDF·`T_base_robot` 연결.
- **별도 plan 후보 2건** (PLAN10 범위 밖으로 뺌):
  - **브리지에 ZED360 캘리브 게이트가 없다** — `run_fusion.py` 에는 재캘리브 강제 게이트가
    있는데 `run_bridge.sh` 에는 없다. 카메라가 움직여도 낡은 `fusion_zed360.json` 으로
    조용히 돈다. **라이브 테스트 전 카메라를 건드렸는지 사람이 직접 확인해야 한다.**
  - **`check_tf_to_base.py` 환경 가드 부재** — 브리지는 환경이 틀리면 안내 후 exit 3 인데
    이 도구만 raw `ModuleNotFoundError`. 실행 전 `source /opt/ros/humble/setup.bash` 필요.

---

## Recent decisions

- **역할 정리 (v2 템플릿 채택, 2026-07-17)**: **Claude 기획 / 사용자 승인 / codex 구현**.
  status 토큰 `approved`(구 `codex_approved` 도 하네스가 호환 허용). Claude 쓰기 권한은
  마크다운 한정(`.claude/settings.local.json`). 자세히는 [AGENTS.md](../AGENTS.md).
- **USB3 패시브 연장선 금지 (2026-07-17)**: 연장선이 SuperSpeed 신호를 저하시켜 **불완전 프레임
  (화면 찢김)** 과 `POTENTIAL_CALIBRATION_ISSUE`(경고, 값 -5) 를 유발했다. **PC 직결로 해결.**
  ZED `ERROR_CODE` 규약: 0=SUCCESS, **음수=경고(카메라는 열림)**, 양수=에러.
- **2×HD720@30 고정**: USB 컨트롤러가 하나(Intel xHCI `00:14.0`)라 @60 은 붕괴. 코드가 60 을 거부한다.
- **Fusion 전 ZED360 강제 (PLAN04)**: 카메라가 고정이 아니고 사람들이 치고 지나가 extrinsic 이
  틀어지므로, 매 세션 재캘리브를 기본으로 강제하고 `--skip-calib` 만 탈출구로 둔다.
- **★ 정반 고정 + 캘리브 동결 (2026-09-03)**: 카메라를 정반에 고정하면 두 측정(ZED360, ArUco)
  모두 비접촉이라 "ZED360 1회 → measure_base_cam 1회 → 동결" 이 성립. 이후 세션은
  `--skip-calib` 이 기본 경로가 되고(코드 변경 0), **재캘리브는 fusion_world 원점을 옮겨
  base YAML 을 무효화하므로 오히려 해롭다.** PLAN04 게이트 기본값 뒤집기는 편의성 문제라
  보류. 드리프트 감시는 세션 시작 시 `base_tf_live.py` 육안 확인.
- **좌표/포맷 통일**: `RIGHT_HANDED_Z_UP_X_FWD` / METER, sender=BODY_18, 융합=BODY_34.
- **base static TF 환경 분리 (PLAN06)**: ZED 측정 프로세스는 conda `zed`에서 ROS2 없이 실행하고,
  시스템 Humble 노드는 pyzed/CUDA 없이 좌표 YAML만 읽는다. 기본 TF는
  `base→zed1_link`, `base→zed2_link`, `base→fusion_world`다.
- **★ conda pyzed + 시스템 rclpy 는 한 프로세스에서 공존한다 (2026-08-03 실측)**: 양쪽 다
  Python **3.10**(conda 3.10.20 / 시스템 3.10.12)이라 C 확장 ABI 가 호환되고, conda 쪽
  libstdc++가 더 최신(GCC 14 > 11)이라 시스템 `.so`를 얹는 방향이 문제없다. rclpy·tf2_ros·
  pyzed 동시 import, Node/publisher/TransformListener, DDS(`rmw_fastrtps_cpp`)까지 동작 확인.
  **따라서 소켓/UDP 등 IPC 우회는 불필요**하다. 결합은 `scripts/run_bridge.sh` 서브셸 안에만
  가두고(부모 셸 무오염 확인됨), 브리지가 시작 시 numpy/pyzed/rclpy 로드 경로를 검사해
  어긋나면 **exit 3**으로 죽는다.
- **좌표 변환은 tf2 에 위임 (PLAN09)**: 스켈레톤을 `fusion_world` 로 발행하고 base 변환을
  코드로 곱하지 않는다. 브리지는 `base_cam_extrinsics.yaml` 을 열지도 않는다. 좌표계
  single source of truth 는 `/tf_static` 하나다.
- **numpy 2.2.6 유지**: conda `zed` 의 numpy 를 바꾸지 않는 대신, numpy 1.x 를 요구하는 ROS2
  자산(`cv_bridge`, `sensor_msgs/Image`, PointCloud 헬퍼)을 브리지에서 import 하지 않는다.
  **이미지·포인트클라우드는 ROS2 로 발행하지 않는다**는 것이 설계 제약이다.

---

## Known issues / blockers

- **id0/id1 분리** — **해소 확인됨(2026-07-24)**. 융합 뷰어에서 사람 1명이 단일 스켈레톤으로 나옴.
- **★ ArUco 게이트 역효과 가설(2026-08-03, 미검증)** — `--ambiguity-ratio 0.3` 이 이 리그에서
  **정확도를 오히려 떨어뜨릴 가능성**. 합성 검증 결과 게이트는 코너 노이즈 0.3px 이하에서만
  이득이고, **1.0px 에서는 크게 해롭다**(최악 위치 1515mm/회전 51° → 게이트 OFF 시 93mm/6.4°).
  원인은 88% 를 버려 표본이 12% 만 남아 **평균 효과가 사라지는 것**. 7/24 현장 관측(채택 9/60
  = 15%, 교차검증 552~1022mm)이 정확히 이 구간이다. **확인은 코드 수정 없이 가능**:
  `measure_base_cam.py` 를 기본값으로 3회, `--ambiguity-ratio 0.99` 로 3회 돌려 교차검증
  요동 폭을 비교한다(⚠ `logs/base_cam_extrinsics.yaml` 을 덮어쓰므로 `--out /tmp/...` 사용).
  단, 시뮬은 i.i.d. 가우시안 노이즈 가정이라 **현장 재확인이 필요한 가설**이다.
  상세는 `docs/worklog/2026-08-03.md`.
- **base↔camera 코드는 정확하다 — orientation 포함(2026-08-03 감사)** — PnP→`T_BODY_OPTICAL`→
  `base_T_cam`→Markley 평균→YAML(quat xyzw)→`/tf_static`→tf2 전 구간을 합성 데이터로 검증.
  무노이즈 회전오차 `0.00002°`, YAML 왕복 `0°`, 쿼터니언 순서 전 구간 일관. **오차는 코드가
  아니라 측정 노이즈에서 온다.**
- **ArUco base TF 데시미터급 한계(2026-07-24)** — `measure_base_cam` 교차검증이 실행마다
  552~1022mm/14~21°로 요동 = **노이즈 지배**(버그·datum 오류 아님). datum 방향/ID/up은 검출로
  대조해 정확 확인, 치수만 99mm로 정정(`base_cube_datum.json` 반변 0.0495). 원인: 화면상 태그가
  작음(100mm@1.9m≈34px, ZED-M 광각 fx≈650) → 거리오차 ∝ 거리²/(fx·태그) + 정사각 IPPE flip
  모호성(회전). 평균은 zero-mean만 줄이고 flip·계통오차는 못 지움. **id0/id1 융합과 무관**(융합은
  ZED360 extrinsic). cm급 필요 시 **ChArUco 보드(A3~A2)** 또는 더 가까이 측정.
  **2026-08-03 갱신**: 사용자가 "camera to base 가 필요한 거긴 해"라고 확인 → 단순 보류가 아니라
  **실제 필요 항목**이다. 다만 **게이트 실험(위 항목)이 보드 구매·hand-eye 없이 지금 당장
  시도할 수 있는 유일한 정밀화 수단**이라 그것부터 해본다. 상세 `docs/worklog/2026-07-24.md`.
- **git 스냅샷이 안 찍힌다 (2026-08-03 정정)** — git 2.34.1 은 **설치돼 있다**. 문제는
  `/home/pc/cbf_ws/.git` 이 **빈 디렉터리로 존재**한다는 것. `codex_exec_plan.sh` 는
  `[ ! -d .git ]` 일 때만 `git init` 을 하므로 이 분기를 비껴가고, 이어지는 `git status` 도
  실패해 `SNAP=unknown` 으로 넘어간다 → **롤백 지점 없음**. 고치려면 빈 `.git` 을 지우거나
  직접 `git init` 하면 된다. 단, **지금 상태로 커밋하면 `.mcp.json.example` 의 실제 API 키가
  히스토리에 박힌다** — 키부터 정리하고 할 것.
- **`.mcp.json.example` 에 실제 API 키** 가 하드코딩돼 있다(사용자 의도). `.mcp.json` 은
  .gitignore 됐지만 `.example` 은 추적 대상 — 커밋 시 노출 주의.

---

## 갱신 규칙

- 단계가 바뀌거나 결정이 확정되면 갱신한다. 세션 로그가 아니다 — 날짜별 기록은 `docs/worklog/`.
- 오래된 항목은 지운다. 이 파일은 "현재 상태"만 담는다.
