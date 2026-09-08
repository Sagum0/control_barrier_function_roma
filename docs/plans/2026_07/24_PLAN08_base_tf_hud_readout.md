---
date: 2026-07-24
task: base_tf_live.py 오버레이 뷰어에 base_T_cam 의 거리(xyz + 총거리)와 자세(RPY 도 + quaternion)를 화면 HUD·stdout 에 표시. 축만 그리던 것에서 수치 판독을 추가
planner: Claude
executor: codex
status: done
---

# PLAN08 — base 좌표축 뷰어에 거리·자세 수치 판독 추가

> 파일: `docs/plans/2026_07/24_PLAN08_base_tf_hud_readout.md` (식별자 = PLAN08).

## 한 줄 결론

PLAN07 에서 만든 `scripts/base_tf_live.py` 뷰어는 지금 base 좌표축만 그리고 **수치를 안 보여준다.**
여기에 **base 기준 카메라가 얼마나 떨어졌고(xyz + 총거리) 어떤 자세인지(RPY 도 + quaternion)** 를
**화면 HUD 와 stdout 에 표시**한다. 축 그리기·측정·게이트는 그대로 두고, 이미 확정된 `base_T_cam`
에서 숫자만 뽑아 얹는다. **새 계산 없이 판독 표시만 추가하는 최소 변경**이다.

## 왜 이 plan 이 필요한가

라이브로 축을 봤더니 정합은 맞는데(빨/초/파 축이 큐브에 얹힘), **"카메라가 base 에서 정확히
얼마나·어느 방향으로 떨어졌는지"** 숫자가 화면에 안 보여 판정이 애매하다. 현재는 stdout 에
`base_T_cam xyz` 한 줄만 찍히고 **orientation 은 전혀 안 찍힌다.** 거리와 자세를 화면·로그에
같이 띄우면, 실제 배치(줄자로 잰 거리·각도)와 대조해 측정이 옳은지 바로 판정할 수 있다.

## 지금까지 이어진 맥락 (이 plan 만 읽어도 되게 재서술)

프레임 표기: `T_A_B` = B 좌표의 점을 A 좌표로 보냄. `base_T_cam` = **카메라 body 원점을 base
프레임으로** 보내는 4×4 → 그 **translation = base 기준 카메라 위치**, **rotation = base 기준
카메라 자세**다. 좌표계는 전 구간 `RIGHT_HANDED_Z_UP_X_FWD`/METER (X=전방, Y=좌, Z=상; REP-103 동일).

PLAN07 산출물 `scripts/base_tf_live.py`(pyzed, conda `zed` env)의 현재 동작:
- `--serial`/`--serial-map` 로 카메라를 순차 open, 시작 시 큐브를 warmup 프레임 측정하거나
  `--from-yaml` 로 복원해 **`base_T_cam` 를 1회 확정**.
- 라이브 루프에서 `T_optical_base = inv(T_BODY_OPTICAL) @ inv(base_T_cam)` 로 base 원점 좌표축을
  `cv2.drawFrameAxes` 로 그려 `imshow`(또는 `--save-frame` 저장).
- HUD 는 현재 2줄만: `"zed1 S/N ..."` 과 `"base origin  {mode}"`(measured/from-yaml). **숫자 없음.**
- stdout 은 `base_T_cam xyz(m): [...] [mode]` 한 줄만. **orientation 없음.**
- 재사용 자산: `aruco_cube_datum.mat_to_xyzquat(T) -> (xyz, quat_xyzw)` 가 이미 import 돼 있다
  (quaternion 은 여기서 그대로 나온다). RPY 는 이 quaternion(또는 회전행렬)에서 파생한다.

## 지금 기준 판단 (사용자와 확정)

- 표시 대상은 **`base_T_cam`**(카메라가 base 기준 어디에·어떤 자세인지). fusion_world·스켈레톤은
  이번에도 범위 밖.
- 자세 형식은 **RPY(도) + quaternion 둘 다**. **화면 HUD 에는 읽기 쉬운 RPY(도)**, **stdout 에는
  RPY(도) + quaternion(x,y,z,w)** 를 함께 출력.
- 거리는 **xyz(m) 각 축 + 총거리 `‖t‖`(m)**.
- **축 그리기·측정·게이트·CLI 기본 동작은 변경 없음.** 순수 추가(HUD 줄 추가 + print 확장)만.

## 이번에 할 것

`scripts/base_tf_live.py` 만 수정한다(다른 파일 없음). `base_T_cam` 확정 직후·라이브 루프의
HUD 그리기 지점에서 **거리·자세 수치를 계산해 표시**한다.

## 구현해야 할 것 (파일 단위)

### `scripts/base_tf_live.py` 수정

1. **RPY 헬퍼 (파일 내 작은 함수)**: 회전행렬(또는 `base_T_cam[:3,:3]`)에서 roll(X)/pitch(Y)/
   yaw(Z) 를 **도(degree)** 로 뽑는다. 좌표계가 Z-up/REP-103 이므로 **ZYX(yaw-pitch-roll) 오일러**
   관례를 쓴다(roll=X축 회전, pitch=Y축 회전, yaw=Z축 회전). gimbal(pitch≈±90°) 근처 수치 안정만
   신경 쓰고, 과설계하지 말 것. quaternion 은 이미 있는 `mat_to_xyzquat` 결과를 그대로 쓴다.
   - 참고: 새 의존성 추가 금지. numpy 로 충분(원하면 `mat_to_xyzquat` 의 quaternion → RPY 로 변환).

2. **stdout 확장**(현재 `base_T_cam xyz` 한 줄 → 거리+자세로):
   - `base_T_cam` 확정 후 출력에 다음을 포함:
     - `xyz(m)`: 각 축 값 + 총거리 `dist = ‖xyz‖` (예: `dist=1.945 m`).
     - `rpy(deg)`: roll/pitch/yaw.
     - `quat(xyzw)`: `mat_to_xyzquat` 의 quaternion.
   - 한 카메라당 사람이 읽기 쉬운 2~3줄로. mode(measured/from-yaml)도 유지.

3. **HUD 확장**(라이브 루프에서 매 프레임 그리는 putText):
   - 기존 2줄 아래에 **거리 줄**과 **자세(RPY) 줄**을 추가.
     - 예: `pos(m)  x= 1.410  y=-1.331  z=-0.191  |t|=1.945`
     - 예: `rpy(deg)  r= ..  p= ..  y= ..`
   - **quaternion 은 HUD 에 안 그림**(길고 안 읽힘) — stdout 에만. HUD 는 RPY 까지.
   - 글자 크기·색·위치는 기존 putText 스타일에 맞춰 왼쪽 상단에 이어 붙인다. 배경 대비가 약하면
     기존 톤 유지(과한 반투명 박스 등 새 장식 추가하지 말 것).
   - `base_T_cam` 는 세션 중 고정이므로 매 프레임 재계산할 필요 없다 — **루프 진입 전에 문자열을
     한 번 만들어 두고** 매 프레임 같은 문자열을 그린다(불필요한 연산 회피).

## 참고해야 할 것 (왜 보는지 함께)

- `scripts/base_tf_live.py` (PLAN07) — 수정 대상. `base_T_cam` 확정 위치(현재 xyz print 하는 곳,
  ~223줄)와 HUD putText 위치(~178~182줄), import 된 `mat_to_xyzquat` 를 그대로 활용.
- `scripts/aruco_cube_datum.py` — `mat_to_xyzquat`(quaternion x,y,z,w 산출), `_mat_to_quat`.
  **이 파일은 수정하지 않는다.** RPY 변환은 base_tf_live 안에서 한다.
- PLAN07 plan(`24_PLAN07_...`) — 프레임 규약(`base_T_cam` = body Z-up, optical↔body) 재확인용.

## 신경써야 할 것 (가드레일)

- **축 그리기·측정·게이트 불변**: `drawFrameAxes` 로직, warmup 측정, 재투영오차/모호성 게이트,
  `--from-yaml` 복원, CLI 옵션/기본값은 **손대지 않는다.** 순수 표시 추가만.
- **다른 파일 수정 금지**: `aruco_cube_datum.py`·`measure_base_cam.py`·`zed_fusion_*`·`run_fusion.py`
  는 import/참조만. 변경은 `scripts/base_tf_live.py` 한 파일뿐.
- **프레임 의미 정확히**: 표시하는 값은 `base_T_cam`(카메라가 base 기준 어디/어떤 자세). "카메라에서
  본 base" 로 뒤집지 말 것. 거리/자세 라벨이 이 의미와 일치하게(`pos`=카메라 위치, `rpy`=카메라 자세).
- **RPY 관례 명시**: 주석에 "roll=X, pitch=Y, yaw=Z, ZYX 오일러, 도 단위" 를 적어 나중 혼동 방지.
  quaternion 은 (x,y,z,w) 순서(기존 `mat_to_xyzquat` 와 동일).
- **성능**: HUD 문자열은 루프 밖에서 1회 생성(고정값). 매 프레임 삼각함수 재계산 금지.
- **새 의존성·장식 금지**: scipy 등 추가 금지, 이모지·구분선·반투명 오버레이 박스 추가 금지.
- **샌드박스 한계**: codex 는 카메라·디스플레이 없음 → `py_compile`, `--help`, RPY 헬퍼의 합성
  회전행렬 라운드트립(예: 알려진 RPY→행렬→RPY 복원) 정적 검증까지. **라이브 육안은 사용자.**

## 코드 스타일 (사용자 요청 — "AI 티 안 나게")

PLAN07/`measure_base_cam.py` 와 같은 결. 한국어 주석으로 "왜"만, 과한 docstring·타입힌트 금지,
논리 국면마다 빈 줄, 네이밍 짧고 실용적(`t`, `q`, `rpy`, `dist`). 이모지·장식 금지.

## 이번에는 하지 않는 것 (non-scope)

- **fusion_world 축·스켈레톤 표시**, base_T_world 표시. (PLAN07 non-scope 유지.)
- **축 그리기 방식/길이/색 변경**, 측정 게이트 튜닝, CLI 옵션 추가/변경.
- **quaternion 을 HUD 에 그리기**(stdout 만).
- **다른 스크립트 리팩터**, 좌표계 변환 규약 변경.

## 근거

- 사용자 요청: 라이브 확인 시 축뿐 아니라 **거리(xyz+총거리)와 자세(RPY+quaternion)** 수치가 필요.
  현재 stdout 은 xyz 만, HUD 는 라벨만 → 실측 대조가 어려움.
- `base_T_cam` 는 이미 확정돼 있고 `mat_to_xyzquat` 로 xyz·quaternion 이 바로 나오므로, 추가 계산은
  RPY 파생 하나뿐 → 최소 변경으로 판독성 확보.

## 검증

**정적 (codex, 샌드박스):**
- `python3 -m py_compile scripts/base_tf_live.py` 통과.
- `python3 scripts/base_tf_live.py --help` 정상(옵션 변화 없음 확인).
- RPY 헬퍼 라운드트립: 알려진 roll/pitch/yaw → 회전행렬 → 헬퍼로 RPY 복원이 도 단위 오차 내인지,
  그리고 그 행렬의 `mat_to_xyzquat` quaternion 과 상호 정합하는지 합성 확인(하드웨어 없이 numpy).

**라이브 (사용자, conda `zed` + 하드웨어):**
- `python3 scripts/base_tf_live.py --serial 13870389 --save-frame /tmp/base_axis.png` →
  HUD 에 `pos(m) x/y/z/|t|` 와 `rpy(deg)` 가 뜨고, stdout 에 xyz+dist+rpy+quat 가 찍히는지 확인.
- 화면 수치가 **실제 카메라-큐브 배치(줄자 거리·대략 각도)** 와 상식적으로 맞는지 대조.

## 다음 단계

- 거리·자세까지 확인되면 두 카메라 값을 비교해 ZED360 extrinsic 품질(둘의 base_T_world 편차)과
  연결. 이후 fusion_world 축/스켈레톤을 base 프레임에 오버레이하는 확장(PLAN07 다음 단계)으로 이어감.
