# robot_base_registration.md — 융합 스켈레톤을 로봇 베이스 프레임에 정합하기

Fusion world frame → robot base frame 변환(`T_base_world`)을 **매 세션 수 초 안에** 복구하는
방법에 대한 조사·설계 문서. "지금 어디"는 `docs/memory.md`, "어떻게 갈지"는 `docs/plans/`,
이 문서는 **"이 문제를 어떻게 풀 것이고 왜 그렇게 푸는가"** 를 담는다.

작성: 2026-07-17 / 조사자: Claude / 상태: **설계 후보 (plan 아님, 승인 대상 아님)**

> **원자료는 [robot_base_registration_research.md](robot_base_registration_research.md) 에 있다.**
> 이 문서는 압축·주관적이다 — 채택한 것만 담는다. 근거를 검증·반박하거나, 버린 선택지를
> 재검토하거나, 서로 안 맞는 수치를 보려면 그쪽을 읽어라. 미확인 항목 총목록(§9)도 거기 있다.

---

## 한 줄 결론

**마커의 6-DOF 자세를 쓰지 말고, 마커의 "중심 위치"만 3점 이상 모아 Kabsch 로 푼다.**
회전 추정은 이 리그(ZED-M, 2~3 m)에서 가장 약한 고리이고, 위치-only 로 바꾸면 그 약점이
통째로 사라진다. 이건 우리만의 발상이 아니라 **Kadam et al. 2025 가 UR10e + ZED2i 로
똑같이 해서 x/y < 1 mm, z < 2 mm** 를 얻은 방법이다.

그리고 이 문제의 진짜 병목은 캘리브 알고리즘이 아니라 **하드웨어 구성**이다 → §5.

---

## 0. 검증 등급 표기

이 문서의 모든 주장에는 아래 등급이 붙는다. **등급 없는 문장은 신뢰하지 말 것.**

| 표기 | 뜻 |
|---|---|
| ✅ **실측** | 이 워크스페이스에서 직접 실행/측정해 확인 |
| 📄 **공식문서** | Stereolabs / OpenCV 공식 문서·API 레퍼런스에서 확인 |
| 🔬 **문헌** | 피어리뷰 논문 또는 신뢰할 만한 출처 |
| 🧮 **추론** | 위 사실들로부터 계산·유도. 실측으로 확인 안 됨 |
| ⚠️ **미확인** | 확인 실패. 실측 필요 |

---

## 1. 문제 정의

- **구해야 하는 것**: `T_base_world` — fusion world frame 의 점을 robot base frame 으로 보내는 4×4.
  - 표기 규약: `T_A_B` = B 좌표의 점을 A 좌표로 보냄 (`p_A = T_A_B · p_B`).
- **왜 매번 다시 구해야 하나**: 카메라를 고정 위치에 둘 수 없다. 게다가 ZED360 월드 원점이
  **카메라에 묶여** 있어서(§2), 재캘리브할 때마다 월드가 통째로 딴 데로 간다.
- **최종 소비처**: CBF 안전층. 즉 이 변환의 오차는 **안전 마진에 그대로 가산**된다(§8).

---

## 2. ZED360 월드 프레임 해부 ✅ 실측 + 📄 공식문서

이 절이 이 문서에서 제일 중요하다. **추측이 아니라 우리 실제 캘리브 파일을 SDK 로 읽어서 확인했다.**

### 2.1 실측 결과

`logs/fusion_zed360.json` 을 `sl.read_fusion_configuration_file(path, RIGHT_HANDED_Z_UP_X_FWD, METER)`
로 읽은 결과: ✅

| 카메라 S/N | 위치 (m) | rpy (deg) | override_gravity |
|---|---|---|---|
| `13870389` | `[0.000, 0.000, +0.675]` | `[0, 0, 0]` ← **단위행렬** | `false` |
| `19321109` | `[1.296, −1.756, +0.572]` | `[11.9, −14.9, 72.0]` | `false` |

- 두 카메라 baseline = **2.184 m** ✅
- 원본 JSON 의 `pose` 는 **4×4 행렬을 공백 구분 16-float 문자열**로 저장한다 ✅

### 2.2 ZED360 공식 문서가 말하는 것 📄

`docs.stereolabs.com/docs/development/zed-tools/zed-360` "Useful knowledge" 절, 원문:

> - *"The camera rotations (pitch and roll) are given by the camera IMU, **only the yaw is calibrated**."*
> - *"If during the process the ankles of the person are seen, the floor plane level is estimated."*
> - *"One camera, **the first to be loaded, is defined as the world origin**, its position will be
>   **(0, H, 0)** with H being its height."*

### 2.3 실측과 문서의 일치 ✅

문서의 `(0, H, 0)` 과 우리 파일이 **정확히 일치한다**. 원본 JSON 은 `IMAGE` 좌표계(Y=아래)라
`(0, −0.675, 0)` 으로 저장돼 있고 = 카메라가 원점 위 0.675 m. `RIGHT_HANDED_Z_UP_X_FWD` 로
읽으면 `[0, 0, +0.675]`. **H = 0.675 m = 카메라 1번의 바닥 위 높이.**

### 2.4 결론 — 이게 설계를 좌우한다

- **ZED360 월드 원점** = 카메라 `13870389` 바로 아래 **바닥면**
- **Z** = 중력 반대 (IMU 가 보장)
- **X** = 카메라 `13870389` 이 바라보는 방향(yaw)
- **ZED360 은 4-DOF(yaw + xyz) 만 푼다.** roll/pitch 는 애초에 캘리브 대상이 아니다.
- 카메라 1번의 회전이 단위행렬인 건 그래서다 — 얘가 yaw 기준(yaw=0)이고, 실제 기울기는
  런타임에 IMU 가 공급한다.

> **💡 핵심 함의**: fusion world 는 **중력 정렬이 구조적으로 보장**된다. 로봇 베이스가 수평이면
> `T_base_world` 도 **4-DOF(yaw + xyz)** 다. 6-DOF 로 풀 이유가 없고, 6-DOF 로 풀면
> 오히려 roll/pitch 추정 오차만 주입하는 셈이다. → §6 의 설계 근거.

---

## 3. ZED SDK 사실 정리

### 3.1 `override_gravity` 📄 (SDK 5.2 에서 추가)

pyzed 5.4 스텁 원문:

> - *If true : The calibration pose directly specifies the camera's absolute pose relative to a global reference frame.*
> - *If false : The calibration pose (Pose_rel) is defined relative to the camera's IMU rotational pose.
>   To determine the true absolute position, the Fusion process will compute `Pose_abs = Pose_rel · Rot_IMU_camera`.*

- **우리 파일은 `false`** ✅ → JSON 의 roll/pitch 는 IMU 가 런타임에 덮어쓴다.
- 단일 카메라 쪽 대응물은 `PositionalTrackingParameters.set_gravity_as_origin` (기본 true) 📄

### 3.2 좌곱 항등식 🧮 — 재앵커링이 안전한 이유

`Rot_IMU_camera` 가 **우곱**이라는 점이 결정적이다:

```
목표:  Pose_abs' = T_base_world · Pose_abs
성립:  Pose_abs' = Pose_rel' · Rot_IMU_camera
따라서: Pose_rel' · Rot_IMU = T_base_world · Pose_rel · Rot_IMU
   ⟹   Pose_rel' = T_base_world · Pose_rel        ← Rot_IMU 가 양변에서 소거
```

**즉 JSON 의 pose 를 좌곱하면 `override_gravity` 값과 무관하게 정확히 전파된다.**
순수 대수라 `Rot_IMU_camera` 의 의미를 몰라도 성립한다.

⚠️ 단, 6-DOF 좌곱은 월드를 중력에서 기울인다. §6 의 4-DOF 구속을 쓰면 이 문제 자체가 없다.

### 3.3 config JSON 이 곧 출력 프레임 📄

- `FUSION_REFERENCE_FRAME.BASELINK` (= `retrieve_bodies` 기본값)
  = *"the reference frame where camera calibration is given"* → **config JSON 이 정의하는 프레임**
- `FUSION_REFERENCE_FRAME.WORLD` = fused positional tracking 이 정의 (드리프트/relocalize 가능)
- **`setWorldTransform` 같은 Fusion API 는 없다** 📄 (`InitFusionParameters` 전체 멤버 목록에 없음).
  per-camera `pose` + `override_gravity` 가 유일한 메커니즘.
- 📄 실제 선례: 커뮤니티 사용자가 2대 ZED Fusion 리그를 ArUco 마커 프레임으로 re-base 하는 데
  성공했다. 단 *"works but fiddly"* — `override_gravity=true` 를 제대로 줘도 바닥 그리드가
  약간 안 맞는다는 미해결 보고가 같이 있다.

> ### ⚠️ 이름 함정
> `FUSION_REFERENCE_FRAME.BASELINK` 는 **로봇의 `base_link` 와 아무 상관 없다.**
> ZED 가 "캘리브 프레임"을 부르는 이름일 뿐이다. 코드에서 반드시
> `zed_baselink` vs `robot_base` 로 구분해 명명할 것.

### 3.4 JSON 스키마 불일치 ⚠️

| | 공식 문서 📄 | 우리 SDK 5.4 실파일 ✅ |
|---|---|---|
| 구조 | `{"SN": {"input": {...}, "world": {...}}}` | `{"SN": {"FusionConfiguration": {...}}}` |
| pose 표현 | `world.rotation` (radian, Rodrigues 추정) + `world.translation` | `pose` = 4×4 flat 16-float 문자열 |

**문서와 실제가 다르다.** 손으로 JSON 을 파싱하지 말고 반드시 SDK 함수를 쓸 것:
`sl.read_fusion_configuration_file()` / `sl.write_configuration_file()`.
둘 다 `coord_system` / `unit` 인자를 받아 변환을 대신 해 준다 📄.
(`scripts/zed_make_fusion_config.py` 가 이미 이 왕복 경로를 쓴다 ✅)

### 3.5 좌표계 📄

- **`IMAGE` (SDK 기본값) = OpenCV 규약과 완전히 동일** (X=오른쪽, Y=아래, Z=전방).
  → `coordinate_system=IMAGE` 로 두면 `solvePnP` 결과에 **변환이 아예 불필요**하다.
- 우리 프로젝트는 `RIGHT_HANDED_Z_UP_X_FWD` (ROS REP-103) 로 통일돼 있으므로 변환이 필요하다:

```
X_ros(전방) =  Z_img(전방)
Y_ros(좌)   = −X_img(우)
Z_ros(상)   = −Y_img(하)
```
```
R_ros_img = [[ 0, 0, 1],
             [−1, 0, 0],
             [ 0,−1, 0]]        det = +1 (순수 기저변환)
```
🧮 **이건 유도한 것이다.** Stereolabs 는 이 변환 행렬도, 헬퍼 함수도 공개하지 않는다 📄(부재 확인).
온디스크 JSON 은 항상 `IMAGE` + `METER` 고정 📄.

### 3.6 마커 검출 📄

- **SDK 5.4 에 내장 마커 검출 없음** ✅ (`aruco|apriltag|charuco|fiducial` grep 전부 공백)
- 공식 샘플 `stereolabs/zed-aruco` 존재. OpenCV contrib aruco 사용, **C++ 전용(Python 포팅 없음)**,
  master 는 유지보수 중(최근 커밋 2026-01). `multi-camera/` 모드는 "모든 카메라가 마커 하나를
  보고 공통 프레임에서의 각자 pose 를 도출" — ZED360 의 마커판.
- Stereolabs 서포트가 포럼에서 이 용도로 `zed-aruco` 를 반복 권장 📄.

### 3.7 내부 파라미터 📄 — 마커 검출용

- **`retrieve_image()` 는 rectified/undistorted 이미지를 준다** → `solvePnP` 에 **distortion = 0**.
  공식 서포트 문서 원문: *"distortion parameters are null because images are rectified"*
- 경로: `camera_information.camera_configuration.calibration_parameters.left_cam` → `fx, fy, cx, cy`
  - `calibration_parameters` = rectified (disto 0, 좌우 동일)
  - `calibration_parameters_raw` = unrectified (disto 비영)

> ### ⚠️ 함정 두 개
> 1. **`CalibrationParameters` 는 항상 `IMAGE` 좌표계로 반환된다.**
>    `InitParameters.coordinate_system` 의 영향을 받지 않는다 📄(클래스 레벨 Warning).
>    단 같은 페이지의 `stereo_transform` 필드 설명은 반대로 적혀 있다 — **Stereolabs 문서 자체가
>    모순**이다. 실측으로 확인할 것.
> 2. **intrinsic 이 세션마다 미세하게 바뀐다.** `Camera::open()` 때 self-calibration 이 돌기 때문.
>    캘리브 재현성이 중요하면 **`camera_disable_self_calib=True`** 로 고정할 것 📄.

---

## 4. 방법 landscape

### 4.1 마커 기반 — 6-DOF 자세 사용

| 방법 | 장점 | 단점 |
|---|---|---|
| 단일 ArUco 태그 | 제일 간단 | **평면 자세 모호성(flip)** — 정면에서 두 해가 홱 뒤집힘. 안전 시스템에 치명적 |
| ChArUco / ArUco 보드 | 코너 多 → flip 해소, 회전 안정 | 여전히 회전을 추정해야 함 |
| AprilTag 번들 / 다중 태그맵 | 가림에 강함 | 맵 구축(번들조정) 비용 |

**flip 모호성 상세** 🔬 (Collins & Bartoli, IPPE, IJCV 2014 — 원문):
> *"The problem is ambiguous when the projection of the object is close to affine, which in
> practice happens if it is **small or viewed from a large distance**."*

- 두 해는 시선축을 지나는 평면에 대한 **거울 뒤집힘** 관계다.
- 📄 **거리가 멀어질수록 두 해의 재투영오차 차이가 0 으로 수렴** → 재투영오차만으로 구분 불가.
- ⚠️ OpenCV 기본 iterative `solvePnP` 는 **해를 하나만 반환**해 조용히 틀린 걸 고를 수 있다.
  `SOLVEPNP_IPPE_SQUARE` / `solvePnPGeneric` 은 두 해와 각 재투영오차를 다 준다.
- 🔬 실측 증거 (Jin et al., IROS): AprilTag 자세 추정이 **쌍봉분포**를 보인다.
  *"a 7 cm tag only occupies 15 pixels [at 65 cm], the system has a significant failure rate
  even at 65 cm."*
- 🔬 **IPPE 저자 본인이 제시한 해소법**: *"충분히 넓은 영역에 걸친 여러 개의 공면 마커"* 로
  독립 자세를 각각 풀고 **합의(consensus) 클러스터**를 찾는다.
  → **§6.3 의 다점 데이텀이 정확히 이것이다.** 우리 설계는 자세를 아예 안 쓰므로 더 강하다.
- ⚠️ **단, 공면 마커 집합이 "충분히 넓지" 않으면 보드 전체가 한 덩어리로 flip 한다** (IPPE 저자).
  → §6.3 이 개별 태그 크기가 아니라 **스팬 ≥ 0.8 m** 를 요구하는 이유.
- 🔬 kalibr 공식 위키가 AprilGrid 를 권하는 첫 번째 이유가 *"pose of the target is fully
  resolved (**no flips**)"* 다. `apriltag_ros` 문서도 *"bundle detection is more accurate than
  single tag detection"* 을 사실로 명시한다.

> ### 🚨 안전 시스템에서 flip 이 특히 위험한 이유
> 🔬 FMAC 벤치마크: ArUco 단일 태그의 회전오차 **평균은 멀쩡한데 표준편차가 "수십 도"** 다.
> 원인은 전체의 **~0.5% 가 모호성 케이스에 빠지기 때문**이다.
>
> **평균이 좋아 보여도 꼬리가 시스템을 죽인다.** CBF 안전층은 평균이 아니라 **최악값**으로
> 판정된다. 200 프레임에 한 번 30° 틀어지는 앵커는 "평균 0.1°" 라는 숫자로 정당화될 수 없다.
> → 위치-only 설계는 이 꼬리를 **확률적으로 줄이는 게 아니라 구조적으로 제거**한다.

**태그 패밀리** 📄: AprilRobotics 공식 README 는 이제 *"For the vast majority of applications,
the **tagStandard41h12** family will be the correct choice"* 라고 명시한다 (tag36h11 아님).
41h12 는 2115개 고유태그(36h11 은 587개), 같은 물리크기에서 bit pitch 가 커 검출거리도 길다
(Krogius et al., IROS 2019).

### 4.2 마커 기반 — 위치-only ⭐ 추천

- 마커의 **중심 위치만** 쓰고 자세는 버린다 → 3점 이상 비공선 → Kabsch/Umeyama/Horn 로 강체변환.
- 🔬 **Đalić et al. 2024** (PMC10892941): translation-only 폐형해가 full-pose 보다 **더** 정확·강건.
  캘리브 대상을 단일 3D 점으로 줄이면 자세추정 오차의 영향이 최소화된다. **4개 비공면점으로
  서브밀리**, 기존 SOTA 대비 ~4배 개선.
- 🔬 **Klimchik et al.** (arXiv:1311.6677): 위치(mm)와 자세(deg) 잔차를 한 최소제곱에 섞는 건
  **비동차(non-homogeneous)라 통계적으로 부적절**. 위치-only 가 이걸 회피한다.
  → **"위치-only 는 편해서가 아니라 실제로 더 정확하다"** 의 이론적 근거.
- 🔬 **CMU Robotics Knowledgebase** — "Camera-Robot Registration Using Horn's Method":
  EE 에 **색 구슬** 부착 → 5~6 자세 → 스테레오 HSV 분할 → 삼각측량 → FK 와 짝지어 Horn 로 해.
  원전 Zevallos et al. 2018 (da Vinci), 코드 `gnastacast/dvrk_vision`.
  **스테레오 카메라가 로봇 작업공간을 내려다보는** 구조 = 우리와 거의 동일.

### 4.3 터치 프로빙

- 🔬 TCP 로 알려진 점 N개 접촉 → FK ↔ Kabsch. 4-point 법이 표준, 8~12점 최소제곱 권장.
  현장 정확도 **±0.5 mm, 반복도 ≤0.1 mm**.
- **비전 오차가 0** → `T_base_datum` 확정의 **교차검증용으로 최적**.
- 매 세션은 불가(사람이 조그해야 함).

### 4.4 Markerless (로봇 자체를 마커로) — 🔬 지금은 부적합

| 방법 | 정확도 | 속도 | 비고 |
|---|---|---|---|
| DREAM (ICRA'20) | ~17–113 mm (변형별) | — | 로봇별 학습 필요 |
| RoboPose (CVPR'21) | ~20 mm | **1–1.8 FPS** | 실시간 불가 |
| CtRNet (CVPR'23) | ~20 mm | — | self-supervised |
| CtRNet-X (2024) | ~14 mm | — | 부분 가시성 대응 |
| HoRoPose (ECCV'24) | AUC 82.2 (최고) | **22.6 FPS** | 첫 실시간 holistic |
| LRBO (ICP 기반) | **0.93 mm / 0.265°** | <1–6 s | ⚠️ 구조광/ToF depth 사용, **스테레오 아님** |

**판정: 연구 단계.** 최고가 ~14 mm 인데 이건 우리가 고전 방법으로 얻을 수치보다 **나쁘다**.
게다가 전부 `camera↔robot` 을 풀지, 우리가 필요한 `융합스켈레톤↔robot` 이 아니다.

### 4.5 ZED depth 로 ICP — 🔬 부적합

- 📄 **ZED Mini 데이터시트 (우리 카메라 정확히)**: depth 정확도 **< 1.5% up to 3 m**, < 7% up to 15 m.
  → **2 m 에서 최대 30 mm.** (일반 ZED 문서의 "1%" 보다 나쁘다 — ZED-M 은 베이스라인이 작다)
  📄 오차는 거리에 **2차식**으로 증가하고, 저텍스처 면에서 더 나빠진다.
- ⚠️ 혼동 주의: ZED-M 스펙의 **±1 mm / 0.1°** 는 **visual-inertial ego-motion 추적** 수치지
  정적 장면의 depth map 정확도가 아니다.
- → LRBO 가 1 mm 를 낸 건 구조광/ToF 라 가능했던 것.
- ⚠️ **ZED 스테레오로 로봇 베이스 ICP 를 한 발표 사례는 찾지 못했다.**

---

## 5. 🚨 진짜 병목 — AR 태그는 ZED360 을 대체하지 못한다

**이게 이 문서에서 두 번째로 중요한 지점이다.** 두 문제는 **직교**한다:

| | 무엇을 푸나 | 틀리면 |
|---|---|---|
| **ZED360** | 카메라 ↔ 카메라 상대 extrinsic | 같은 사람이 id0/id1 둘로 갈라짐 (현재 겪는 문제) |
| **AR 태그** | 월드 ↔ 로봇 베이스 | 스켈레톤이 통째로 엉뚱한 곳에 |

- 카메라를 옮기면 **둘 다** 다시 해야 한다. 태그만으로는 절대 안 된다.
- 게다가 ZED360 월드 원점은 카메라 1번에 묶여 있어(§2.4) 재캘리브마다 월드가 이동한다.

> **ZED360 은 *일관된* 프레임을 줄 뿐 *의미 있는* 프레임을 주지 않는다. 의미는 태그가 붙인다.**

### → 해법: 두 카메라를 하나의 강체 리그에 고정

- 알루미늄 프로파일 바 등에 카메라 2대를 **물리적으로 결속**
- cam↔cam extrinsic 이 **불변** → **ZED360 은 평생 1회**
- 리그를 통째로 옮겨도 → 매 세션 **태그 앵커만** 갱신 (수 초)
- 부수효과: 매 세션 ZED360 강제(PLAN04)가 불필요해짐 — 사람이 공간을 걸어다닐 필요 없음
- **"카메라 위치를 고정하지 말고, 둘의 *상대 관계* 를 고정하라"**

⚠️ 미확인: `override_gravity=false` 라 리그를 **기울여도** 저장된 캘리브가 유효한지는
확인하지 못했다(IMU 가 roll/pitch 를 공급하므로 이론상 유효해 보이지만 검증 필요).
안전하게는 리그 자세도 대략 재현하는 걸 권장.

---

## 6. 추천 설계 — 위치-only 다점 데이텀 + 4-DOF Kabsch

### 6.1 왜 위치-only 인가 (근거 3개)

1. 🔬 Klimchik — 위치+자세 혼합 최소제곱은 통계적으로 부적절
2. 🔬 Đalić — translation-only 폐형해가 더 정확, 4점 서브밀리
3. 🧮 우리 리그 계산 — 아래

### 6.2 🧮 오차 계산 (σ_px = 0.2 px, f ≈ 700 px, Z = 2 m 가정)

| 방식 | 깊이 오차 | 비고 |
|---|---|---|
| ZED-M 자체 스테레오 depth (B = **63 mm**) | `Z²σ/(fB)` ≈ **18 mm** | 📄 ZED-M 스펙 "1.5% = 30 mm" 와 같은 자릿수 ✅ |
| 30 cm 태그 단일카메라 PnP | `(Z/S)(Zσ/f)` ≈ **3.8 mm** | 태그의 **알려진 물리 크기**가 스케일 기준 |
| **리그 교차 삼각측량 (B = 2.18 m)** | `Z²σ/(fB)` ≈ **0.5 mm** | ⭐ |

> **💡 ZED-M 의 63 mm 베이스라인은 2~3 m 에서 쓸모없다.**
> 태그의 알려진 크기가 훨씬 나은 깊이 단서이고, **2.18 m 리그 베이스라인은 그보다도 35배 낫다.**
> → **데이텀에 ZED depth(`retrieve_measure`)를 쓰지 말 것.**

📄 참고 (MarkerPose, arXiv:2105.00368): "스테레오를 쓴다"에는 두 가지가 있다 —
(a) 내장 dense depth map 읽기(위 30 mm 노이즈에 종속), (b) **좌/우 rectified 이미지에서 태그
코너를 각각 검출해 그 점만 삼각측량**(dense stereo 를 우회). (b) 가 훨씬 정확하다.
우리 "리그 교차 삼각측량"은 (b) 를 2.18 m 베이스라인으로 하는 것과 같다.

### 6.2b 🧮 태그 크기 산정

📄 Optitag 공식: **`L ≈ (목표_픽셀 × 거리) / 초점거리_px`**

| 목적 | 필요 픽셀 | Z=2 m 에서 L | Z=3 m 에서 L |
|---|---|---|---|
| **검출만** | 16~40 px (📄 Optitag: bit수 × 5 px 권장) | 46~114 mm | 69~171 mm |
| **정확한 자세** | ~100~150 px 🧮 | **286~429 mm** | **429~640 mm** |

> **🚨 단일 태그로 2~3 m 에서 제대로 된 자세를 얻으려면 한 변이 30~64 cm 여야 한다.**
> 로봇 베이스 옆에 붙이기엔 비현실적이다. → **§6.3 의 다점 데이텀이 유일하게 실용적인 답.**
> 보드/번들은 개별 요소가 검출 임계만 넘으면 되고, 정확도는 점들의 **총 스팬**에서 나온다.

🔬 현실 점검: 실제(합성 아님) 단일 태그 보고치는 **1 m 미만 거리에서도 cm 급**에 몰려 있다
(PMC6960891: ~70 cm 에서 1 cm). mm 급은 합성 벤치마크(FMAC)나 자체 개발 마커(TopoTag)에서만
나온다. **작은 단일 태그로 2~3 m 에서 5 mm 는 안 나온다.**

### 6.3 데이텀 설계

- **ArUco/AprilTag 3~4장을 로봇 테이블/베이스 구조물에 ≥ 0.8 m 간격으로 넓게 분산**
- 각 태그는 **중심 위치만** 기여. 자세는 버린다 → flip 모호성 자체가 소멸
- 🧮 **지렛대 효과**: yaw 오차 ≈ 위치오차 / 분리거리 = 2 mm / 0.8 m = **0.14°**
  (반면 40 cm 태그 하나의 자세추정은 잘해야 ~1°, 🔬 Wang & Olson 2016 실측은 **0.5~3°**)
- **"넓게 벌린 성긴 보드"** 가 "조밀한 작은 보드"를 이긴다

> ### 📐 개별 태그 크기 스펙 — 놓치기 쉬운 제약
> 다점 데이텀이라고 **개별 태그를 작게 만들 수는 없다.** 각 태그는 여전히 **독립적으로 ID
> 디코딩**이 돼야 하므로 검출 임계(32~40 px)를 각자 넘어야 한다:
>
> | | 필요 픽셀 | Z=2 m | Z=3 m |
> |---|---|---|---|
> | **개별 태그 (ID 디코딩 가능해야 함)** | 32~40 px 📄 | **9~11 cm** | **14~17 cm** |
> | 데이텀 전체 스팬 (정확도의 원천) | — | ≥ 80 cm 🧮 | ≥ 80 cm 🧮 |
>
> **→ 구체적 제작 스펙: 한 변 15 cm 태그 4장을, 80 cm 이상 벌려서 배치.**
> 정확도는 개별 태그 크기가 아니라 **점들의 총 스팬**에서 나온다. 이게 단일 태그
> 30~64 cm(§6.2b)를 15 cm × 4장으로 대체할 수 있는 이유다.
>
> ⚠️ ChArUco 는 체커보드 코너 검출이 ID 디코딩보다 낮은 해상도로도 될 수 있다고 여러 출처가
> 시사하지만 **정량화한 출처는 없다**. ArUco 다점이 더 안전한 선택.

### 6.4 1단계 — 딱 1회, 오프라인

1. EE 에 마커 부착 → 로봇을 **10~20 자세**로 이동
2. 각 자세에서 `p_base` (FK) ↔ `p_world` (비전) 쌍 수집
3. **Kabsch 로 바로 `T_base_world`** ← ⚠️ **AX=XB 가 필요 없다.**
   카메라가 고정이고 EE 가 움직이므로 이건 순수 점집합 정합 문제다
4. 그 상태에서 데이텀 태그 중심들의 base 좌표를 계산 → **동결** (`p_base_datum[i]`)
5. 🔬 **TCP 터치로 교차검증** — 데이텀을 TCP 로 찍어 독립 확인. 5 mm 안에서 일치해야 통과
6. 버전 태그 달아 저장 → **영구 자산**

### 6.5 2단계 — 매 세션, 수 초

1. 데이텀 태그 3개 이상 검출 → 각 중심의 `p_world`
2. **프레임 게이팅** — 재투영오차 > 1 px 인 검출은 버린다 📄. IPPE 두 해의 재투영오차 차이가
   작으면(모호) 그 프레임도 버린다
3. **30~100 프레임에서 각 데이텀 점의 위치를 중앙값 집계** (outlier 제거)
4. 집계된 점들로 **Kabsch 1회** → `T_base_world`
5. **4-DOF 구속** (yaw + xyz) — §2.4 근거. roll/pitch 를 0 으로 강제

> **💡 위치-only 의 또 다른 공짜 이득**: 점을 먼저 평균내고 Kabsch 를 나중에 돌리므로
> **회전 평균(SO(3)/쿼터니언 평균)이 아예 필요 없다.** 프레임마다 자세를 뽑아 평균내는
> 방식이었다면 🔬 Markley et al. 2007 (`M = Σ wᵢqᵢqᵢᵀ` 의 최대고유벡터) 같은 걸 제대로
> 구현해야 했고, 오일러각/쿼터니언 성분을 순진하게 평균내는 흔한 버그의 위험이 있었다.

**1·2단계가 같은 솔버(Kabsch)를 쓴다.** 코드 하나로 끝난다.

### 6.6 🔬 이 설계의 직접적 선례

**Kadam et al. 2025, "Stereo-Based Single-Shot Hand-to-Eye Calibration for Robot Arms",
Computers (MDPI) 15(1):53** — **UR10e + ZED2i**:

- 포인터 툴로 **3개 비공선 점**을 찍어 world reference frame 을 1회 측정
- 이후 *"if the robot or camera is moved, **a single stereo image of a board with three
  non-collinear points is sufficient** to determine the world-to-camera transformation matrix"*
- 결과: **median RMSE x/y < 1 mm, z < 2 mm** (작업거리 ~500 mm)
- 고전 15-자세 법(x/y 1 mm, z ±3.5 mm)을 **이겼다**

**우리가 수렴한 설계와 사실상 동일하다.** 다만 그들의 작업거리는 500 mm 고 우리는 2~3 m 다
→ 숫자는 그대로 기대하면 안 된다(§8).

### 6.7 어디에 변환을 적용하나

| | C-1. config JSON 재작성 | C-2. 다운스트림 변환 ⭐ |
|---|---|---|
| 방법 | 각 카메라 pose 에 `T_base_world` **좌곱** → `retrieve_bodies` 가 바로 base 좌표 | BODY_34 keypoint 에 곱함 |
| 근거 | §3.2 좌곱 항등식 ✅. 📄 커뮤니티 선례 있음 | 34점 × 4×4 = 수 μs |
| ➕ | 소비자 코드 불필요 | ZED360 출력 원본 보존, Fusion 내부 리스크 0 |
| ➕ | | **앵커 핫리로드** 가능 (Fusion 재시작 불필요) |
| ➕ | | JSONL 에 **두 프레임 다 로깅** → 사후 재앵커링 가능 |
| ➕ | | 프로젝트 규칙 "새 기능은 새 파일" 과 일치 |
| ➖ | `logs/**` 수정 금지 → 새 파일 필요 | 소비자가 매번 곱해야 함 (어차피 CBF 코드는 써야 함) |
| ➖ | 📄 선례 보고가 *"works but fiddly"* | |

**→ C-2 추천.** C-1 의 유일한 장점("다운스트림 코드 불필요")은 어차피 CBF 층 코드를 써야 하므로
실질 장점이 아니다.

---

## 7. 함정 모음

| # | 함정 | 근거 |
|---|---|---|
| **1** | **eye-to-hand 인자 반전** — `cv2.calibrateHandEye` 를 eye-to-hand 로 쓰려면 **로봇 pose 를 역변환**해 **같은 인자 슬롯**에 넣어야 한다. 인자 슬롯을 바꾸면 틀린다. 출력 `R_cam2gripper` 가 실제로는 `R_cam2base`. | 📄 OpenCV 포럼 모더레이터 + 대학 위키 이중 확인 |
| **2** | 🔬 **실제로 터진 사례**: U. Twente 학위논문 — **ZED 2 + Franka** eye-to-hand 에서 **최대 3 m 오차**. 툴이 eye-in-hand 를 암묵 가정. 카메라를 EE 에 옮기니 0.5 m 로 감소. | essay.utwente.nl/103684 |
| **3** | **OpenCV 기본 솔버가 최악** — 기본 `CALIB_HAND_EYE_TSAI` 가 **회전 노이즈에 극도로 민감**. `CALIB_HAND_EYE_PARK` 를 명시적으로 지정할 것. Daniilidis 는 저노이즈에선 최고지만 실제 노이즈 데이터에서 **NaN 반환** 사례 있음. | 🔬 Enebuse et al. PLOS ONE 2022 |
| **4** | **좌표계 변환** — `solvePnP` 는 OpenCV 프레임, config 는 `Z_UP_X_FWD`. 빠뜨리면 조용히 90° 틀어짐. `IMAGE` 로 통일하면 변환 불필요. | §3.5 |
| **5** | **`BASELINK` 이름 충돌** — ZED 의 `FUSION_REFERENCE_FRAME.BASELINK` ≠ 로봇 `base_link` | §3.3 |
| **6** | **ZED depth 금지** — 63 mm 베이스라인은 2 m 에서 18 mm 오차 | §6.2 |
| **7** | **`CalibrationParameters` 는 항상 IMAGE** — `coordinate_system` 무시. 문서 자체가 모순 | §3.7 |
| **8** | **self-calib 변동** — 세션마다 intrinsic 이 미세하게 바뀜. `camera_disable_self_calib=True` | §3.7 |
| **9** | **JSON 손파싱 금지** — 문서 스키마와 SDK 5.4 실파일이 다름 | §3.4 |
| **10** | **`override_gravity` 는 ZED360 이 준 값 그대로** — false→true 로 바꾸려면 `Rot_IMU_camera` 를 알아야 하는데 오프라인에선 모름 | §3.1 |
| **11** 🚨 | **태그 크기는 "검은 사각형만"** — 흰 여백(quiet zone) 을 포함해서 재면 안 된다. 🔬 실제 사례: ROS 사용자가 바깥 종이 크기를 넣어 **2.4 m 에서 0.3~0.35 m 오차**. **이 문서의 다른 모든 오차원을 합친 것보다 크다.** 구현 시 전용 검사 필요 | 📄 3개 출처 독립 확인 (ROS SE, MoveIt Pro, 태그생성기) |
| **12** | **`cv2.aruco.estimatePoseSingleMarkers()` 는 OpenCV 4.7.0 에서 삭제됨** — `cv2.solvePnP(..., flags=SOLVEPNP_IPPE_SQUARE)` 를 직접 호출할 것. API 도 클래스형 `ArucoDetector` 로 이동 | 📄 |
| **13** | **`opencv-python` 말고 `opencv-contrib-python` 을 설치할 것** — 전자의 내장 objdetect 는 사용자들이 "quite buggy" 로 보고. Python ChArUco API 는 아직 C++ 대비 미완(`detectBoard` 부재 등, 2025-08 버그 스레드 존재) ⚠️ 최신 버전에서 해결됐는지는 미확인 → 설치본으로 실측할 것 | 📄 OpenCV 포럼 |
| **14** | **지렛대는 양날** — §6.3 은 지렛대로 yaw 정확도를 벌지만, **데이텀과 로봇 베이스 원점 사이의 거리**는 반대로 자세오차를 증폭한다. 데이텀을 베이스에서 너무 멀리 두지 말거나 오프셋을 명시적으로 모델링할 것 | 🧮 |

---

## 8. 정확도 기대치 🔬

| 출처 | 구성 | 결과 |
|---|---|---|
| **Kawawaki et al. 2025** (MDPI Robotics 14(5):65) | 커스텀 2-카메라 스테레오, 체커보드 + Zhang + eye-to-hand | **평균 3D 위치 오차 ≈ 15 mm** |
| **Kadam et al. 2025** (MDPI Computers 15(1):53) | **UR10e + ZED2i**, 3점 비공선, ~500 mm | **x/y < 1 mm, z < 2 mm** |
| easy_handeye 메인테이너 | UR10e + D435, eye-on-base | "잘하면 5 mm 미만", 실패 시 10~20 mm |
| TCP 터치 프로빙 | 산업 표준 4-point | **±0.5 mm**, 반복도 ≤0.1 mm |

> **🔬 15 mm 를 현실적 기준선으로 잡아라.** Kawawaki 는 "지루하지만 제대로 실행한 고전 방법"이
> 실제로 내는 숫자다. Kadam 의 1~2 mm 는 **작업거리 500 mm** 였고 우리는 2~3 m 다.

⚠️ **1~3 m 작업거리에서의 피어리뷰 정확도 수치는 찾지 못했다.** 두 정량 출처 모두 ~500 mm 다.
거리가 늘면 z 오차가 유의하게 커진다 → **우리 리그에서 실측해야 한다.**

### 8.1 이 오차가 CBF 로 어떻게 전파되나 🔬

**NIST Marvel & Norcross, "Implementing Speed and Separation Monitoring in Collaborative
Robot Workcells"** (PMC5117641) — ISO/TS 15066 SSM 의 사실상 레퍼런스 구현 가이드:

- ISO/TS 15066 최소보호거리 식은 **`Z_R`(로봇 위치 불확실성)과 `Z_S`(작업자/센서 위치
  불확실성)를 가산항으로 명시**한다.
- **→ 정합 오차는 안전거리에 1:1 로 그대로 더해진다.** 필터링되거나 상쇄되지 않는다.
- ⚠️ 원문: *"no standard currently exists for human localization or pose-estimation
  measurement uncertainty."* **정합 정확도의 codified 목표치는 없다** — 통합자의 리스크 평가 몫.

> **→ `T_base_world` 의 반복도 표준편차가 곧 ε(t) 예산의 상수항이다.** 이건 측정해서 넣어야 한다.

---

## 9. 검증 프로토콜

1. **정확도**: TCP 를 K 개 자세로 → FK `p_base` vs 융합관측 `T_base_world · p_world` → residual mm
   - `ZEDM_포즈추출_초기셋업.md` §8 의 EE 프로빙(0.8 / 1.2 / 1.8 m)과 그대로 합류
2. **반복성**: 앵커링 10회 반복 → `T_base_world` 표준편차 → **ε(t) 상수항**
3. **공짜 검증 2개** 🧮:
   - **양 카메라가 데이텀을 다 본다** → `T_base_world` 추정 2개 → **불일치량 = ZED360 extrinsic
     품질 지표.** 지금 겪는 id0/id1 문제의 정량 진단기가 공짜로 생긴다
   - **4-DOF 잔차** — 로봇 베이스가 수평이면 `T_base_world` 의 roll/pitch 는 0 이어야 한다.
     0 에서 벗어난 만큼이 곧 추정 오차

---

## 10. 미해결 / 미확인 ⚠️

1. **로봇 기종 미상** — 리포에 로봇 언급이 전혀 없다. FK/조그 방식이 1단계 설계를 좌우한다.
2. **리그 고정 가능 여부** — 물리적 판단 필요. §5 가 이것에 달려 있다.
3. **1~3 m 정확도 수치 부재** — 문헌이 ~500 mm 만 다룬다. 실측 필요.
4. **Fusion body-tracking 이 월드 Z=up 을 가정하는가** — 4-DOF 구속을 쓰면 무의미해지는 질문.
5. **리그를 기울여도 ZED360 캘리브가 유효한가** (§5) — 이론상 유효해 보이나 미검증.
6. **`CalibrationParameters` 좌표계** — Stereolabs 문서 자체가 모순. 실측 필요.
7. 🔬 **선례 부재** — **ZED Fusion(다중카메라) → 로봇 베이스 정합 사례가 문헌에 없다.**
   우리가 메우는 진짜 공백이지, 뒤처진 게 아니다.
8. 🔬 **Maithani et al.** (이 프로젝트가 인용하는 그 CBF 논문, arXiv:2505.16055) — **ZED 2i +
   Franka + BODY_34** 로 우리와 거의 같은 걸 하면서 **정합 방법을 아예 안 밝혔다**
   (전문 2회 검색). 이 분야가 이 문제를 얼마나 가볍게 넘기는지 보여주는 증거.
9. ⚠️ **"보드가 단일태그 대비 회전오차를 N배 줄인다"는 깔끔한 수치가 문헌에 없다.** 메커니즘과
   방향성은 확실하지만 정량 배수는 아무도 발표하지 않았다. 가장 유망한 미확인 후보:
   Kallwies, Forkel & Wuensche 2020 (IEEE, 49회 인용) — **IEEE Xplore 유료라 초록만 확인.**
   학교 IEEE 접근권이 있으면 이것부터 볼 것.
10. ⚠️ **"정확한 자세"에 필요한 픽셀 수(§6.2b 의 80~150 px)는 합성 추정치다.** 검출 임계
    (32~40 px)는 여러 출처가 일치하지만, 자세용 임계를 명시한 권위 있는 출처는 없다.
    **우리 리그에서 실측해야 한다.**
11. ⚠️ **fiducial 단독 monocular PnP 로 2~3 m 에서 5 mm/1° 를 달성했다는 출처를 찾지 못했다.**
    문헌은 그 거리에서 cm 급을 시사한다. 이것이 다점 데이텀 + 리그 삼각측량을 택하는 이유지만,
    **우리 목표치 자체가 실측으로 검증되지 않았다.**

---

## 11. 참고문헌

### 공식 문서
- ZED360 — https://docs.stereolabs.com/docs/development/zed-tools/zed-360 (월드 원점·yaw-only·floor)
- Fusion 모듈 — https://docs.stereolabs.com/docs/development/zed-sdk/modules/fusion
- Coordinate Frames — https://docs.stereolabs.com/docs/development/zed-sdk/modules/positional-tracking/coordinate-frames
- `FusionConfiguration` — https://www.stereolabs.com/docs/api/structsl_1_1FusionConfiguration.html
- `CalibrationParameters` — https://www.stereolabs.com/docs/api/structsl_1_1CalibrationParameters.html
- rectified vs raw — https://support.stereolabs.com/hc/en-us/articles/27824782212119
- `stereolabs/zed-aruco` — https://github.com/stereolabs/zed-aruco
- OpenCV calib3d — https://docs.opencv.org/4.x/d9/d0c/group__calib3d.html
- OpenCV 포럼 eye-to-hand — https://forum.opencv.org/t/eye-to-hand-calibration/5690

### 논문
- **Kadam et al. 2025**, *Stereo-Based Single-Shot Hand-to-Eye Calibration for Robot Arms*,
  Computers 15(1):53 — https://www.mdpi.com/2073-431X/15/1/53 ⭐ **가장 가까운 선례 (UR10e+ZED2i)**
- **Kawawaki et al. 2025**, MDPI Robotics 14(5):65 — https://www.mdpi.com/2218-6581/14/5/65
  — 현실적 15 mm 기준선
- **Enebuse et al. 2022**, *Accuracy evaluation of hand-eye calibration techniques*, PLOS ONE
  — https://pmc.ncbi.nlm.nih.gov/articles/PMC9581431/ — Tsai 민감성, Park 권장
- **Đalić et al. 2024**, *Submillimeter-Accurate Markerless Hand–Eye Calibration Based on a
  Robot's Flange Features* — https://pmc.ncbi.nlm.nih.gov/articles/PMC10892941/ — translation-only 우위
- **Klimchik et al.**, *Advanced robot calibration using partial pose measurements*
  — https://arxiv.org/abs/1311.6677 — 위치-only 의 통계적 근거
- **Marvel & Norcross (NIST)**, *Implementing SSM in Collaborative Robot Workcells*
  — https://pmc.ncbi.nlm.nih.gov/articles/PMC5117641/ — ISO/TS 15066 `Z_R`/`Z_S` 가산항
- **Maithani et al. 2025**, *Proactive Hierarchical CBF-Based Constraint Prioritization*
  — https://arxiv.org/abs/2505.16055 — ZED 2i+Franka+BODY_34, 정합 방법 미공개
- Tsai & Lenz 1989 — https://kmlee.gatech.edu/me6406/handeye.pdf
- Wershoven (U. Twente BSc) — https://essay.utwente.nl/103684 — ZED 2+Franka eye-to-hand 3 m 오차

### 마커 / 자세추정
- **Collins & Bartoli 2014**, *Infinitesimal Plane-Based Pose Estimation*, IJCV 109(3):252–286
  — https://encov.ip.uca.fr/publications/pubfiles/2014_Collins_etal_IJCV_plane.pdf — **IPPE 원전, flip 모호성**
- **Krogius, Haggenmiller, Olson 2019**, *Flexible Layouts for Fiducial Tags*, IROS
  — https://docs.wpilib.org/fr/latest/_downloads/e72e01c5464f1a0838751a5cb158087e/krogius2019iros.pdf
  — tagStandard41h12 원전
- **FMAC 2026**, *Fair Fiducial Marker Accuracy Comparison* — https://arxiv.org/html/2601.07723v1
  — ArUco/AprilTag/STag/TopoTag 합성 벤치마크. **회전오차 꼬리(~0.5% 모호성)** 근거
- **Wang & Olson 2016**, *AprilTag 2: Efficient and robust fiducial detection*, IROS
  — https://april.eecs.umich.edu/pdfs/wang2016iros.pdf — 단일태그 자세오차 0.5~3° 실측
- AprilTag issue #71 "Ambiguity flipping" — https://github.com/AprilRobotics/apriltag/issues/71
  — 메인테이너의 "근본적 모호성" 설명 + 30°+ 실제 오차 사례
- kalibr, Calibration targets (공식 위키) — https://github.com/ethz-asl/kalibr/wiki/calibration-targets
  — AprilGrid 권장 이유 "no flips"
- tobycollins/IPPE — https://github.com/tobycollins/IPPE — 저자의 모호성 해소법 원문
- **Jin et al.**, *Sensor Fusion for Fiducial Tags*, IROS — https://pengjujin.github.io/files/iros_aptag.pdf
  — 쌍봉분포 실측 증거
- **Markley et al. 2007**, *Averaging Quaternions*, JGCD 30(4):1193–1197
  — https://www.acsu.buffalo.edu/~johnc/ave_quat07.pdf — 회전 평균 정본
- *Analysis and Improvements in AprilTag Based State Estimation* — https://pmc.ncbi.nlm.nih.gov/articles/PMC6960891/
  — 실제 단일태그 cm급 수치
- MarkerPose — https://arxiv.org/abs/2105.00368 — dense depth vs 코너 삼각측량 구분
- Optitag, *Designing the perfect Apriltag* — https://optitag.io/blogs/news/designing-your-perfect-apriltag
  — 크기 산정 공식
- OpenCV `solvePnP` — https://docs.opencv.org/4.x/d5/d1f/calib3d_solvePnP.html
- **ZED Mini 데이터시트** — depth < 1.5% @ 3 m (우리 카메라 정확한 스펙)
- AprilRobotics/apriltag — https://github.com/AprilRobotics/apriltag
- christianrauch/apriltag_ros (ROS2 사실상 표준) — https://github.com/christianrauch/apriltag_ros

### 도구
- CMU Robotics Knowledgebase, Registration Techniques — https://roboticsknowledgebase.com/wiki/math/registration-techniques/
- `easy_handeye2` (ROS2, "eye-on-base") — https://github.com/marcoesposito1988/easy_handeye2
- `gnastacast/dvrk_vision` — https://github.com/gnastacast/dvrk_vision — 색구슬+Horn 참조구현
- MoveIt 2 Hand-Eye Calibration — https://moveit.picknik.ai/humble/doc/examples/hand_eye_calibration/hand_eye_calibration_tutorial.html

---

## 12. 다음 단계 (제안 — 승인 대상 아님)

1. **리그 제작 판단** (§5) — 하드웨어 결정. 다른 모든 것의 전제
2. **C-2 다운스트림 변환 골격** — `T_base_world` 를 JSON 에서 읽어 BODY_34 에 곱하고 두 프레임
   다 로깅. 더미 항등행렬로 먼저 (로봇 없이 가능)
3. **데이텀 검출기** — ArUco 다점 + 위치-only Kabsch + 4-DOF 구속 + 양카메라 교차검증
4. **1단계 캘리브** — 로봇 실물 필요

→ plan 화하려면 `/new-plan`.
