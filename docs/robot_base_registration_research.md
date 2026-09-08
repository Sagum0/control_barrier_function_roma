# robot_base_registration_research.md — 원자료 모음

**융합 스켈레톤 → 로봇 베이스 정합** 조사의 **원자료(raw material)** 다.
2026-07-17 에 수행한 로컬 실측 + 5갈래 웹 리서치의 결과를 **압축하지 않고** 보존한다.

## 이 문서의 위치

| | [robot_base_registration.md](robot_base_registration.md) | **이 문서** |
|---|---|---|
| 성격 | **설계 결정** — 압축·주관적 | **원자료** — 망라적·중립적 |
| 답하는 질문 | "그래서 뭘 할 건데" | **"근거가 정확히 뭔데"** |
| 버려진 선택지 | 결론만 | **왜 버렸는지 전부** |
| 수치 | 채택한 것만 | **찾은 것 전부 + 서로 안 맞는 것도** |

- **설계 판단을 보려면 그쪽을 읽어라.** 이 문서는 그 판단의 근거를 검증·반박·재활용하기 위한 것이다.
- 이 문서는 **plan 이 아니다.** 승인 대상이 아니다.
- 조사 시점: **2026-07-17**. 웹 자료는 시간이 지나면 바뀐다. SDK 사실은 **pyzed 5.4** 기준.

## 검증 등급 (전 문서 공통)

| 표기 | 뜻 |
|---|---|
| ✅ **실측** | 이 워크스페이스에서 직접 실행/측정해 확인 |
| 📄 **공식문서** | Stereolabs / OpenCV 공식 문서·API 레퍼런스 |
| 🔬 **문헌** | 피어리뷰 논문 또는 신뢰할 만한 출처 |
| 🧮 **추론** | 위 사실들로부터 계산·유도. 실측 안 됨 |
| ⚠️ **미확인** | 확인 실패. 실측 필요 |
| 🗣️ **일화** | 포럼·블로그·학위논문 등 낮은 권위. 참고만 |

> **원칙**: 등급 없는 문장은 신뢰하지 말 것. 리서치 에이전트가 "확인 못 했다"고 명시한 것은
> **그대로 ⚠️ 로 보존**했다. 확신 있어 보이게 다듬지 않았다.

---

# §1. 로컬 실측 원자료 ✅

**이 절이 이 문서에서 가장 신뢰도가 높다.** 웹 검색이 아니라 이 PC 에서 직접 실행한 결과다.

## 1.1 ZED360 캘리브 파일 원본

`logs/fusion_zed360.json` (2026-07-17 17:14 생성) 전문:

```json
{
    "13870389": {
        "FusionConfiguration": {
            "communication_parameters": {
                "CommunicationParameters": {
                    "communication_type": "INTRA PROCESS",
                    "ip_add": "",
                    "ip_port": 0
                }
            },
            "input_type": {
                "InputType": {
                    "input_type_conf": "13870389",
                    "input_type_conf_right": "0",
                    "input_type_input": "AUTO",
                    "input_virtual_serial_number": 0
                }
            },
            "override_gravity": false,
            "pose": "1.000000 0.000000 0.000000 0.000000 0.000000 1.000000 0.000000 -0.674864 0.000000 0.000000 1.000000 0.000000 0.000000 0.000000 0.000000 1.000000",
            "serial_number": 13870389
        }
    },
    "19321109": {
        "FusionConfiguration": {
            "communication_parameters": { "CommunicationParameters": {
                "communication_type": "INTRA PROCESS", "ip_add": "", "ip_port": 0 } },
            "input_type": { "InputType": {
                "input_type_conf": "19321109", "input_type_conf_right": "0",
                "input_type_input": "AUTO", "input_virtual_serial_number": 0 } },
            "override_gravity": false,
            "pose": "0.302219 -0.063902 -0.951094 1.755632 -0.038873 0.996094 -0.079278 -0.571798 0.952446 0.060931 0.298555 1.295626 0.000000 0.000000 0.000000 1.000000",
            "serial_number": 19321109
        }
    }
}
```

**관찰**:
- 키는 **serial number 문자열**
- `pose` 는 **4×4 행렬을 공백 구분 16-float 문자열**로 (row-major)
- `override_gravity: false` — **ZED360 이 직접 쓴 값**
- 카메라 `13870389` 의 회전부가 정확히 **단위행렬**, 병진만 `(0, -0.674864, 0)`

## 1.2 좌표계별 읽기 결과 (probe 스크립트)

`sl.read_fusion_configuration_file(PATH, <COORD>, sl.UNIT.METER)` 를 6개 좌표계로 실행:

| COORDINATE_SYSTEM | `13870389` t (m) | `13870389` rpy° | `19321109` t (m) | `19321109` rpy° |
|---|---|---|---|---|
| `IMAGE` | `[0, −0.675, 0]` | `[0, 0, 0]` | `[1.756, −0.572, 1.296]` | `[4.55, −72.40, −2.23]` |
| `LEFT_HANDED_Y_UP` | `[0, +0.675, 0]` | `[0, 0, 0]` | `[1.756, 0.572, 1.296]` | `[−4.55, −72.40, 2.23]` |
| `RIGHT_HANDED_Y_UP` | `[0, +0.675, 0]` | `[0, 0, 0]` | `[1.756, 0.572, −1.296]` | `[4.55, 72.40, 2.23]` |
| `RIGHT_HANDED_Z_UP` | `[0, 0, +0.675]` | `[0, 0, 0]` | `[1.756, 1.296, 0.572]` | `[11.54, −7.33, 72.26]` |
| `LEFT_HANDED_Z_UP` | `[0, 0, +0.675]` | `[0, 0, 0]` | `[1.296, 1.756, 0.572]` | `[−11.94, −14.87, −72.01]` |
| **`RIGHT_HANDED_Z_UP_X_FWD`** ⭐ | `[0, 0, +0.675]` | `[0, 0, 0]` | `[1.296, −1.756, 0.572]` | `[11.94, −14.87, 72.01]` |

- 모든 좌표계에서 `det(R) = 1.000000`, `|t|` 불변 (0.6749 / 2.2556) → 변환이 올바르게 동작 ✅
- **카메라 간 baseline = 2.1844 m** (좌표계 무관 불변량) ✅

**핵심 확인**: `read_fusion_configuration_file` 은 **파일의 네이티브 규약에서 요청한 좌표계로 변환해준다.**
파일 원본 숫자를 직접 해석하면 안 된다.

## 1.3 pyzed 5.4 스텁 원문 ✅

`/home/pc/miniconda3/envs/zed/lib/python3.10/site-packages/pyzed/sl.pyi` 에서 직접 추출.

### `FusionConfiguration.override_gravity`
```
Indicates the behavior of the fusion with respect to given calibration pose.
- If true : The calibration pose directly specifies the camera's absolute pose
  relative to a global reference frame.
- If false : The calibration pose (Pose_rel) is defined relative to the camera's
  IMU rotational pose. To determine the true absolute position, the Fusion process
  will compute Pose_abs = Pose_rel * Rot_IMU_camera.
```

### `Fusion.subscribe`
```python
def subscribe(self, uuid: CameraIdentifier, communication_parameters: CommunicationParameters,
              pose: Transform, override_gravity: bool = False) -> FUSION_ERROR_CODE
```
> `pose`: The World position of the camera, regarding the other camera of the setup.

### `FUSION_REFERENCE_FRAME` enum
```
| WORLD    | The world frame is the reference frame of the world according to the
             fused positional Tracking. |
| BASELINK | The base link frame is the reference frame where camera calibration is given. |
```

### `Fusion.retrieve_bodies`
```python
def retrieve_bodies(self, bodies: Bodies, parameters: BodyTrackingFusionRuntimeParameters,
                    uuid: CameraIdentifier = CameraIdentifier(0),
                    reference_frame: FUSION_REFERENCE_FRAME = FUSION_REFERENCE_FRAME.BASELINK
                    ) -> FUSION_ERROR_CODE
```
> `reference_frame`: The reference frame in which the objects will be expressed.
> Default: `FUSION_REFERENCE_FRAME::BASELINK`.

### `Fusion.get_position`
```python
def get_position(self, camera_pose: Pose,
                 reference_frame: REFERENCE_FRAME = REFERENCE_FRAME.WORLD,
                 uuid: CameraIdentifier = CameraIdentifier(),
                 position_type: POSITION_TYPE = POSITION_TYPE.FUSION) -> POSITIONAL_TRACKING_STATE
```

### `read_fusion_configuration_file` / `write_configuration_file`
```python
def read_fusion_configuration_file(json_config_filename: str,
                                   coord_system: COORDINATE_SYSTEM,
                                   unit: UNIT) -> list[FusionConfiguration]
#   coord_system: "The COORDINATE_SYSTEM in which you want the World Pose to be in."

def write_configuration_file(json_config_filename: str, fusion_configurations: list,
                             coord_sys: COORDINATE_SYSTEM, unit: UNIT) -> None
#   coord_sys: "The COORDINATE_SYSTEM in which the World Pose is."
```
→ **읽기/쓰기 양쪽이 좌표계 변환을 대신해준다.** 왕복(round-trip) 이 지원되는 공식 경로.

## 1.4 SDK 내장 마커 검출 부재 ✅

```bash
grep -niE "aruco|apriltag|fiducial|marker|charuco" pyzed/sl.pyi
# → 결과 없음 (0 hits)
```
**SDK 5.4 에 마커 검출 기능이 없다.** OpenCV `cv2.aruco` 를 직접 써야 한다.

## 1.5 코드베이스에 이미 있던 것 ✅

`scripts/zed_make_fusion_config.py` 가 **이미 config 왕복 경로를 쓰고 있다**:
```python
conf = sl.FusionConfiguration()
conf.serial_number = int(serial)
conf.communication_parameters.set_for_shared_memory()
conf.input_type.set_from_serial_number(int(serial))
conf.pose = _pose(translation, rpy_deg)      # ← pose 는 설정 가능
conf.override_gravity = bool(override_gravity)
...
sl.write_configuration_file(output, configs, COORD, UNIT)
readback = sl.read_fusion_configuration_file(output, COORD, UNIT)
```
→ **read → modify `conf.pose` → write 경로가 이 코드베이스에서 이미 검증된 것.**

`ZEDM_포즈추출_초기셋업.md` §8 (이전 세션에서 이미 확정된 순서):
> 1. **eye-on-base 캘리브레이션**: ChArUco + 로봇 자세 15–20개 → `T_base←cam`. 자동화는
>    easy_handeye2(ROS 2) 계열 사용. **이후 AR 태그 필드 데이텀 방식으로 원샷 재캘 체계 구축
>    (별도 논의 완료).**
> 2. **파일럿 검증**: EE 프로빙 정적(0.8 / 1.2 / 1.8 m) + 리니어 스테이지 동적 → ε(t) 바닥값.

→ **2단계 구조는 이미 결정돼 있었다.** 이번 조사는 그 안을 채운 것이다.

---

# §2. ZED SDK / Fusion / ZED360 📄

## 2.1 Fusion 월드 프레임의 정체

📄 **Fusion 모듈 자체에는 월드에 대한 의미론이 없다.** 월드란 *"구독된 각 카메라의 `pose` 가
표현된 공통 기준 프레임"* 일 뿐이다. Fusion 은 이 프레임을 계산하지도, 강제하지도 않는다.
캘리브 데이터가 말하는 게 곧 월드다.
(docs.stereolabs.com/docs/development/zed-sdk/modules/fusion)

**→ 이건 정책이 아니라 구조다. 따라서 JSON 을 바꾸면 월드가 바뀐다.**

## 2.2 ZED360 의 정책 (Fusion 의 요구사항이 아님)

📄 `docs.stereolabs.com/docs/development/zed-tools/zed-360`, "Useful knowledge" 절 **원문**:

> - *"The camera rotations (pitch and roll) are given by the camera IMU, **only the yaw is calibrated**."*
> - *"If during the process the **ankles** of the person are seen, the **floor plane level is estimated**."*
> - *"One camera, **the first to be loaded, is defined as the world origin**, its position will be
>   **(0, H, 0)** with H being its height, which depends on the condition mentioned above."*

**해석**:
- 원점 = **첫 번째로 로드된 카메라** (임의적 — auto-discover 순서에 좌우됨)
- 방향 = **중력 정렬**(roll/pitch 는 IMU). 캘리브가 푸는 건 **yaw + 병진뿐**
- 바닥 높이 = **발목이 보였을 때만** 추정 (보장 안 됨)

**§1.2 실측과의 대조** ✅: `IMAGE` 좌표계(Y=아래)에서 `13870389` 이 `(0, −0.675, 0)` →
문서의 `(0, H, 0)` 과 **정확히 일치**, **H = 0.675 m**.

⚠️ **함의**: 원점이 "첫 번째로 로드된 카메라"에 묶여 있으므로, **재캘리브할 때마다 월드가
이동할 수 있다.** 심지어 auto-discover 순서가 바뀌면 기준 카메라 자체가 바뀔 수 있다
(⚠️ 이 순서가 결정론적인지는 확인 못 함).

## 2.3 JSON 스키마 — 문서와 실제가 다르다 ⚠️

📄 **공식 문서가 말하는 스키마** (community 실제 예시 4건으로 교차검증, 2023-09~2025-08):
```json
{
    "40457803": {
        "input": {
            "zed": { "type": "USB_SERIAL", "configuration": "40457803" },
            "fusion": { "type": "LOCAL_NETWORK",
                        "configuration": { "ip": "192.168.35.102", "port": 30002 } }
        },
        "world": {
            "override_gravity": "true",
            "rotation": [-0.0834210962, -2.7039804459, -0.0425810814],
            "translation": [1.3352969885, -0.6200794578, 6.5112423897]
        }
    }
}
```

✅ **우리 SDK 5.4 가 실제로 쓰는 스키마** (§1.1): `{"SN": {"FusionConfiguration": {..., "pose": "<16 floats>"}}}`

> ## 🚨 **문서와 실제 파일 포맷이 다르다.**
> - 문서: `world.rotation` (3-vector) + `world.translation` (3-vector)
> - 실제: `pose` (4×4 flat 문자열)
>
> **→ JSON 을 손으로 파싱하지 말 것.** 반드시 `sl.read_fusion_configuration_file()` /
> `sl.write_configuration_file()` 을 쓸 것. SDK 버전 간 포맷이 바뀌었다.

**필드 의미** 📄:
- `input.zed.type`: `USB_SERIAL` | `USB_ID` | `GMSL_SERIAL` | `GMSL_ID` | `SVO_FILE` | `STREAM`
- `input.fusion.type`: `INTRA_PROCESS` (같은 머신) | `LOCAL_NETWORK` (ip+port 필요)
- `world.translation`: **미터**, `world.rotation`: **라디안**
- **온디스크 규약은 `UNIT::METER` + `COORDINATE_SYSTEM::IMAGE` 로 고정** — *"the API read/write
  functions will handle the metric and coordinate system changes"*

**회전 표현** ⚠️: 문서는 "3개 숫자, 라디안"까지만 말한다. 리서치 에이전트의 추론:
`sl::Transform` 이 `getRotationVector()`/`setRotationVector()` 를 *"the 3×1 rotation vector
obtained from a 3×3 rotation matrix using **Rodrigues' formula**"* 로 문서화하고 있고
(`getEulerAngles()` 는 별도 메서드), 실제 예시의 벡터 노름이 ≈2.705 rad (≈155°) 로
"한 성분이 지배적 + 나머지 둘이 작은" 축각(axis-angle) 의 전형적 서명이다.
→ **Rodrigues 벡터로 추정되나 Stereolabs 가 명시적으로 말한 적은 없다.**
(우리 SDK 5.4 는 4×4 를 쓰므로 실무상 무관)

## 2.4 `override_gravity` 📄 (SDK **5.2** 에서 추가)

- ✅ 스텁 원문은 §1.3 참조.
- 📄 단일 카메라 대응물: `PositionalTrackingParameters.set_gravity_as_origin` (기본 **true**)
  — *"the positional tracking system uses the IMU's gravity vector to **override the roll and
  pitch** components of the `initial_world_transform`... The **yaw is preserved**."*
- 📄 **기본 `false` 는 중력 정렬을 강제한다** (JSON 의 roll/pitch 가 라이브 IMU 로 덮어씌워짐).
  **비중력정렬(예: 기울어진 로봇 베이스) 월드가 필요하면 `true` 로.**
- 📄 Stereolabs 서포트가 포럼에서 이 상황에 대해 정확히 이 메커니즘을 안내한 기록 있음.
- 📄 **body tracking 이 중력정렬을 *요구*한다는 서술은 없다.** opt-out 가능한 기본값이지 하드 제약이 아님.

## 2.5 좌곱 항등식 🧮 — 재앵커링 수학

`Rot_IMU_camera` 가 **우곱**이라는 점이 결정적:

```
목표:   Pose_abs' = T_base_world · Pose_abs
성립:   Pose_abs' = Pose_rel' · Rot_IMU_camera        (override_gravity=false 의 정의)
따라서: Pose_rel' · Rot_IMU = T_base_world · Pose_rel · Rot_IMU
  ⟹    Pose_rel' = T_base_world · Pose_rel            ← Rot_IMU 가 양변 우측에서 소거
```

**→ JSON 의 pose 를 좌곱하면 `override_gravity` 값·`Rot_IMU_camera` 의 의미와 무관하게
정확히 전파된다.** 순수 대수라 강건하다. 각 순간마다 성립하므로 IMU 가 런타임 측정치여도 무방.

⚠️ **단**: 6-DOF 좌곱은 월드를 중력에서 기울인다. `override_gravity=false` 상태에서 Fusion 이
IMU 로 중력을 맞추는데 우리가 기울인 월드를 주면 기하학적으로는 일관되나, **Fusion body-tracking
내부가 월드 Z=up 을 가정하는지는 확인 못 했다.** yaw-only(4-DOF) 로 구속하면 이 질문 자체가 소멸.

## 2.6 월드 원점 재정의 — 공식 지원 여부

📄 **결론: 지원된다.** 두 독립 메커니즘:

**(1) 읽기/쓰기 시 좌표계·단위 변환** — 공식 샘플 코드:
```cpp
constexpr sl::COORDINATE_SYSTEM COORDINATE_SYSTEM = sl::COORDINATE_SYSTEM::RIGHT_HANDED_Y_UP;
constexpr sl::UNIT UNIT = sl::UNIT::METER;
auto configurations = sl::readFusionConfigurationFile(argv[1], COORDINATE_SYSTEM, UNIT);
...
sl::InitFusionParameters init_params;
init_params.coordinate_units = UNIT;
init_params.coordinate_system = COORDINATE_SYSTEM;
sl::Fusion fusion;
fusion.init(init_params);
for (auto& it : configurations) {
    sl::CameraIdentifier uuid(it.serial_number);
    fusion.subscribe(uuid, it.communication_parameters, it.pose, it.override_gravity);
}
```
(github.com/stereolabs/zed-sdk — `object detection/multi-camera/cpp/src/main.cpp`)

**(2) 캘리브 파일의 강체 re-base 는 정상 워크플로다** 📄
`T_new_cam_i = T_new_old · T_old_cam_i` 를 모든 카메라에 적용하고 `writeConfigurationFile()`
로 되쓰기 — 📄 **실제 선례**: 한 사용자가 2대 ZED Fusion 리그를 **ArUco 마커 프레임으로
re-base** 하는 데 성공했다 (community.stereolabs.com/t/.../9642, post #6-8). 우리가 하려는
것과 직접적으로 같다.

⚠️ **단, 같은 스레드의 미해결 보고**: `override_gravity=true` 를 제대로 줬는데도 장면/바닥
그리드가 약간 안 맞는다는 문제가 스레드에서 해결되지 않은 채 끝났다.
→ **"works but fiddly"** 로 취급할 것.

**`setWorldTransform` 류 API 는 없다** 📄 (부재를 적극 확인):
- Fusion 모듈 공개 함수 전체: `stopPublishing`, `getCommunicationParameters`,
  `readFusionConfigurationFile`×2, `readFusionConfiguration`, `writeConfigurationFile`
- `InitFusionParameters` 전체 멤버: `coordinate_units`, `coordinate_system`,
  `output_performance_metrics`, `verbose`, `timeout_period_number`, `sdk_gpu_id`,
  `sdk_cuda_ctx`, `synchronization_parameters`, `maximum_working_resolution`
- → **월드 변환 필드 없음.** 단일 카메라의 `PositionalTrackingParameters.initial_world_transform`
  은 Fusion 레벨 개념이 **아니다**.
- **→ per-camera `pose` + `override_gravity` 가 유일한 메커니즘.**

## 2.7 좌표계 규약 📄

`docs.stereolabs.com/docs/development/zed-sdk/modules/positional-tracking/coordinate-frames`:
- **`IMAGE`** (`InitParameters`·`InitFusionParameters` 양쪽 기본값): 오른손, **X=우, Y=하, Z=전**
  → **OpenCV `solvePnP` 규약과 완전히 동일. 변환 불필요.**
- **`RIGHT_HANDED_Z_UP_X_FORWARD`**: 오른손, X=전, Z=상 (Y=좌) — 문서가 명시적으로 **"ROS - REP 103"**

🧮 **변환 행렬 (유도)**:
```
X_ros(전) =  Z_img(전)
Y_ros(좌) = −X_img(우)
Z_ros(상) = −Y_img(하)

R_ros_img = [[ 0, 0, 1],
             [−1, 0, 0],
             [ 0,−1, 0]]      det = +1 (순수 기저변환, 반사 없음)
```
⚠️ **Stereolabs 는 이 행렬도, 변환 헬퍼 함수도 공개하지 않는다** (부재 확인).
`sl::convertCoordinateSystem(pose, from, to)` 같은 건 없다. SDK 가 자동 변환해주는 곳은
**딱 두 군데**: Fusion config 읽기/쓰기의 `coord_sys` 인자, 그리고
`InitParameters`/`InitFusionParameters.coordinate_system` (SDK **전체 라이브 출력**을 재표현;
외부에서 계산한 일회성 pose 에는 안 먹음).

## 2.8 마커 검출 📄

- ✅ **SDK 내장 없음** (§1.4).
- 📄 공식 샘플 **`stereolabs/zed-aruco`** — docs.stereolabs.com/docs/integrations 에 공식 통합으로
  등재 (*"Track or relocalize camera position using Aruco marker"*).
  - `mono/` — 단일 카메라 positional tracking 을 알려진 기준으로 리셋
  - `multi-camera/` — **모든 카메라가 마커 하나를 보고 공통 프레임에서의 각자 pose 를 도출**
    → **ZED360 의 마커판.** 우리 용도와 직접 관련.
  - API: OpenCV Contrib ArUco (BSD-3) 로 검출 + ZED SDK 로 캡처/트래킹 리셋
  - 기본: 6×6 dictionary, **160 mm 마커** (조정 가능, 실물과 반드시 일치해야 함)
  - **유지보수 중**: 커밋 2026-01-08 ("Order device info by serial number"),
    2025-07-10 ("Zed sdk 4... add camera pose export in multi camera").
    **C++ 전용 (99.8%), Python 포팅 없음.** 마지막 태그 릴리스는 v2.x(2020-01) 로 낡았지만
    master 는 계속 커밋됨.
- 📄 전용 how-to 문서 페이지는 없으나, **Stereolabs 서포트(Myzhar, Head of Support)가 포럼에서
  이 용도로 `zed-aruco` 를 반복 권장**.
- 📄 ROS2 별도 컴포넌트: `stereolabs/zed-ros2-examples` 의 `zed_aruco_localization` —
  알려진 마커 글로벌 pose 를 `aruco_loc.yaml` 로 주고 relocalize. positional tracking 필요,
  spatial mapping 불필요, 마커는 relocalization 시점에만 필요.
- 📄 2019 블로그: Unity + OpenCV-for-Unity ArUco (Unity 전용, 코어 SDK/Python 아님)

## 2.9 내부 파라미터 📄

**`retrieve_image()` 는 rectified + undistorted 를 반환** — 공식 서포트 문서
(support.stereolabs.com/hc/en-us/articles/27824782212119) **원문**:
> *"When you use the ZED SDK API functions to retrieve the VIEW::LEFT and VIEW::RIGHT color
> images you normally get the rectified images... 1. left and right intrinsic parameters are
> the same [aligned epipolar lines]... 2. **distortion parameters are null because images are
> rectified** and distortions are no longer present."*

→ **`solvePnP` 에 distortion = zeros 를 넘기는 게 맞다.** ✅ 확정.

**Python 경로** (공식 문서의 정확한 코드):
```python
calibration_params = zed.get_camera_information().camera_configuration.calibration_parameters
fx, fy = calibration_params.left_cam.fx, calibration_params.left_cam.fy
cx, cy = calibration_params.left_cam.cx, calibration_params.left_cam.cy
# calibration_params.left_cam.disto == [0]*12  on rectified images
```
`CameraParameters` 필드: `fx, fy, cx, cy` (픽셀), `disto[12]` = k1,k2,p1,p2,k3,k4,k5,k6,s1,s2,s3,s4,
`lens_distortion_model` = `PINHOLE` (rectified) vs `RAD_TAN`/`FISHEYE` (raw).

**`calibration_parameters` vs `_raw`** 📄:

| | `calibration_parameters` | `calibration_parameters_raw` |
|---|---|---|
| 대응 | `VIEW::LEFT`/`RIGHT` (rectified) | `VIEW::LEFT_UNRECTIFIED`/`RIGHT_UNRECTIFIED` |
| 왜곡 | **0** (`lens_distortion_model = PINHOLE`) | 공장/self-cal 값 (비영) |
| 좌우 fx,fy,cx,cy | **동일** (epipolar 정렬) | 다를 수 있음 |
| `camera_disable_self_calib` 영향 | 받음 | 받음 (둘 다 `Camera::open()` 후 self-cal 반영. 손 안 탄 건 온디스크 `SNXXX.conf` 뿐) |

> ## ⚠️ 함정 2개
> **(a) `CalibrationParameters` 는 항상 `COORDINATE_SYSTEM::IMAGE` 로 반환된다.**
> *"not impacted by `sl::InitParameters::coordinate_system`"* (클래스 레벨 Warning).
> **그런데 같은 페이지의 `stereo_transform` 필드 설명은 정반대로** *"expressed in user
> coordinate system... defined by InitParameters"* 라고 적혀 있다.
> **→ Stereolabs 문서 내부 모순.** 리서치 에이전트도 해결하지 못했다.
> `print(calibration_parameters.stereo_transform)` 을 non-IMAGE 좌표계에서 찍어 **실측 필요**.
>
> **(b) intrinsic 이 세션마다 미세하게 바뀐다.** `Camera::open()` 때 self-calibration 이 돌기
> 때문. Stereolabs Head of Support 가 2025-12~2026-01 포럼 스레드에서 확인.
> **재현성이 sub-pixel self-cal 정확도보다 중요하면 `camera_disable_self_calib = True`.**
> ← **캘리브 워크플로에서는 거의 확실히 이걸 원한다.**

---

# §3. Hand-eye / eye-to-hand (AX=XB) 📄🔬

> **먼저**: 우리 설계(§6 설계문서)는 결국 **AX=XB 를 안 쓴다.** 카메라가 고정이고 EE 가
> 움직이므로 (FK 점 ↔ 관측 점) 쌍이 바로 나와서 **Kabsch 로 충분**하다. 그럼에도 이 절을
> 남기는 이유: (a) 이전 세션에서 easy_handeye2 로 하기로 했던 경로의 근거,
> (b) 교차검증용 대안, (c) **§3.2 의 함정은 누가 AX=XB 를 쓰든 반드시 알아야 한다.**

## 3.1 `cv2.calibrateHandEye()` — 공식 시그니처 📄

```python
cv.calibrateHandEye(R_gripper2base, t_gripper2base, R_target2cam, t_target2cam
                    [, R_cam2gripper[, t_cam2gripper[, method]]]) -> R_cam2gripper, t_cam2gripper
```

| 인자 | 방향 | 의미 |
|---|---|---|
| `R_gripper2base`, `t_gripper2base` | in | **gripper → base** (`bTg`). 로봇 FK pose. 자세당 1개씩 `Mat` 벡터 |
| `R_target2cam`, `t_target2cam` | in | **target → camera** (`cTt`). 보드/마커 PnP 결과 |
| `R_cam2gripper`, `t_cam2gripper` | out | **camera → gripper** (`gTc`). 추정할 상수 변환 |
| `method` | in | `HandEyeCalibrationMethod`, 기본 `CALIB_HAND_EYE_TSAI` |

**메서드 enum** 📄 (OpenCV 가 명시한 인용 포함):

| 상수 | 원전 | 분류 |
|---|---|---|
| `CALIB_HAND_EYE_TSAI` **(기본값)** | Tsai & Lenz 1989 | separable (회전→병진 순차) |
| `CALIB_HAND_EYE_PARK` | Park & Martin 1994 | separable |
| `CALIB_HAND_EYE_HORAUD` | Horaud & Dornaika 1995 | separable |
| `CALIB_HAND_EYE_ANDREFF` | Andreff, Horaud & Espiau 1999 | simultaneous (동시) |
| `CALIB_HAND_EYE_DANIILIDIS` | Daniilidis 1998 | simultaneous, dual-quaternion |

📄 공식 주석 **원문**: *"A minimum of **2 motions with non-parallel rotation axes** are necessary
to determine the hand-eye transformation. So at least **3 different poses** are required, but it
is strongly recommended to use **many more** poses."*

## 3.2 🚨 eye-to-hand 함정 — 이 절에서 가장 중요

📄 **삼중 확인됨** (OpenCV 공식 문서 유도 + OpenCV 포럼 모더레이터 + 질문자 본인의 해결 코드 +
대학 로보틱스 위키의 독립 재현).

**공식 문서의 유도**:
- **eye-in-hand**: `Ai·X = X·Bi`, `Ai=(bTg₂)⁻¹·bTg₁`, `Bi=cTt₂·(cTt₁)⁻¹`, `X=gTc`
- **eye-to-hand**: `gTb₁·bTc·cTt₁ = gTb₂·bTc·cTt₂` ⟹ `Ai·X=X·Bi` where
  **`Ai=(gTb₂)⁻¹·gTb₁`** — 즉 **`gTb` (로봇 pose 의 역)** 로 만들고, **`X=bTc`**
  (= 로봇 베이스 프레임에서의 카메라 pose = **우리가 원하는 것**)

**실전 레시피** (forum.opencv.org/t/eye-to-hand-calibration/5690):
1. `R_target2cam`/`t_target2cam` 는 **평소와 똑같이** 계산 (보드 PnP). **구성과 무관하게 불변.**
2. `R_gripper2base`/`t_gripper2base` 도 평소대로 FK 에서 계산
3. **각 gripper pose 를 역변환**: `R_b2g = R_g2b.T` ; `t_b2g = -R_b2g @ t_g2b`
4. `cv2.calibrateHandEye(R_gripper2base=R_b2g_list, t_gripper2base=t_b2g_list,
   R_target2cam=R_target2cam, t_target2cam=t_target2cam, method=...)`
   — **역변환한 pose 를 같은 인자 슬롯에 넣는다.**
   ⚠️ **`R_target2cam` 을 다른 슬롯으로 바꿔 넣으면 틀린다** (같은 스레드에서 그렇게 시도한
   사람이 틀린 결과를 얻음)
5. 출력이 시그니처상 `R_cam2gripper`/`t_cam2gripper` 로 불리지만 **수치적으로는
   `R_cam2base`/`t_cam2base`** 다.

> ### 🔬 이 함정이 실제로 터진 사례
> **Wershoven, U. Twente BSc 논문 2024** (essay.utwente.nl/103684):
> **Franka Research 3 + ZED 2** 캘리브. 카메라를 **월드 프레임에 고정**(= 우리의 eye-to-hand
> 시나리오)했을 때 오차가 **최대 3 미터**. 원인은 툴/문서가 **eye-in-hand 만 지원**하는데
> eye-to-hand 로 쓴 것. 카메라를 EE 에 옮기니 최대 ~0.5 m 로 감소.
>
> 🗣️ 학위논문 수준(단독 저자, 한 학기)이라 권위는 낮지만 **정확히 우리 구성(ZED + eye-to-hand)
> 에서 터진 경고**다. **범용 hand-eye 툴은 eye-in-hand 를 조용히 가정하고, 설정을 명시적으로
> 안 하면 처참하게 실패할 수 있다.**

## 3.3 `cv2.calibrateRobotWorldHandEye()` 📄

```python
cv.calibrateRobotWorldHandEye(R_world2cam, t_world2cam, R_base2gripper, t_base2gripper
                              [, R_base2world[, t_base2world[, R_gripper2cam[, t_gripper2cam
                              [, method]]]]]) -> R_base2world, t_base2world, R_gripper2cam, t_gripper2cam
```
- **AX=ZB** 를 푼다: `A⇔cTw`(자세별), `X⇔wTb`(상수, 출력), `Z⇔cTg`(상수, 출력), `B⇔gTb`(자세별)
- ⚠️ **주목**: `B` 인자가 이미 `base2gripper` 방향으로 **명명**돼 있다 → 역변환 트릭이
  파라미터 이름에 내장돼 있는 셈
- 최소 3 측정. 메서드: `CALIB_ROBOT_WORLD_HAND_EYE_SHAH` (기본, Shah 2013),
  `CALIB_ROBOT_WORLD_HAND_EYE_LI` (Li, Wang & Wu 2010)
- 용도: gripper↔camera extrinsic **과** 외부 "world" 프레임의 로봇 베이스 정합을 **동시에** 복구.
  world/target 이 base 와 일치할 필요가 없음.

⚠️ **미확인**: `calibrateRobotWorldHandEye` 를 eye-to-hand 에 어떻게 매핑하는지에 대한
**인용 가능한 완결 레시피를 찾지 못했다.** OpenCV 포럼 자체에 미해결 스레드가 있다
(forum.opencv.org/t/2733) — 질문자가 "하나는 base/world 도 반환한다" 이상의 답을 못 받았다.
**→ eye-to-hand 목적이면 `calibrateHandEye` + 역변환 트릭이 이중 확인된 더 나은 경로.**

📄 **공통 제약** (2025-10 포럼): **둘 다** 체인의 한쪽(`bTg`/`gTb` 또는 target/world)이 모든
샘플에서 **역할상 상수**여야 한다. **target 자체가 자세마다 독립적으로 움직이는 시나리오는
어느 쪽도 지원 안 함.**

## 3.4 솔버 비교 🔬

**주 출처: Enebuse et al., "Accuracy evaluation of hand-eye calibration techniques for
vision-guided robots," PLOS ONE 2022** (PMC9581431, 29회 인용).
6개 알고리즘(Tsai, Chou, Park — separable; Daniilidis, Lu, Li — simultaneous)을 시뮬레이션 **+
실제 UR5e** 로 벤치마크.

**핵심 결과**:
- ⚠️ **보편적 승자 없음** — *"these different algorithms perform differently when the noise
  conditions vary rather than following a general trend."*
- **simultaneous (Daniilidis, Lu, Li) 는 회전 노이즈에 강함**
- **separable (Tsai, Park, Chou) 는 병진 노이즈에 강함**
- 🚨 **Tsai 는 "회전 노이즈에 극도로 민감"** — 아주 낮은 노이즈에서만 남들과 비슷.
  **= OpenCV 의 기본값이 이 그룹에서 가장 노이즈에 취약하다.**
- 복합 노이즈 종합: **Daniilidis, Park, Chou 가 가장 신뢰할 만함.**
  Daniilidis 는 저노이즈에서 최고지만 노이즈가 커지면 Park/Chou 아래로 떨어짐
- **운동 범위 효과 (반직관적, 중요)**:
  - **회전** 스팬↑ → separable 정확도 **개선**, simultaneous 정확도 **악화**
  - **병진** 스팬↑ → simultaneous **개선**, separable **악화**
  - **→ "자세를 많이/넓게"가 만능이 아니다. 솔버 계열에 맞춰야 한다.**
- 계산량: **Park 가 가장 효율적.** Daniilidis 는 자세 수가 적을 때, Li 는 많을 때 비쌈
- 실제 로봇 실험 기준선: **~18 자세, 평균 회전 44.7°, 평균 병진 350.6 mm**

🗣️ **실전 데이터 포인트**: `CALIB_HAND_EYE_DANIILIDIS` 가 어떤 사용자의 실제(노이즈 있는)
데이터셋에서 **NaN 반환**. 나머지 4개는 (부정확해도) 유한한 값 반환
(forum.opencv.org/t/hand-eye-calibration/1880).

> **실무 권고**: **`method=cv2.CALIB_HAND_EYE_PARK` 를 명시적으로 지정하라.**
> OpenCV 기본값(Tsai)에 의존하지 말 것. 또는 여러 개 돌려 잔차 교차검증.

**보조 출처**: Ali et al., *"Methods for Simultaneous Robot-World-Hand–Eye Calibration:
A Comparative Study,"* Sensors 2019 (111회 인용) — Shah/Li/Dornaika 계열 비교.
다만 **새 방법 제안이 주목적**이라 고전 5개 랭킹에는 Enebuse 가 더 적합.

## 3.5 데이터 요구사항 🔬 — 4개 출처 수렴

| 출처 | 최소 | 권장 |
|---|---|---|
| 📄 OpenCV 공식 | **3 자세** (2 motion, 비평행 회전축) | "many more" |
| 🔬 Tsai & Lenz 1989 원전 | **3 station** | "Using more than three stations improves the accuracy" |
| 📄 MoveIt 2 | **5 샘플** | **"plateau after about 12 or 15 samples"** |
| 🔬 Enebuse 실험 | — | ~18 자세 |

🔬 **Tsai 원전의 미묘한 지적**: station 을 많이 쓸수록 연속 station 간 회전축 사이 각도가
**좁아지는 경향** → **자세 수보다 축 분산(axis spread) 을 의도적으로 설계하는 게 중요**.

📄 **`easy_handeye2` README 가 Tsai §1.3.2 를 직접 인용**:
> *"Maximize rotation between poses. Minimize the distance from the target to the camera.
> Minimize the translation between poses. Use redundant poses. Calibrate the camera intrinsics
> if necessary. Calibrate the robot if necessary."*
>
> *"the end effector must be rotated as much as possible (**up to 90°**) about **each axis, in
> both directions**. Translating the end effector is not necessary, but can't hurt either."*

📄 **MoveIt 2**: *"at least **two rotation axes** are needed to uniquely solve for the
calibration"*, 항상 같은 축으로만 회전시키지 말라고 경고.

🗣️ **자세 다양성 > 자세 개수의 극적 증거** (Mech-Mind 커뮤니티):
**30개의 잘못 분포된/불규칙한 자세 → ≈4 cm 오차** vs **더 적지만 잘 분포된 세트 → ≈5 mm 오차**.

**종합**: **3자세는 수학적 하한. 10~20 자세가 현실 목표.** 축 분산을 우선하고, simultaneous
솔버를 쓸 거면 병진 다양성도 챙길 것.

## 3.6 패키지 landscape 📄

| 패키지 | 생태계 | 지원 | 마커 | 비고 |
|---|---|---|---|---|
| **`easy_handeye2`** | ROS2 | **둘 다** — **"eye-in-hand" / "eye-on-base"** (= eye-to-hand 의 그들 용어) | `tf` 발행하는 아무 트래커 (`aruco_ros` 등) | ⭐ 280 stars, 활발히 커밋 중. GUI 샘플링 + MoveIt 자동 이동. OpenCV Tsai 계열 래핑. **eye-on-base 에서 보조 마커의 배치를 "지워준다"** — 마커가 어디 있는지 몰라도 됨 |
| `easy_handeye` | ROS1 | 동일 | 동일 | 1.2k stars (원본). ROS2 는 위쪽 사용 |
| **MoveIt Calibration** | ROS1(Melodic) 주력, ⚠️ ROS2 상태 확인 필요 | 명시적으로 둘 다 | ArUco/ChArUco 보드 | RViz 플러그인, "AX=XB Solver" 드롭다운(**기본 Daniilidis**), **raw joint state 를 기록해 세션 재생 가능** |
| `handeye_calib_camodocal` | ROS1 | 범용 | 다양 | ⚠️ 2026 유지보수 상태 미확인 (README 자체 주장만) |
| `ethz-asl/hand_eye_calibration` | 독립 Python/ROS1 | eye-in-hand 지향 | 아무 마커 | Daniilidis + **시간 오프셋 동시 추정** — 카메라/로봇 스트림이 하드웨어 동기가 아닐 때 유용 (Furgale et al., FSR 2017) |
| **Kalib** (2024) | 연구 코드 | markerless | 없음 (foundation model 로 단일 기준점 추적) | 물리 마커 회피. 덜 검증됨 |

⚠️ **`handeye-calib` 이라는 정확한 이름의 표준 패키지는 없다.** 소규모/지역 저장소만 존재
(`fishros/handeye-calib` 중국어 ROS1, `lixiny/Handeye-Calibration-ROS`).

🗣️ **`easy_handeye` 메인테이너 본인의 정확도 발언** (issue #130): UR10e + RealSense D435
eye-on-base 구성에서 **"you should at least be able to achieve an error of a few millimeters
(less than 5)"**. 질문자 본인의 (아마 최적화 안 된) 실행은 **1~2 cm**.

## 3.7 hand-eye 정확도 수치 🔬

| 출처 | 구성 | 결과 |
|---|---|---|
| 🗣️ easy_handeye issue #130 | UR10e + D435, eye-on-base | 잘하면 **< 5 mm**; 첫 시도 **1~2 cm** |
| 🔬 **Kadam et al. 2025/26** (Computers 15(1):53) | **UR10e + ZED2i**, 작업깊이 ~500 mm | **median RMSE x/y < 1 mm, z < 2 mm**. 스테레오 intrinsic reprojection error 0.26 px |
| 🔬 Kadam 의 비교 기준선 (고전 15-자세법) | — | x/y ~1 mm, z ±3.5 mm → **Kadam 의 single-shot 이 이겼다** |
| 🔬 Enebuse 2022 | UR5e | ⚠️ **상대오차 곡선만 보고** (실기에 ground truth 없음) → 위 행들과 직접 비교 불가 |

🔬 **Kadam 의 z 오차 해석**: ZED2i 의 **depth 스펙(< 1% up to 3 m)** 이 z-RMSE 의 하한.
500 mm 에서 ~5 mm 가 "카메라 스펙상 허용", 실측 z-RMSE 는 그 안에 들어옴.

> ## ⚠️ 결정적 갭
> **1~3 m 작업거리에서의 스테레오 hand-eye 정확도 피어리뷰 수치를 찾지 못했다.**
> 정량 출처 두 개(Kadam, easy_handeye issue) **둘 다 ~500 mm** 다.
> depth 카메라 정확도가 z 오차의 바닥을 결정하므로, **0.5 m → 2~3 m 로 가면 z 오차가
> 유의하게 커진다.** 우리 리그에서 실측해야 한다.

## 3.8 2단계(1회 캘리브 → 이후 원샷) 패턴 🔬

⚠️ **이 패턴의 정착된 단일 명칭을 찾지 못했다.** "base to tag", "world anchor",
"single-shot recalibration", "calibration transfer" 등으로 표적 검색했으나 필드 표준 용어 없음.

**그러나 개념은 두 곳에서 독립적으로 근거가 확실하다**:

**(1) 📄 MoveIt 2 튜토리얼이 수학을 명시** — 기본값으로 **안 하는 이유**로서:
> *"If the target's pose in the robot base frame were known accurately, **only a single
> observation** of the camera-target transform would be necessary to recover the camera's pose
> in the end-effector frame... A better option, however, is to combine the information from
> several poses to **eliminate the target pose in the base frame from the equation**."*

→ **MoveIt 은 수학이 성립함을 인정하되, 저장된 target pose 의 부정확성에 의존하지 않으려고
다자세를 기본으로 둔다.** ← 우리 설계의 리스크가 정확히 여기 있다: `T_base_datum` 의 품질.

**(2) 🔬 Kadam et al. 2025** (§5 "Collecting Data Only Once") — **ZED2i 로 이걸 구현**:
- 포인터 툴로 **3개 비공선 점**을 찍어 world reference frame 을 로봇 베이스 대비 1회 측정
- 이후 *"if the robot or camera is moved, **a single stereo image of a board with three
  non-collinear points is sufficient** to determine the world-to-camera transformation matrix"*
- 결과: **x/y < 1 mm, z < 2 mm**, 고전 15-자세법 대비 **정확도로 이기면서** 데이터 수집은 훨씬 적음

**🧮 이 패턴의 오차 특성 (종합)**: 원샷 단계는 단일 PnP/삼각측량이므로 (다자세 hand-eye 가
암묵적으로 하는) 다중 관측 평균이 없다. 정확도의 상한은 (a) 단일 프레임 fiducial 검출/PnP
노이즈 바닥 — 코너 국소화 오차, 태그 크기, 시야각(정면 얕은 각에서 평면 PnP 모호성이 악화),
(b) 원래 `T_base_datum` 측정에 박힌 잔차. **→ 제대로 된 다자세 재캘리브보다는 노이즈가 크다.**
채택 시 원 다자세 캘리브 잔차 위에 **추가 오차항을 예산에 잡을 것.**

---

# §4. Fiducial 마커 — 정확도·모호성·크기 🔬📄

> 리서치 **2건**(마커 정확도 / 보드·크기)의 결과를 병합. 서로 다른 수치를 낸 부분은
> **양쪽 다 보존**했다.

## 4.1 마커 패밀리 비교 🔬

### FMAC 벤치마크 (arXiv:2601.07723, 2026-01 preprint)
**방법론**: 마커 타입당 **10,000개 Halton-샘플 6-DoF 자세**, 50×50 mm 가상 마커, 레이트레이싱.
⚠️ **합성이다** — 실제 센서/조명 노이즈 없음.

| 마커 | 검출률 | 위치 정확도 | 회전 정확도 | 비고 |
|---|---|---|---|---|
| **TopoTag** | 최저/최단거리 (500~1000 mm 만) | **≈0.1 mm X/Y, 0.7 mm Z** (최고) | — | 범위가 너무 좁음 |
| **AprilTag** (3.4.5, tag36h11) | **99.74%** | ArUco 보다 전 DoF 에서 훨씬 작음 | **≈0.1°** — *"particularly good at estimating rotation angles"* | ⚠️ **~90° 주기의 순환 yaw 오차 아티팩트** 발견, 저자도 설명 못 함 (*"could indicate numerical errors"*) |
| **ArUco** | **100%** (가장 강건한 검출기) | **체계적 depth 과대추정** | 🚨 **표준편차 "수십 도"** | 500~900 mm 좁은 대역에서만 정확 |
| **STag** | ~40 px 이하 실패 | — | 쌍봉 오차 분포, yaw 주기성 | |

> ## 🚨 FMAC 의 가장 중요한 발견 — 안전 시스템 관점
> ArUco 회전오차의 **평균은 멀쩡한데 표준편차가 "수십 도"** 다. 원인은 전체의 **~0.5% 가
> 모호성(ambiguity) 케이스에 빠지기 때문.**
>
> **→ 평균이 좋아 보여도 꼬리가 시스템을 죽인다.** CBF 안전층은 평균이 아니라 **최악값**으로
> 판정된다. 200 프레임에 한 번 30° 틀어지는 앵커는 "평균 0.1°"로 정당화할 수 없다.

### 기타 데이터 포인트

- 🔬 **Wang & Olson 2016, "AprilTag 2"** (공식, 실측+합성): 단일 태그 자세오차
  **≈0.5~3°** (시야각 0~90° 스윕, 그들 Fig. 6). **모호성이 없는 정상 영역에서도** 단일 마커
  회전오차는 무시할 수 없고 **비스듬한 각도에서 커진다**. 실제 모자이크 테스트: 0.167 m 태그,
  0.6~7 m.
- 🔬 **Olson 2011 (AprilTag 원전)**: 그들 실험에서 태그가 **"about 49 to 100 pixels, including
  the payload"** — 최소값 선언이 아니라 실제 운용 범위.
- 🔬 **PMC6960891** ("Analysis and Improvements in AprilTag Based State Estimation"):
  **~70 cm 에서 raw AprilTag ≈1.0 cm (x̄), ≈0.40 cm (ȳ)**. 보정 기법 적용 후 0.8 cm / 0.54 cm.
  **카메라 z축이 태그 중심을 향할 때 가장 정확**, yaw 가 벗어날수록 측정 가능하게 악화.
- 🗣️ **Krumstroh et al. 2025/26** (크로스카메라 ArUco): 실제 ArUco 정밀도 **91~97%**
  (HP webcam 94%, Logitech Brio 91%, Meta Quest 3 97%), coverage 72~89%.
  ⚠️ 커스텀 트래커(BART) 대비 벤치마크지 AprilTag 대비가 아님.
- 🗣️ **ARTag/AprilTag/CALTag 가림 연구** (2017, kpfu.ru): 복잡한 물체에 의한 가림 하에서
  AprilTag(구 버전)가 100회 중 15회 실패, CALTag/ARTag 가 더 강건. ⚠️ **AprilTag 3 이전
  검출기라 낡음.**
- 🔬 **원조 ArUco 논문의 보드 실험** (Garrido-Jurado et al. 2014, 24-마커 보드, 가림 스윕):
  회전/병진 오차가 **가림 ~85% 를 넘을 때까지 "insignificant"**. 단일-vs-보드 수치는 아니지만
  **보드의 여유(slack) 가 얼마나 큰지** 보여줌.

### 태그 패밀리 선택 📄

**Krogius, Haggenmiller, Olson, "Flexible Layouts for Fiducial Tags," IROS 2019**
(= tagStandard41h12 를 도입한 논문):
- **41h12: 고유 태그 2115개** vs **36h11: 587개**
- 셀 수가 적은데도 **최소 해밍거리는 더 큼**
- 같은 물리 크기에서 **bit pitch 가 커 검출거리가 길다**
- 새 검출기가 AprilTag2 와 ArUco 보다 **recall 이 높으면서 precision 유지**

📄 **AprilRobotics 공식 README 현재 문구**:
> *"For the vast majority of applications, the **tagStandard41h12** family will be the correct choice."*

→ **tag36h11 이 아니다.** 기본 선택은 41h12.

📄 **비트 수 vs 강건성 트레이드오프** (Optitag + AprilRobotics 문서):
- 비트가 적은 패밀리(16h5)는 더 멀리 검출되지만 **false positive 율이 매우 높다**
- AprilRobotics 권고: **36h11 = 범용 강건성**, **25h9 = 거리 필요 + 강건성 일부 희생**,
  **16h5 = 극단적 거리 니치만**

🗣️ **Politesi.polimi.it 학위논문 2025** (Firmino & Petrucci): 36h11 / 41h12 / 52h13 **모두**
90 cm 에서 USB·스마트폰 카메라 양쪽에서 **100% 검출 / 0 false positive**. 패밀리 간 차이는
**더 먼 거리 / 더 작은 크기에서만** 나타나며 거기서 52h13, 41h12 가 36h11 을 근소하게 이김.

⚠️ **갭**: **동일한 실제(합성 아님) 조건에서 ArUco vs AprilTag vs ChArUco 의 false-positive
율을 %로 보고한 단일 벤치마크를 찾지 못했다.** 위 수치들은 조각이지 통합 표가 아니다.

## 4.2 🚨 평면 자세 모호성 (flip) — 가장 위험한 실패 모드

### 원전: Collins & Bartoli, "Infinitesimal Plane-Based Pose Estimation," IJCV 109(3):252–286, 2014

📄 **논문 원문**:
> *"The problem is ambiguous when the projection of the object is **close to affine**, which in
> practice happens if it is **small or viewed from a large distance**."*

**기하학적 성질**: 두 해는 *"a **flip** of the object about a plane whose normal passes through
the line-of-sight from the camera centre to the object's centre"* 관계.
→ **정면에 가까움 / 픽셀상 작음 / 멀리 있음 = 정확히 위험 구간.**

### IPPE 의 처리 📄
> *"It always returns **two candidate pose solutions and their respective reprojection errors**...
> sorted with the first pose having the lowest reprojection error. It is possible to **reject the
> second pose if its reprojection error is significantly worse** than the first (a likelihood
> ratio test)."*

🚨 **OpenCV 기본 iterative `solvePnP` 는 이 문제를 겪는다** — *"because it only returns one
solution"* → **조용히 틀린 해를 고를 수 있다.**

### 🚨 거리가 멀면 재투영오차로도 구분 불가 📄
IPPE GitHub 데모: **"the reprojection error of the second pose solution tends to zero as the
depth tends to infinity"**
→ **멀어질수록 두 해가 재투영오차만으로는 구별되지 않는다.** 우리는 2~3 m 다.

### 독립적 실측 증거 🔬
**Jin et al., "Sensor Fusion for Fiducial Tags: Highly Robust Pose Estimation from Single-Frame
RGBD," IROS**:
- AprilTag 자세 추정의 **쌍봉(bimodal) 분포**를 관측하고 정량화
- 원문: *"a **7 cm tag only occupies 15 pixels** [at 65 cm], the system has a **significant
  failure rate even at 65 cm**."*
- AprilTag P4P 파이프라인 몬테카를로 → **회전오차 > 30° 인 자세의 비율**을 시야거리/각도 함수로 측정

### AprilTag 메인테이너 본인의 인정 📄
**GitHub issue #71 "Ambiguity flipping"** — 이례적으로 명시적:
- 메인테이너: *"a **fundamentally ambiguous problem**, if the tag's apparent size in the image
  is small enough"*
- 다른 기여자: *"there's **no way to resolve it other than more points, or 4 non-planar points**"*
  → **즉 정확히 보드/번들**
- 한 보고자의 실제 데이터: 자세가 flip 하면 **오차 > 30°**

### 해소법 — IPPE 저자 본인이 제시 📄
1. **비공면(non-coplanar) 추가 마커**: *"if you have one or more additional markers that are
   **not co-planar**... you can resolve the ambiguity. This is because the PnP problem no longer
   involves a planar model, and we can compute pose uniquely."*
2. **공면 추가 마커** (= ArUco/ChArUco 보드): 되긴 하는데 **조건부** —
   🚨 *"the set of markers must span a region of space that is **'sufficiently large'**"*
   → **안 그러면 보드 전체가 한 덩어리로 flip 한다.**
3. 🔬 **Ch'ng et al. 2019** (arXiv:1909.11888): 모호성이 근본적임을 확인하고
   **다중 마커/다중 뷰 + robust rotation averaging with clique constraints** 로 해소 제안

### 업계의 인정 📄
- **kalibr 공식 위키**가 AprilGrid 를 권하는 **첫 번째 이유**: *"pose of the target is
  **fully resolved (no flips)**"*
- **`apriltag_ros` 문서**가 사실로 명시: *"**bundle detection is more accurate than single tag
  detection**"*
- 🗣️ **Limelight** (FRC 비전 코프로세서 벤더) 문서: *"Increasing capture resolution will always
  increase 3D accuracy and increase 3D stability. This will also **reduce the rate of ambiguity
  flipping** from most perspectives."*

### 실전 사례 — 우리 시나리오와 동일 🗣️
Stack Overflow (stackoverflow.com/questions/71407392): **UR10e 로봇 툴에 붙인 2 cm ArUco
마커**가 카메라에 정면일 때 전형적 X/Y 회전 모호성 아티팩트 발생.
통제된 실험은 아니지만 **실제 로봇팔 리그에서 이 실패 모드가 나온다는 직접 확인.**

### OpenCV API 📄
- `cv2.SOLVEPNP_IPPE_SQUARE`: *"suitable for marker pose estimation... requires 4 coplanar object
  points"* (특정 코너 순서 필요)
- `cv2.solvePnPGeneric`: *"allows retrieving **all the possible solutions**"*.
  다중 해 반환 가능 플래그: `SOLVEPNP_IPPE`, `SOLVEPNP_IPPE_SQUARE`, `SOLVEPNP_P3P`,
  `SOLVEPNP_AP3P`, `SOLVEPNP_SQPNP`
- ⚠️ **미확인**: 반환되는 재투영오차의 **정렬 순서/포맷 보장을 OpenCV 문서 자체에서 확인 못 함.**
  상류 IPPE 라이브러리의 문서화된 동작(정렬, 낮은 것 먼저)을 따를 것으로 **추정**되나
  OpenCV 문서 텍스트로 직접 확인되지 않음.
- 🗣️ 커뮤니티 우회책: `useExtrinsicGuess=true` (시간적 warm-start), "more points in different planes"

## 4.3 보드/번들이 단일 마커를 이기는 이유

### 메커니즘 (4개 독립 출처 수렴)

**(1) 지렛대(baseline/moment-arm) 논리** 🗣️ (Robotics Stack Exchange):
단일 사각 마커의 자세는 **좁은 영역의 4개 코너**에서만 나온다. 고정된 픽셀 국소화 오차(예: 1 px)가
만드는 각도오차는 **코너 간 거리에 반비례** — *"the angular error will be greater if the tag in
view is **20 pixels** across as opposed to **200**"*.

**(2) 점이 많으면 PnP 조건수가 좋아진다** 🔬 (Garrido-Jurado et al. 2014, ArUco 원전):
> *"more corner points... available for computing the camera pose, thus, the pose obtained is
> **less influenced by noise**"*

**(3) 모호성 파괴** — §4.2 참조. **이게 핵심이다.** 보드는 가우시안 노이즈를 조금 줄이는 게
아니라 **파국적 실패 모드(수십 도)를 제거**한다.

**(4) ChArUco 만의 추가 이점** 📄 (OpenCV 공식 튜토리얼):
> *"it is **highly recommended using the ChArUco corners approach** since the provided corners
> are **much more accurate** in comparison to the marker corners."*

메커니즘 (OpenCV ChArUco 코너 검출 튜토리얼): ArUco 마커 코너는 *"accuracy... **not too high**,
even after applying subpixel refinement"* (선형회귀 에지 피팅). 반면 체스보드 코너는
*"can be refined more accurately since **each corner is surrounded by two black squares**"*
(더 날카로운 saddle-point 그래디언트).

→ **ChArUco 는 두 가지 독립적 이유로 이긴다**: (a) 개별 코너가 본질적으로 더 정확하게 국소화됨,
(b) 코너가 훨씬 많고 넓은 영역에 퍼져 있음.

### 🚨 정량 갭 — 정직하게 밝힘

⚠️ **"보드가 단일 마커 대비 회전 RMSE 를 N배/N% 줄인다"는 깔끔한 수치가 문헌에 없다.**
**두 리서치 에이전트가 독립적으로 이 결론에 도달했다.** 통제된 "같은 태그, 같은 조건, 단일 vs
N-마커 보드, 양쪽 회전 RMSE" 연구가 발표된 적이 없어 보인다.

**가장 유망한 미확인 후보**: **Kallwies, Forkel & Wuensche 2020**, *"Determining and Improving
the Localization Accuracy of AprilTag Detection"* (IEEE, **49회 인용**). AprilTag3 /
AprilTags-C++ / ArUco-OpenCV 의 국소화 정확도를 직접 비교한다고 초록에 명시.
🚨 **IEEE Xplore 유료라 초록만 접근 가능.** **학교 IEEE 접근권이 있으면 이것부터 볼 것.**

🔬 **PMC12943937 (2026, ChArUco 자세 vs 시야각/거리)**: 보드의 이미지 footprint 가 거리에 따라
줄면 회전 **재현성**이 악화 (*"reduced board footprint... makes corner localization more
sensitive to pixel-level noise"*). ⚠️ **정확한 도/mm 값이 그림에 박혀 있어 텍스트 추출 실패** —
경향만 인용 가능. 필요하면 https://pmc.ncbi.nlm.nih.gov/articles/PMC12943937/ 직접 열람.

🗣️ **실제 예시** (diva-portal 학위논문): **~4 m 에서 단일 ArUco 마커 코너가 "zero to three
pixels" 정확도밖에 안 나와 거의 10 cm 오차** 유발. 저자 결론: *"if possible, **ChArUco markers
would be a better option**... [because ChArUco] contains a lot more line intersections... and
can return more points."*

### 📄 캘리브 품질 기준 (실무 게이팅용)
🗣️ OKLAB 블로그 + FRC 커뮤니티 (중간 권위, 커뮤니티 통념과 일치):
- ChArUco 캘리브 재투영오차: **< 0.3 px = good**, 0.3~1.0 px = acceptable,
  **> 1.0 px = 문제 있음** (보드 평탄도, 블러, 나쁜 코너)
- FRC 커뮤니티 실제 결과: ~0.5 px 가 전형
- 📄 OpenCV 커뮤니티 일반 지침: **자세별 재투영오차 < 1 px = good** ("depends on many factors")

## 4.4 크기 산정 🧮📄 — 두 리서치의 수치가 다름, 양쪽 보존

### 공식 📄
**Optitag** ("Designing the perfect Apriltag"):
> 검출 최소 태그 폭(px) ≈ **b × p**
> - `b` = 태그 폭을 걸치는 비트 수 (36h11: **b=8**, 25h9: b=6, tagStandard41h12: **b=9**)
> - `p` = 비트당 필요 픽셀 (**Nyquist 최소 = 2**, **권장 = 5** — *"to avoid detection pitfalls"*)

**Optitag 의 더 엄밀한 삼각함수 형태** (FOV 를 쓰므로 소각근사 불필요):
```
Max detection distance (m) = t / (2·tan((b·FOV·p)/(2·r)))
    t = 태그 한 변(m), b = 비트 수, FOV = 수평 화각, r = 수평 해상도(px), p = 비트당 px
```

**핀홀 기본형** (모두가 수렴하는 표준 관계):
```
L ≈ (목표_픽셀 × 거리) / 초점거리_px
f_px = f_mm × image_width_px / sensor_width_mm
```
⚠️ **이 표기 그대로 쓴 출처는 없다** — 표준적이고 논란 없는 핀홀 관계이며, 두 독립 출처
(Optitag 의 삼각형태, PMC6960891 의 센서 모델)가 대수적으로 동등한 형태를 사용함을 확인.

### 검출 임계 — 출처들이 잘 수렴 📄🗣️

| 출처 | 값 | 성격 |
|---|---|---|
| 🗣️ dsp.stackexchange | **2 px/bit (Nyquist)** — *"a 4×6 tag needs to be imaged at least at 8×12 pixels"* | 절대 하한, 안전 운용점 아님 |
| 📄 Optitag | **2 = Nyquist 최소**, **5 권장** | 36h11(b=8) → **16 px 하한 / 40 px 권장** |
| 🗣️ ChiefDelphi (FRC 실측) | *"detect the tags at 4 pixels per square or **32 pixels across** white-border-to-white-border... detection became unreliable after that"* | **실제 하드웨어 테스트** |
| 🔬 FMAC | STag **~40 px** 이하 실패, TopoTag **~50 px** 이하 실패 | 내부 구조가 더 많은 패밀리 → 일관됨 |
| 🔬 Olson 2011 | 실험에서 **49~100 px** 사용 | 운용 범위 |

→ **32 px (실측) 과 40 px (벤더 안전마진) 이 서로를 잘 감싼다. 검출은 32~40 px.**

⚠️ **AprilRobotics 공식 README/wiki 에는 최소 픽셀 지침이 없다** (부재 확인).
`tagsize`, focal length, `SOLVEPNP_IPPE_SQUARE` 만 문서화. **위 숫자들은 전부 커뮤니티/벤더/포럼
출처지 AprilRobotics 자체가 아니다.**

### 🚨 자세 정확도 임계 — 권위 있는 출처 없음, 두 에이전트 추정치가 다름

**양쪽 다 "이건 내가 합성한 추정치다"라고 명시했다.**

| 리서치 | "좋은 자세" 픽셀 추정 | 근거 |
|---|---|---|
| **리서치 A** | **~100~150 px** | 검출 권장의 2~3× + OpenMV 실사례 갭 |
| **리서치 B** | **~60~120 px** (80 px 를 "floor, not ceiling" 으로) | FMAC 역산(18~54 px), Robotics SE 의 20-vs-200 px 예시 |

**양쪽이 공통으로 말하는 것**:
- 자세 정확도 임계는 검출 임계보다 **상당히 높다** — 이건 모든 출처가 정성적으로 동의
- **연속적 SNR 관계지 절벽이 아니다** — *"the bigger the tag, the more data we obtain... the
  better the position of the estimate"* (dsp.stackexchange)
- 🗣️ **핵심 뉘앙스** (Stack Overflow): 물리 크기를 키우는 건 **사용 가능 거리 범위를 이동시킬
  뿐**, 주어진 겉보기(픽셀) 크기에서의 정확도를 "고치는" 게 아니다. **중요한 건 cm 가 아니라
  프레임 내 픽셀 수.**

🗣️ **현실 점검 — 이론적 최소치의 함정** (OpenMV 포럼): 60~80 cm 에서 **8 cm 태그**를
320×240 센서로 (= 40 px "권장" 임계를 훨씬 넘김) 썼는데도 **~10 mm** 위치 정확도밖에 안 나옴.
기대했던 sub-pixel/2~3 mm 가 아니었다.
→ **픽셀 수 최소치는 *검출*용이고, 실제 *자세* 정확도는 훨씬 큰 여유 + 좋은 초점/조명/캘리브가 필요.**

### 우리 리그 계산 (1280×720, f_px ≈ 700, D = 2~3 m)

**리서치 B 의 표** (3 m 를 구속 조건으로 보수적 계산):

| 목표 | P (px) | L @ 2 m | L @ 3 m |
|---|---|---|---|
| Nyquist 하한 (맥락용, 운용점 아님) | 16~24 | 4.6~6.9 cm | 6.9~10.3 cm |
| **검출만**, 실전 신뢰 (ChiefDelphi 32 + Optitag 40) | 32~40 | **9.1~11.4 cm** | **13.7~17.1 cm** |
| **좋은 자세**, 검출 하한의 2~3× 합성 | 80~120 | **22.9~34.3 cm** | **34.3~51.4 cm** |

계산 예시: 검출만 @ 3 m, P=40 → L = 40 × 3.0 / 700 = 0.1714 m ≈ **17.1 cm**

**리서치 A 의 표** (더 보수적):

| 목적 | 필요 픽셀 | L @ 2 m | L @ 3 m |
|---|---|---|---|
| 검출만 | 16~40 px | 46~114 mm | 69~171 mm |
| 정확한 자세 | ~100~150 px | **286~429 mm** | **429~640 mm** |

**→ 두 표가 검출에서는 일치, 자세에서는 리서치 A 가 더 보수적.
공통 결론: 단일 태그로 2~3 m 자세를 제대로 하려면 한 변 30~64 cm.**

### 벤더/커뮤니티 실제 값으로 교차검증 🗣️
- **FTC 공식 대회 필드** (수 미터 규모) 기본 AprilTag 크기: **4 in (10.2 cm)**, **6 in (15.2 cm)**
  → 위 "검출만" 9~17 cm 대역에 정확히 들어감 ✅ 안심됨
- **laserscanning-europe** 측정 표: **10×10 cm AprilTag 이 좋은 시야각에서도 ~2~3 m 까지만**
  신뢰성 있게 검출 → "검출만 @ 3 m" 의 저역과 대체로 일치 (약간 짧음, 다른 카메라/패밀리)

### 🚨 개별 태그 크기 — 다점 데이텀의 숨은 제약

**리서치 B 의 핵심 지적**: 다점 데이텀이라고 **개별 태그를 작게 만들 수는 없다.**
각 태그는 여전히 **독립적으로 ID 디코딩**이 돼야 하므로 검출 임계(32~40 px)를 각자 넘어야 한다.

> **→ 3 m 에서 개별 태그가 14~17 cm 는 돼야 한다.**
> 정확도는 개별 태그 크기가 아니라 **점들의 총 스팬**에서 나온다.
> **구체적 제작 스펙: 한 변 15 cm 태그 4장을 80 cm 이상 벌려서 배치.**

⚠️ **ChArUco 는 체커보드 코너 검출이 전체 ID 디코딩보다 낮은 해상도로도 될 수 있다**고 여러
출처가 시사하지만 **정량화한 출처가 없다.** → **ArUco 다점이 더 안전한 선택** (각 태그가
독립적으로 디코딩되므로 요구사항이 명확함).

### 🚨 안전 마진에 대해
⚠️ **"공식에 X% 마진을 더해라"고 말하는 출처는 없다.** 가장 가까운 등가물은 Optitag 의 `p`
파라미터 — **권장 p=5 가 Nyquist 하한 p=2 대비 이미 2.5× 마진**이며, 정확히 안전계수처럼 동작한다.

### 🚨 목표치(5 mm / 1° @ 2~3 m) 자체가 미검증
⚠️ **두 리서치 모두 독립적으로**: *"fiducial 단독 monocular PnP 로 2~3 m 에서 5 mm/1° 를
달성했다는 출처를 찾지 못했다."*
문헌은 그 거리에서 **cm 급**을 시사한다 (PMC6960891 근거리, diva-portal 4~6 m, FMAC 0.5~1.5 m
모두 거리에 따라 병진오차가 대략 선형 증가).
→ **다점 데이텀 + 리그 삼각측량을 택하는 이유지만, 목표치 자체가 실측 검증 대상이다.**

## 4.5 🚨 태그 크기 측정 함정 — 이 문서 최대의 단일 오차원

📄 **3개 독립 출처에서 발견** (ROS robotics.stackexchange, MoveIt Pro 문서, chaitanyantr
AprilTag 생성기 툴):

> **태그 크기는 "검은 검출 사각형만" 재야 한다. 흰 여백(quiet zone)을 제외한다.**

🗣️ **실제 사고**: 한 ROS 사용자가 바깥 종이 크기를 넣어서 **< 2.4 m 거리에서 0.3~0.35 m
위치 오차**. **이 문서에서 논의된 거의 모든 다른 오차원보다 크다.**

**→ 구현 시 전용 안전 검사를 둘 것.**

## 4.6 라이브러리 현황 (2025~2026) 📄

### OpenCV `cv2.aruco`
- 🚨 **`estimatePoseSingleMarkers()` 는 OpenCV 4.7.0 에서 제거됨.**
  대신 `cv2.solvePnP()` 직접 호출 (`SOLVEPNP_IPPE_SQUARE` 와 함께).
  OpenCV 의 명시된 이유: **마커 로컬 좌표계를 완전히 제어**할 수 있게 (고정 규약 대신).
- API 가 같은 시기에 클래스 기반 **`cv2.aruco.ArucoDetector`** 로 이동.
- 모듈이 `opencv_contrib` → 메인 저장소 `objdetect` 로 **2022-12** 경 이동.
- 🚨 **이 전환이 깨뜨린 것들**: OpenCV 포럼 스레드가 **4.6/4.7 사이에 마커 좌표계 Z축 규약
  자체가 바뀐 것**을 문서화.
- ⚠️ **OpenCV 4.10.0 (2024-10) 및 2025 까지도** Python `ArucoDetector` 가 `detectBoard`/
  전체 ChArUco 를 C++ API 만큼 지원하지 않는다는 사용자 보고. 라이브 버그 스레드 다수
  (`CharucoDetector.detectBoard returns NoneType`; **2025-08** Charuco 몇 mm 오차 스레드).
- 📄 **확인된 우회책**: **`opencv-contrib-python` 을 설치할 것. `opencv-python` 말고.**
  후자의 내장 objdetect 를 사용자들이 *"quite buggy"* 로 묘사.
- ⚠️ **2026 중반 최신 릴리스에서 이 Python 갭이 고쳐졌는지는 확인 못 함** — **설치본으로 실측할 것.**

### 앞으로 📄
**OpenCV GitHub RFC #28953** (2026 SoftwareX 논문 "ArUco Nano" 참조): OpenCV 5.0 용
**"ArUco 2.0" / `aruco2` 모듈** 전면 재작성 제안 —
**최대 6.5× 빠른 검출** (1MP: 6.68 ms vs 현재 43.46 ms), 단순한 자유함수 API, id+corner 통합
결과 타입, 한 번의 호출로 다중 dictionary 검출, ChArUco2/Diamond/FractalMarker 일급 지원.
⚠️ **제안 단계, 아직 미출시.** → **aruco API 표면이 또 바뀔 신호. 버전을 신중히 고정할 것.**

### AprilRobotics `apriltag` (C)
- 📄 **활발히 유지보수**: 473 커밋, **v3.4.5** 까지 릴리스, 다중 기여자
  (christian-rauch 포함 — ROS2 래퍼도 그가 유지)
- README 가 **tagStandard41h12** 를 기본 권장
- **공식 Python 래퍼 `apriltag_pywrap.c` 를 메인 저장소에 동봉**
- 🗣️ **반대 의견 1건** (FRC/ChiefDelphi): 내부 C 코드가 *"rather low quality... messy... not
  that performant"*. 신뢰할 만하지만 비공식적인 엔지니어링 불만이지 유지보수 상태 주장은 아님.

### Python 래퍼
- **`pupil-apriltags`**: AprilRobotics C 소스 래핑 (`pupil-labs/apriltags-source` 벤더링).
  `v1.0.4.post8` 까지 주기적 릴리스 — **기능 개발보다 패키징/휠 재빌드 성격**
- **`duckietown/lib-dt-apriltags`**: 비견할 만한 활발한 대안. 깔끔한 `Detector` 클래스가
  `pose_R`, `pose_t`, `pose_err` 를 직접 반환

### ROS2
- 🚨 **원본 `AprilRobotics/apriltag_ros` 에 병합된 1st-party ROS2 포팅은 없다**
  (PR #114 "ros2 porting" 이 있으나 Discourse 스레드에 따르면 논쟁 중)
- 📄 **커뮤니티 표준은 `christianrauch/apriltag_ros`** — 문자 그대로의 포팅이 아니라 **ROS2
  전용 재작성**. 154 커밋, 활발히 유지보수. **공식 ROS build farm 에 빌드/릴리스됨**:
  `ros2-gbp/apriltag_ros-release` 로 확인, **Humble·Jazzy 양쪽에 v3.3.0 (2025-08-29)** 까지 릴리스
- 소규모 대안 `Adlink-ROS/apriltag_ros` (29 stars, 12 커밋) — 훨씬 덜 활발

### TagSLAM
- 원본 ROS1 (Pfrommer & Daniilidis, arXiv:1910.00679) — GTSAM 팩터그래프 프론트엔드
- 📄 현재 저장소 `berndpfrommer/tagslam` 명시: **"ROS2 is WORK IN PROGRESS. Documentation will
  follow. At the moment TagSLAM requires ROS2 Rolling/Jazzy or newer."**
  → 살아있고 활발히 ROS2 포팅 중이나 (Jazzy = 2024-05, 최근 작업) **본인 인정상 아직 다듬어진
  ROS2 릴리스는 아님.** **ROS2 에서는 "쓸 수 있지만 거침" 으로 취급.**

## 4.7 다중 태그 맵 (tag bundle) 📄

### `apriltag_ros` tag bundles
- 📄 **일급 문서화 기능.** 번들 = 이름 붙은 태그 그룹, 각각 공유 원점 대비
  `{id, size, x, y, z, qw, qx, qy, qz}` 를 부여 (실제 `tags.yaml` 예시로 스키마 확인)
- **번들 태그의 *임의 부분집합*만 검출돼도 번들의 6-DoF 자세가 나온다**
- 📄 **AprilRobotics 저장소가 `calibrate_bundle.m` 을 동봉** — 선택한 "master" 태그 대비
  각 태그의 강체변환을 여러 프레임에 걸친 camera→tag 변환 체이닝 + 평균으로 계산하는 MATLAB
  스크립트. **= 이게 바로 1회 번들 캘리브 워크플로이고 공식적으로 제공된다.**
- ⚠️ Optitag 블로그의 "AprilTag-ROS 는 AprilTag 2 패밀리만 지원" 주장은 **낡았을 수 있음** —
  활발히 유지보수되는 ROS2 포크는 링크된 apriltag C 라이브러리 버전을 따르고, 그건 이제
  tagStandard41h12 가 기본. **확인 못 함 / 낡았을 가능성으로 표시.**

### TagSLAM 🔬
arXiv:1910.00679 — GTSAM 팩터그래프 프론트엔드, 이 용도로 명시적 설계:
*"full SLAM, extrinsic camera calibration with **non-overlapping views**, visual localization
for ground truth, loop closure... etc."* — "bodies/tags/cameras" 추상화.
⚠️ **구체적 정확도 수치를 추출하지 못함.**

### 학술 다중 마커 매핑 🔬
**Muñoz-Salinas et al. 계열** (직접 관련):
- *"Mapping and Localization from Planar Markers"* (arXiv:1606.00151) — `aruco_mapping` 계열 툴의 원전
- *"UcoSLAM"* (arXiv:1902.03729) — 키포인트 + 평면 마커 융합
- *"Smart Artificial Markers for Accurate Visual Mapping and Localization"* (PMC7830840)
⚠️ **구체적 mm/deg 수치를 추출하지 못함.**

🔬 **"Scalable Fiducial Tag Localization on a 3D Prior Map"** (arXiv:2207.11942, IROS 2022):
**글로벌 태그맵 정합 성공률 98%** 보고.
⚠️ **평균 태그 자세 정확도 수치는 추출 실패** (모든 출처에서 잘림).

🔬 **Improved Pose Estimation of Aruco Tags Using a Novel 3D Placement Strategy** (PMC7506853)
— ArUco 그리드보드 벤치마크 방법론 (참조만, 깊이 인용 안 함)

### 🚨 안전 관련 주의 — 지렛대의 양날 🗣️
OpenMV 포럼 (비공식이나 기하학적으로 타당):
**태그 자세의 회전오차는 태그와 실제 관심점(예: 로봇 베이스 원점) 사이의 지렛대에 의해 증폭된다.**
태그를 베이스 원점에 정확히 붙일 수 없다면, **오프셋을 최소화하거나 명시적으로 캘리브/모델링**할 것.
**"안전 관련" 프레임에서는 이게 raw 태그 자세 노이즈보다 더 중요하다.**

## 4.8 스테레오 vs 모노큘러 — 뉘앙스 있음, 단순한 답 아님

### ZED Mini 공식 스펙 📄 (**우리 카메라 정확히**)
> **depth 정확도 "< 1.5% up to 3 m, < 7% up to 15 m"**

→ **2 m 에서 최대 30 mm.** 1 m 에서도 ~15 mm. **depth map 만으로는 5 mm 목표의 3~6배 나쁨.**

⚠️ **혼동 주의**: ZED-M 스펙의 **±1 mm / 0.1°** 는 **visual-inertial positional tracking**
(ego-motion) 수치지 정적 장면 depth map 정확도가 **아니다**. 태그 코너의 depth 를 depth map
에서 읽어서 얻는 값이 아니다.

📄 Stereolabs 일반 문서: depth 오차는 **거리에 2차식**으로 증가, **저텍스처 면에서 추가 악화**.

### 모노큘러가 이길 수 있다는 근거 🧮
⚠️ **ChArUco-PnP vs ZED-depth 를 직접 head-to-head 벤치마크한 연구를 찾지 못했다.**
위 ZED 스펙 + FMAC/TopoTag 의 monocular PnP mm/sub-degree 수치를 조합한 **추론**이지
직접 인용된 비교 연구가 아니다.

### 🚨 반대 증거 — 정직하게 제시 🔬
**Azad et al. (KIT), "Stereo-based vs. Monocular 6-DoF Pose Estimation"**:
> *"the monocular approach **suffers from instabilities for planar objects** in the presence of
> skew and... the **stereo-based approach achieves a significantly greater depth accuracy at far
> distances**."*

**반론**: (a) **2009년** 논문으로 IPPE 와 현대 ChArUco 툴링 이전, (b) 일반 물체(fiducial 보드가
아닌) 소수 특징점 평면 타겟 대상 — **즉 정확히 모호성에 취약한 영역**이고, 제대로 설계된 큰
보드가 고치려는 바로 그 문제(§4.2/§4.3)이지, 적절히 크기 잡은 ChArUco 보드 대비 벤치마크가 아니다.

### 🔬 중간 경로 — depth 의 진짜 가치
**Jin et al.** RGBD 융합 연구: depth 의 실제 가치는 **나쁜 조명 구제 + flip 해소**다.
- depth 융합 시 **"unacceptable pose" 비율이 최저 조도에서 25% → 3%** 로 감소
- 위치 정확도는 RGB-only 대비 **~2 cm** 개선
→ **depth 는 정밀도의 주 원천이 아니라 *해소/강건성 보조* 로 쓸 때 가장 유용하다.**

### 🔬 결정적 뉘앙스 — "스테레오를 쓴다"의 두 의미
**MarkerPose** (arXiv:2105.00368):
- **(a)** 카메라 내장 dense depth map 읽기 → ZED 의 1~7%-of-range 노이즈 바닥에 종속
- **(b)** **좌/우 rectified 이미지에서 같은 태그 코너를 각각 독립 검출해 그 점만 직접 삼각측량**
  → **dense stereo 알고리즘을 완전히 우회**

**(b) 가 소수의 잘 국소화된 특징점에 대해서는 벤더 depth map 보다 의미 있게 정밀하다.**
단, 커스텀 엔지니어링 필요 (우측 이미지 독립 검출 + 삼각측량). `zed.retrieveMeasure(DEPTH)`
읽는 것과는 다르다.

> **→ 우리 "리그 교차 삼각측량"(2.18 m 베이스라인)은 (b) 를 두 카메라 사이에 적용하는 것이다.**

### 종합 권고
**rectified left 이미지의 monocular PnP (`SOLVEPNP_IPPE_SQUARE`/ChArUco)를 주 자세 원천으로.**
ZED depth map 은 잘해야 거친 sanity-check / 초기 추정 / 나쁜 조명에서 flip 해소용 폴백.
**정확도 경로에 두지 말 것** — 벤더가 공표한 ≥1.5%-of-range 오차 예산 때문.

## 4.9 안정화 기법 📄🔬

### 회전 평균 — 정본 🔬
**Markley, F.L., Cheng, Y., Crassidis, J.L., Oshman, Y., "Averaging Quaternions,"
Journal of Guidance, Control, and Dynamics 30(4):1193–1197, 2007** (직접 읽음):

```
M = Σ wᵢ · qᵢ · qᵢᵀ
평균 쿼터니언 = M 의 최대 고유값에 대응하는 고유벡터 (정규화)
```
가중 자세행렬 차의 Frobenius 노름 제곱합(chordal distance 기준)을 단위노름 제약 하에 최소화.
**표준·널리 구현됨** (`quatWAvgMarkley`).

> 🚨 **오일러각을 순진하게 평균내지 말 것. 쿼터니언 성분을 독립적으로 평균내지도 말 것.**

### SO(3) / Fréchet 평균 🔬
**Hartley, Trumpf, Dai, Li, "Rotation Averaging," IJCV 2013** — 표준 서베이.
geodesic(진짜 Riemannian/Karcher) 평균과 더 단순하고 널리 쓰이는 **chordal L2 평균** 근사,
수렴 알고리즘(Weiszfeld, Manton 의 Lie-group 그래디언트).

**Outlier-robust 변형** (arXiv:2004.00732, arXiv:2309.05388): 원소별 median 또는 truncated
chordal L2-mean 으로 초기화 → 반복 재가중/거부 (Weiszfeld 식 L1 평균).

### 6-DoF 전체 평균 🔬
**"On the Computation of Mean and Variance of Spatial Displacements"** (PMC11348399) —
강체 변위(병진+회전 동시) 평균을 직접 연구, 오일러각/단위쿼터니언/듀얼쿼터니언 파라미터화 비교.
→ 우리 관심 대상이 회전만이 아니라 **전체 6-DoF camera→tag 변환**이라 관련.

### 매니폴드 인식 시간 필터링 🔬
**PMC6339217** ("Kalman Filtering for Attitude Estimation with Quaternions and Concepts from
Manifold Theory") — 쿼터니언 성분을 독립적으로 필터링하지 말고 **multiplicative/manifold-aware
칼만 필터**를 쓸 것. 평균 지침과 같은 원리를 재귀 필터에 적용.

### 응용 파이프라인 전체 예시 🗣️
**Padova 대학 학위논문** (Montecchio, 다중 AprilTag 맵 UAV 위치추정) — 정확히 이 스택 구현:
가중 IQR 식 outlier 거부("HYB-OR") + chordal-L2 회전평균("QL2-AVG") + FIR 시간필터.
**ablation 테스트에서 이 조합이 최고 위치+자세 정확도.**
🗣️ 학위논문(중간 권위)이나 직접적으로 온-포인트.

### 재투영오차 게이팅 📄
- 자세별 재투영오차 **< 1 px** 를 프레임 게이트로 사용해 평균 전에 outlier 검출 거부
- **IPPE 두 해의 재투영오차 격차**를 써서 모호한 프레임을 거부/플래그
  → **flip 위에서 맹목적으로 평균내는 것을 방지** (§4.2)

### 시작 프레임 수 ⚠️
⚠️ **fiducial 마커 전용 출처가 확정적 숫자를 주지 않았다.**

가장 가까운 유사(그리고 기초적인) 출처: 🔬 **Tsai & Lenz 1989** — 비체계적(노이즈) 오차는
station/프레임이 늘수록 대략 감소하고, 그들 결과표에서 **~10 station** 이면 이미 로봇 자체의
위치결정 정확도 바닥(~14 mil ≈ 0.36 mm) 아래로 병진오차가 내려감.

🗣️ **Zivid hand-eye 가이드**: **10~20 자세**, 작업공간 전반, 다양한 관절 구성.

🗣️ **Mech-Mind 커뮤니티 반례**: **30개의 잘못 분포된 자세 → ≈4 cm** vs 더 적고 잘 분포된
세트 → **≈5 mm**. → **자세 다양성이 개수만큼(또는 그 이상) 중요.**

**정적 단일 태그/보드 설치**(카메라도 태그도 고정 = hand-eye 보다 단순, 동시에 풀 미지 결합변환
없음)에 대해서는 **수 초~수십 초 프레임(30 fps 에서 30~100+)을 outlier 거부와 함께 평균**이
문헌과 일관된 합리적 목표. ⚠️ **단, 이걸 직접 말한 fiducial 자세 전용 논문은 없다** —
hand-eye 캘리브 문헌에서의 **외삽**이지 직접 인용이 아니다.

---

# §5. Markerless 및 대안 정합 🔬

## 5.1 Markerless 로봇 자세 추정 (로봇 자신의 외형에서)

**성격**: 실제 연구 흐름이고 동작하는 코드도 있지만, 타겟이 **manipulation/RL 데이터
파이프라인용 로봇 self-calibration** 이지 **안전등급 정합이 아니다.**

| 방법 | 발표 | 필요한 것 | 보고 정확도 | 코드 |
|---|---|---|---|---|
| **DREAM** (NVIDIA) | ICRA 2020 | 관절각 + FK + intrinsic; **로봇별 네트워크**를 합성 도메인 랜덤화로 학습; PnP 에 ≥4 키포인트 | GT 캡처 노이즈만 1.6~2.9 mm; DREAM-real 벤치마크에서 변형별 **~17 mm (DREAM-H) ~ ~113 mm (DREAM-F)** 평균 ADD. 저자 주장: *"comparable to classical hand-eye calibration"* | [NVlabs/DREAM](https://github.com/NVlabs/DREAM) |
| **RoboPose** | CVPR 2021 | render-and-compare 반복 최적화; CAD/URDF | **~20 mm** 평균 ADD | 🚨 **1~1.8 FPS** — 저자가 명시적으로 실시간 불가 |
| **CtRNet** | CVPR 2023 | self-supervised sim-to-real, 미분가능 렌더링, 실제 3D 라벨 불필요 | ~20 mm | [ucsdarclab/CtRNet](https://github.com/ucsdarclab/CtRNet-robot-pose-estimation) |
| **CtRNet-X** | 2024 | **부분 가시성** 대응 (로봇이 프레임 안팎 이동); VLM 기반 부품 검출 | **~14 mm** (최고); DROID in-the-wild 0.84 IoU | [arxiv 2409.10441](https://arxiv.org/html/2409.10441v1) |
| **SGTAPose** | CVPR 2023 | 구조적 prior + 시간 attention (단일 프레임 아님) | ⚠️ 미추출 | [Nimolty/SGTAPose](https://github.com/Nimolty/SGTAPose) |
| **RoboKeyGen** | ICRA 2024 | diffusion 3D 키포인트 생성; **관절각 몰라도 됨** | ⚠️ 미추출 | [Nimolty/RoboKeyGen](https://github.com/Nimolty/RoboKeyGen) |
| **HoRoPose** | ECCV 2024 | 관절각 가정 불필요; 단일 feed-forward | **AUC 82.2** (vs DREAM-F 68.9, RoboPose 70.4); **44 ms / 22.6 FPS** (vs RoboPose 570 ms / 1.8 FPS) — **첫 실시간 holistic** | [Oliverbansk/HoRoPose](https://github.com/Oliverbansk/Holistic-Robot-Pose-Estimation) |
| **FEEPE** | 2025 | EE 의 CAD; **training-free**, foundation feature 매칭, 크로스로봇 일반화 | ⚠️ *"high-accuracy hand-eye calibration 에 적합"* 주장 (미확인) | [tianshuwu/feepe](https://github.com/tianshuwu/feepe) |
| **Kalib** | 2024 | visual foundation model 로 **단일 기준점** 추적 (CAD 불필요, 로봇별 재학습 불필요) — **점 기반**, §5.3 과 연결 | ⚠️ 마커 기반과 비슷하다 주장 (미확인) | [robotflow-initiative/Kalib](https://github.com/robotflow-initiative/Kalib) |
| **MonoSE(3)-Diffusion** | 2025 | diffusion SE(3) 자세 정제 | ⚠️ 미추출 | ⚠️ 코드 가용성 미확인 |

### 🚨 성숙도 판정
**연구 등급이지 안전-프로덕션 등급이 아니다.**
1. 모든 방법이 **로봇 자신의 몸**을 캘리브 대상으로 삼는다 — ISO/TS 15066 이 함의하는 인증된
   정확도로 **외부의, 처음 보는 융합 스켈레톤**을 로봇에 정합하는 건 아무도 안 한다.
2. 깨끗한 벤치마크에서 **최고 실시간 정확도가 ~14~20 mm** — **우리 카메라 자체의 depth/자세
   노이즈를 더하기 전** 수치다.
3. 🚨 **전부 `camera→robot` 을 캘리브한다. 우리가 필요한 건 `융합스켈레톤(이미 다중카메라
   프레임에 있음) → robot` 이다.** 추가 합성 단계가 필요하다.
4. **~14 mm 는 우리가 고전 방법으로 얻을 수치보다 나쁘다** (§3.7, §6 참조).

## 5.2 터치 프로빙 / TCP 기반 정합 🔬

**고전 산업 방식**: TCP 를 알려진 점 N개로 조그 → FK 로 로봇측 좌표 기록 → 강체변환 해.

- 🗣️ **4-point 법이 표준**; 8~12점 최소제곱이 노이즈를 평균화
  (industrialmonitordirect.com)
- 🗣️ **현장 정확도**: **±0.5 mm (4-point TCP 포인터)**, **< 0.1 mm 면 캘리브 양호**,
  **반복도 ≤ 0.1 mm**
- 📄 **카메라가 볼 수 있는 점을 TCP 로 찍는 변형** = Mech-Mind 상용 **"TCP touch"** eye-to-hand
  워크플로가 정확히 이것 (docs.mech-mind.net)

**솔버** 🔬: **Kabsch / Umeyama / Horn 은 기능적으로 같은 absolute orientation 폐형해**
(최소 3개 비공선점, 여유분은 더). **`cv2.estimateAffine3D`** 가 이 문제의 표준 OpenCV
RANSAC-robust 구현이며, 🗣️ 실제로 **다중 카메라 body-tracking extrinsic 캘리브**에 쓰인
사례가 있다 (drmu.net) — **우리 ZED-Fusion→robot 단계와 직접 유사.**

## 5.3 ⭐ 위치-only / 구슬-on-EE 트릭 — 진짜 기법이지 편법이 아니다

> **이 절이 §5 에서 가장 중요하다.** 설계 문서의 핵심 판단(위치-only)의 근거다.

### 📄 CMU Robotics Knowledgebase — "Camera-Robot Registration Using Horn's Method"
(roboticsknowledgebase.com/wiki/math/registration-techniques/)

**절차**:
1. EE 에 **색 구슬(colored bead)** 부착
2. 작업공간과 카메라 FOV 를 아우르는 **5~6개 점**으로 로봇 이동
3. **스테레오** 이미지에서 HSV 로 구슬 분할
4. 3D 중심 삼각측량, **여러 프레임 평균**
5. FK 로 알려진 로봇 프레임 좌표와 짝지음
6. **Horn's method** 로 `T_camera↔robot` 해

**원전**: Zevallos et al. 2018 (da Vinci 수술로봇 AR 시스템), 코드
[gnastacast/dvrk_vision](https://github.com/gnastacast/dvrk_vision).
→ **스테레오 카메라가 로봇 작업공간을 내려다보는 구조 = 우리와 구조적으로 거의 동일.**

### 🔬 Đalić et al. 2024 — 왜 이게 통하는지 형식화
*"Submillimeter-Accurate Markerless Hand–Eye Calibration Based on a Robot's Flange Features"*
([PMC10892941](https://pmc.ncbi.nlm.nih.gov/articles/PMC10892941/))

- **translation-only 폐형해가 full-pose 해보다 더 정확하고 강건**
- **캘리브 대상을 단일 3D 점으로 줄이면 자세추정 오차의 영향이 최소화**된다
- **결과: 4개 비공면점만으로 서브밀리미터**, 기존 SOTA 대비 **~4배 개선**
- ⚠️ **단, 3D 스캐너 사용 — 스테레오가 아니다.**

### 🔬 Klimchik et al. — 통계적 근거
*"Advanced robot calibration using partial pose measurements"* ([arXiv:1311.6677](https://arxiv.org/abs/1311.6677))
(다른 과업이지만 같은 원리, kinematic calibration 쪽에서의 논거)

> **위치(mm)와 자세(도) 잔차를 하나의 최소제곱 목적함수에 섞는 것은 *비동차
> (non-homogeneous)* 이며 통계적으로 부적절하다.** 여러 기준점의 Cartesian 점 측정만
> 사용하면 이를 회피하고 식별 정확도가 개선된다.

→ **"위치-only 는 편해서가 아니라 실제로 *더 나은* 것"의 형식적 정당화.**

### Kalib (§5.1) = 같은 아이디어의 현대적 딥러닝 화신
색 구슬 대신 foundation model 로 기준점 하나를 추적.

### 🗣️ 리서치 에이전트의 종합 판정
> **구슬/구체-on-EE + Horn/Kabsch 가 우리에게 가장 잘 맞고 리스크가 낮은 기법이다.**
> - 당일 구현 가능한, 문서화가 잘 된, 수십 년 된 방법
> - **스테레오 카메라 참조 구현이 직접 유사** (Zevallos/dvrk_vision)
> - **6-DoF 마커 자세 문제(원거리 스테레오에 어려움)를 순수 3D 점 문제로 변환**
> - "로봇을 N개 점으로 조그, 카메라+FK 기록, 강체변환 해" = **매 세션 재실행이 자명하게 쉽다**
>   (🗣️ samarth-robo 블로그: MoveIt Calibration 이 *"record joint states...then play them back
>   to re-calibrate later if you move your camera"* 지원)

## 5.4 Depth / 포인트클라우드 ICP 🔬

### 🔬 가장 직접 관련 있는 연구: LRBO
Li et al., *"Automatic Robot Hand-Eye Calibration Enabled by Learning-Based 3D Vision"*
([arXiv:2311.01335](https://arxiv.org/html/2311.01335v3), 코드 [leihui6/LRBO](https://github.com/leihui6/LRBO))

- **로봇 베이스(또는 팔) 자체를 캘리브 대상으로**: PV-RCNN++ 로 로봇 포인트클라우드 검출/크롭
  → PREDATOR + ICP 로 참조 포인트클라우드 모델에 정합
- **결과: 병진 편차 0.930 mm, 회전 편차 0.265°**, 3D 재구성 위치오차 1.697 mm,
  **로봇 1회 이동, < 1~6초**
- 🚨 **그들이 "비교군 중 가장 부정확하다"고 명시한 저가 depth 카메라로** 달성

### 🚨 그런데 왜 우리한테는 안 되나
- 📄 **ZED Mini: depth < 1.5% up to 3 m** → **2~3 m 에서 30 mm+ 원시 노이즈**
- 🔬 LRBO 와 Đalić 이 쓴 건 **구조광/ToF** — 우리 스테레오보다 한 자릿수 정확
- 🧮 **평균화 논리**: 로봇 팔 표면 수백 점에 대한 ICP 는 오차가 **불편(unbiased)이면** 대략
  `1/√N` 로 이길 수 있다. **그러나 스테레오 depth 오차는 알려진 대로 체계적·거리의존 편향**을
  가진다 (Ortiz et al. 2018 의 널리 인용되는 ZED depth 오차 모델 — ⚠️ 깊이 검토 안 함).
  **편향은 깔끔하게 평균화되지 않는다.**
- ⚠️ **ZED 기반 CAD-ICP 현실 기대치**: 무거운 평균화로 최선 low-single-digit mm, 현실적으로
  **~1 cm 급**. 🚨 **그러나 이를 확인해 줄 ZED 특정 ICP-to-robot-base 발표 결과를 찾지 못했다** —
  **공개된 갭.**

### 🔬 일반 ICP/CAD 정합 정확도
Denayer et al. 2024 ([mdpi.com/1424-8220/24/7/2142](https://www.mdpi.com/1424-8220/24/7/2142)):
CAD-to-scan 정합 6개 기법 비교. **GO-ICP 가 최고 정확도지만 수 초 소요**, 다른 방법들은 < 1초.

---

# §6. HRC 안전 / ISO-TS 15066 — 오차가 어떻게 전파되나 🔬

> **이 절이 CBF 층과의 접점이다.** 정합 오차를 왜 측정해야 하는지의 근거.

## 6.1 주 출처
**Marvel & Norcross (NIST), "Implementing Speed and Separation Monitoring in Collaborative
Robot Workcells"** ([PMC5117641](https://pmc.ncbi.nlm.nih.gov/articles/PMC5117641/))
— **ISO/TS 15066 SSM 의 사실상 레퍼런스 구현 가이드.**

## 6.2 🚨 핵심 — Z_R / Z_S 는 가산항이다

**ISO/TS 15066 최소보호거리 식은 다음을 명시적으로 포함한다**:
- **`Z_R`** — 로봇 위치 불확실성
- **`Z_S`** — 작업자/센서 위치 불확실성
- **`C`** — 침입 거리

**세 항 모두 안전마진 합에 *가산적으로* 들어간다.**

> **→ 카메라-로봇 정합 오차는 필요 분리거리를 *그대로 1:1 로 늘리도록* 설계돼 있다.**
> 곱셈으로 할인되지도, 필터링으로 상쇄되지도 않는다.

## 6.3 🚨 그런데 목표치를 정한 표준이 없다
📄 **NIST 논문 원문**:
> *"**no standard currently exists** for human localization or pose-estimation measurement
> uncertainty."*

**논문이 제시하는 폴백**:
- `Z_S` 를 **반응시간/지연 측정의 표준편차 × 가정한 인간 속도**에서 유도
- 또는 가장 가까운 센서 클래스 표준을 대입 (예: 광전자 방호장치의 **IEC 61496**)
  — 인간 특정 표준이 나올 때까지

**`Z_R`** (로봇 불확실성): **ISO 9283** 으로 평가하거나 **ASTM E2919-14** (6-DOF 정적 자세 측정
표준) 로 검증.

> **→ 정합 정확도의 codified 목표치는 없다. 통합자의 리스크 평가 몫이다.**

## 6.4 지연 = 마진의 직접 손실
📄 논문이 명시: protective-stop 이벤트가 지연 보고되면 오차가 **(속도 × 지연)** 만큼 분리거리를
1:1 로 먹는다. 예: **2000 mm/s 인간을 0.5 s 늦게 보고 → 1000 mm 마진 손실.**

**같은 논리가 정적 정합 편향에도 적용된다: SSM 식이 계산한 값에 더해지는 상수 오프셋.**

## 6.5 ⚠️ 문헌 갭 — 정합오차 → 안전거리 민감도 분석이 없다
🚨 **"camera-to-robot registration error → required SSM separation distance" 를 그 자체로
연구한 형식적 민감도 분석 논문을 찾지 못했다.**
NIST 논문이 **메커니즘**(가산 `Z_R`/`Z_S`)을 확립하지만 **정합오차-vs-마진 곡선은 정량화하지
않는다.** **진짜 문헌 갭으로 보인다** (검색 실패가 아니라).

## 6.6 인접 연구 (불확실성 인식 CBF)
- 🔬 **Busellato et al., "Uncertainty-Aware Predictive CBFs"**
  ([sciencedirect S0921889025003884](https://www.sciencedirect.com/science/article/pii/S0921889025003884))
  — **인간 동작 예측** 불확실성에 따라 안전마진을 동적 변조. 개념적으로 같은 가산-마진 아이디어를
  *예측*에 적용. ⚠️ **초록만 접근 가능(유료).** **정합/캘리브 불확실성을 다루는지 확인 못 함.**
  → **접근권 있으면 전문을 읽을 가치 있음.**
- 🔬 **Ferraguti et al.** — *"A control barrier function approach for maximizing performance
  while fulfilling ISO/TS 15066 regulations"* (2020), 그리고 이전 *"Safety barrier functions
  and multi-camera tracking for human-robot shared environment"* (2019)
  ⚠️ **Maithani 의 참고문헌 목록 안에서 인용으로만 발견, 직접 읽지 못함.**
  → **ISO/TS 15066 형식적 취급이 중요하면 직접 추적할 만한 유망 리드.**
- 🔬 **Thumm et al. 2026**, *Vision-Based Safe HRC with Uncertainty Guarantees*
  ([arXiv:2604.15221](https://arxiv.org/abs/2604.15221)) — 이 워크스페이스 설정 문서가 이미
  "불확실성·OOD 처리의 상위 참조"로 링크해 둔 것.

---

# §7. 선례 조사 — 남들은 실제로 뭘 했나 🔬

> **이 절의 결론이 놀랍다: 아무도 이걸 제대로 안 했거나, 했는데 안 밝혔다.**

## 7.1 ZED + 로봇팔 선례

### 🚨 가장 강한 데이터 포인트가 실패 사례다
**Wershoven, U. Twente BSc 학위논문 2024** — *"Camera to Robot Arm End-Effector Calibration"*
([essay.utwente.nl/103684](https://essay.utwente.nl/103684))
- **Franka Research 3 ↔ ZED 2** 캘리브
- 카메라를 **월드 프레임에 고정**(= 우리의 eye-to-hand 시나리오) → **오차 최대 3 미터**
- 원인: 캘리브 툴/문서가 **eye-in-hand 만 지원**, eye-to-hand 미지원
- 카메라를 EE 에 마운트하니 오차 최대 **~0.5 m** 로 감소
- 🗣️ 학위논문 등급(단독 저자, 한 학기)이나 **직접적으로 온-포인트인 경고**

### 🔬 Kadam et al. 2025/26 — 우리 설계와 가장 가까운 선례 ⭐
*"Stereo-Based Single-Shot Hand-to-Eye Calibration for Robot Arms"*, **Computers (MDPI) 15(1):53**
([mdpi.com/2073-431X/15/1/53](https://www.mdpi.com/2073-431X/15/1/53))
- **UR10e + ZED2i**, 작업깊이 ~500 mm
- 포인터 툴로 **3개 비공선 점**을 찍어 world reference frame 을 로봇 베이스 대비 **1회** 측정
- 이후: *"if the robot or camera is moved, **a single stereo image of a board with three
  non-collinear points is sufficient** to determine the world-to-camera transformation matrix"*
- **결과: median RMSE x/y < 1 mm, z < 2 mm**. 스테레오 intrinsic reprojection error 0.26 px
- 고전 15-자세 법(x/y ~1 mm, z ±3.5 mm)을 **정확도로 이기면서 데이터 수집은 훨씬 적음**
- z 오차는 ZED2i 의 depth 스펙(< 1% up to 3 m)이 하한 — 500 mm 에서 ~5 mm 가 "스펙상 허용"

> **→ 우리가 독립적으로 수렴한 설계(위치-only, 3점 비공선, 원샷 재캘)와 사실상 동일하다.**
> ⚠️ **단 작업거리가 500 mm 다. 우리는 2~3 m.** 숫자를 그대로 기대하면 안 된다.

### 기타
- 📄 Stereolabs 포럼: ZED 를 로봇팔 EE 에 마운트하는 스레드 존재
  (community.stereolabs.com/t/.../10194) — 또 **eye-in-hand**, 우리 케이스 아님
- 🚨 **ZED Fusion 다중카메라 리그를 로봇 베이스에 캘리브한 GitHub 저장소·블로그·논문을
  하나도 못 찾았다.** ZED 로 human-skeleton-in-robot-frame 을 한 것도 없다.
  **→ 진짜 갭. 우리가 뒤처진 게 아니라 메우는 중이다.**

## 7.2 🚨 CBF/HRC 논문들이 정합을 실제로 어떻게 했나

**리서치 브리프의 직감("실제로 뭘 했는지 봐라")이 여기서 값을 했다 — 대부분이 얼버무린다.**

### 🔬 Kawawaki et al. 2025 — 이 조사 전체에서 가장 유용한 단일 수치 ⭐
*"Collision-Free Path Planning in Dynamic Environment..."*, MDPI Robotics 14(5):65
([mdpi.com/2218-6581/14/5/65](https://www.mdpi.com/2218-6581/14/5/65))
(2026 "Human-robot cooperative catching" 논문의 선행 연구)

**직접 인용**:
> *"Before experiments, we conducted camera and eye-to-hand calibration. We calculated the
> intrinsic and extrinsic parameters of two cameras using a **checkerboard and Zhang's method**.
> Subsequently, we estimated the transformation matrix from the left camera frame to the robot
> base frame using **eye-to-hand calibration**. The **average 3D positional error was
> approximately 15 mm**."*

- **커스텀 2-카메라 스테레오 리그** (ZED 아님, 250 fps XIMEA), 가장 표준적인 방법
  (checkerboard + Zhang + 고전 eye-to-hand AX=XB)
- 🚨 **정확히 우리 문제에 대한 실제 발표된 end-to-end 수치**

> **→ 15 mm 를 "지루하지만 제대로 실행한 고전 방법"의 현실적 상한 sanity-check 으로 쓸 것.**

### 🚨 Maithani et al. 2025 — 우리가 인용하는 그 CBF 논문이 정합 방법을 안 밝혔다
*"Proactive Hierarchical CBF-Based Constraint Prioritization"*
([arXiv:2505.16055](https://arxiv.org/abs/2505.16055) /
[Control Eng. Practice](https://www.sciencedirect.com/science/article/abs/pii/S0967066125003867))

- **ZED 2i + 공식 body-tracking SDK** (HD720@60fps, HUMAN_BODY_ACCURATE, **BODY_34** —
  **우리 프로젝트 포맷과 일치**), **Franka** 팔
- 머리/손 3D 키포인트로 실시간 CBF 제약 구성
- 🚨 **전문을 캘리브/extrinsic/변환행렬 절차에 대해 표적 질문으로 2회 검색했으나 정합 방법에
  대한 서술을 찾지 못했다.** 생략됐거나, 자명한 전제로 취급됐거나, 검색이 못 건진 곳에 묻혀 있음.
- **이것 자체가 발견이다**: **거의 정확히 우리가 만드는 걸 하는 2025년 논문조차 이 문제를 어떻게
  풀었는지 문서화하지 않았다.**
- ⚠️ 이 워크스페이스의 설정 문서가 **이 논문을 설정값 원전으로 인용**하고 있다
  (HD720@60 · BODY_34 · ACCURATE · conf 52 · segmentation off).
  단 **우리 리그는 @30 고정** (USB 컨트롤러 1개).

### 🔬 Cai et al. (NYUAD) — 정합 문제를 아예 우회
*"Safe Human-to-Humanoid Motion Imitation Using CBFs"* ([arXiv:2604.11447](https://arxiv.org/abs/2604.11447))
- 인간 스켈레톤을 **카메라 자신의 프레임(`F_Z`)에 그대로 두고**, **관절각 리타게팅**
  (상대 키포인트 기하에서 몸통/어깨/팔꿈치 각도 계산)으로 모방
- **절대 3D 위치를 로봇 베이스에 맞출 필요가 없으므로 camera-to-robot extrinsic 캘리브가
  불필요**
- **→ CBF 제약을 절대좌표가 아니라 *상대적*으로 세울 수 있다면 정당한 아키텍처 대안**
- ⚠️ **단 시뮬레이션 전용, 실기는 future work 로 명시적 유예**

### 🔬 Wang et al. (HKUST) — 다른 방식으로 우회
*"End-to-End Humanoid Robot Safe and Comfortable Locomotion Policy"*
([arXiv:2508.07611](https://arxiv.org/abs/2508.07611))
- LiDAR 를 **로봇 자신에 마운트** → 모든 장애물 점이 네이티브로 로봇 상대 센서 프레임
  → **외부 카메라-베이스 extrinsic 문제가 아예 없음**
- 고전적 **"센서를 로봇에 붙여라"** 아키텍처. 우리 Fusion 뷰어 용도엔 부적용이나,
  **이 분야가 우리 문제를 피하려고 흔히 택하는 대안 패턴**으로 명명할 가치 있음

## 7.3 🚨 4개 논문에 걸친 패턴

> **아무도 camera-to-robot 정합을 일급 연구 문제로 취급하지 않는다.**
> - **(a)** 30년 된 checkerboard+Zhang+AX=XB 로 하고 분석 없이 수치 하나만 보고 (Kawawaki)
> - **(b)** 하긴 했는데 어떻게 했는지 안 밝힘 (Maithani)
> - **(c)** 아예 필요 없게 설계 (Cai, Wang)
>
> **→ 이 프로젝트가 정합 방법론에 선제적으로 집중하는 건 이미 풀린 문제를 다시 푸는 게 아니라,
> 이 문헌이 일반적으로 얼버무리는 진짜 갭을 다루는 것이다.**

## 7.4 리서치 에이전트의 교차 권고 (원문 취지 보존)

우리 제약(카메라가 세션마다 이동, ZED-M depth ~1~1.5% of range ≈ 15~30 mm @ 1~3 m,
영구 마운트 없음, 매 세션 재실행 필요) 하에서:

1. **완전 markerless 학습 기반 (§5.1) 은 우리에게 가장 미성숙한 선택지** — camera↔robot 을
   풀지 skeleton↔robot 이 아니고, 로봇별 학습/CAD 필요, 자체 정확도 바닥(~14~20 mm)이
   고전 방법과 비슷하거나 나쁜데 성숙도는 없음
2. ⭐ **구슬/구체-on-EE + Horn/Kabsch/`cv2.estimateAffine3D` (§5.2/§5.3) 가 최적합·최저리스크** —
   당일 구현 가능, 문서화된 수십 년 된 방법, 직접 유사한 스테레오 참조 구현 존재,
   **ZED 의 약점(자세추정)이 아니라 강점(점)에 맞춤**, 매 세션 재실행이 자명
3. 🚨 **무엇을 고르든, 결과 정합 오차를 CBF 안전마진에 *직선 가산항*으로 예산 잡을 것**
   (§6 의 `Z_R`/`Z_S` 프레이밍). 상쇄된다고 가정하지 말 것.
   Kawawaki 의 실제 15 mm 와 터치프로빙 문헌의 서브밀리 바닥을 감안하면, **N≈8~12 점으로
   신중히 실행한 점 기반 캘리브는 15 mm 를 충분히 밑돌아야 하지만, 측정 없이 특정 숫자를
   가정하지 말고 명시적으로 예산에 잡을 것.**

---

# §8. 참고문헌 총목록

## 8.1 Stereolabs 공식
| 자료 | URL | 무엇에 쓰나 |
|---|---|---|
| **ZED360 도구 문서** | docs.stereolabs.com/docs/development/zed-tools/zed-360 | ⭐ 월드 원점·**yaw-only**·floor plane |
| Fusion 모듈 | docs.stereolabs.com/docs/development/zed-sdk/modules/fusion | 월드 정의, config 스키마 |
| Coordinate Frames | docs.stereolabs.com/docs/development/zed-sdk/modules/positional-tracking/coordinate-frames | `IMAGE`=OpenCV 규약, REP-103 |
| Positional Tracking Settings | .../positional-tracking/settings | `set_gravity_as_origin`, `initial_world_transform` |
| Global Localization | .../modules/global-localization | 실제 `InitFusionParameters` 사용 패턴 |
| Depth Sensing | .../modules/depth-sensing | depth 정확도 vs 거리 |
| Integrations | docs.stereolabs.com/docs/integrations | `zed-aruco` 공식 등재 |
| Fusion API group | stereolabs.com/docs/api/group__Fusion__group.html | 전체 함수/enum 목록 (**부재 확인용**) |
| `InitFusionParameters` | .../structsl_1_1InitFusionParameters.html | 전체 멤버 (**월드변환 필드 없음 확인**) |
| `FusionConfiguration` | .../structsl_1_1FusionConfiguration.html | `pose`, `override_gravity` 의미 |
| `CalibrationParameters` | .../structsl_1_1CalibrationParameters.html | ⚠️ **IMAGE 고정 경고 + 내부 모순** |
| `CameraParameters` | .../structsl_1_1CameraParameters.html | fx/fy/cx/cy/disto |
| `sl::Transform` | .../classsl_1_1Transform.html | Rodrigues vs Euler |
| `sl::Fusion` | .../classsl_1_1Fusion.html | `getPosition()` 시그니처 |
| **rectified vs raw** | support.stereolabs.com/hc/en-us/articles/27824782212119 | ⭐ **disto=0 확정** |
| 공식 multi-camera 샘플 | github.com/stereolabs/zed-sdk `object detection/multi-camera/cpp/src/main.cpp` | 동작하는 전체 코드 |
| **`stereolabs/zed-aruco`** | github.com/stereolabs/zed-aruco | 공식 마커 샘플 (C++ 전용) |
| **ZED Mini 데이터시트** | (generationrobots 등) | ⭐ **depth < 1.5% @ 3 m — 우리 카메라** |
| SDK 5.2 릴리스 노트 | stereolabs.com/developers/release/5.2 | `override_gravity` 추가 시점 |

**Stereolabs 커뮤니티 포럼** (실제 사례):
- `/t/issue-integrating-yolov8-...-fusion-zed2i/9642` — ⭐ **실제 `override_gravity` JSON,
  ArUco 기반 Fusion re-base 선례, "works but fiddly"**
- `/t/calibrate-networked-cameras-on-local-switch/3509` — config JSON 추가 예시 (2023~)
- `/t/coordinate-system-orientation-and-gravity/5590` — `set_gravity_as_origin` 설명
- `/t/best-way-to-calibrate-a-static-body-tracking-zed-cam/10957` — 서포트가 ArUco 권장
- `/t/aruco-marker-setup-for-zed-aruco-localization/9239` — ROS2 `zed_aruco_localization`
- `/t/camera-intrinsics-and-rectification-for-zed-x/10490` — ⭐ **`_raw` 구분, self-cal 변동성**
- `/t/fused-point-cloud-reference-frame/7783` — `REFERENCE_FRAME` 설명

## 8.2 OpenCV
- **calib3d group** — docs.opencv.org/4.x/d9/d0c/group__calib3d.html
  — ⭐ `calibrateHandEye`/`calibrateRobotWorldHandEye` 시그니처, 메서드 enum, AX=XB/AX=ZB 유도
- **solvePnP** — docs.opencv.org/4.x/d5/d1f/calib3d_solvePnP.html — `SOLVEPNP_IPPE_SQUARE`, `solvePnPGeneric`
- ChArUco 캘리브/검출 튜토리얼 — ⭐ ChArUco 코너 > 마커 코너 공식 권장 + 메커니즘
- **포럼 eye-to-hand** — forum.opencv.org/t/eye-to-hand-calibration/5690 — 🚨 **모더레이터 확인 레시피**
- 포럼 handEye vs robotWorldHandEye — forum.opencv.org/t/.../2733 — ⚠️ 미해결 스레드
- 포럼 3-dof camera on hand — forum.opencv.org/t/.../24133 — 공통 제약
- 포럼 hand-eye (1880) — forum.opencv.org/t/hand-eye-calibration/1880 — 🗣️ Daniilidis NaN 사례
- 포럼 aruco 좌표계 변경 — forum.opencv.org/t/.../12536 — 4.6/4.7 규약 변경
- 포럼 aruco Python 갭 — forum.opencv.org/t/.../18949 — ⚠️ **contrib 설치 권고**
- SO: estimatePoseSingleMarkers 제거 — stackoverflow.com/questions/76515924
- SO: 평면 자세 모호성 — stackoverflow.com/questions/71407392 — 🗣️ **UR10e 실사례**
- SO: 마커 크기와 정확도 — stackoverflow.com/questions/52222327 — 🗣️ 물리크기 vs 픽셀
- **RFC #28953 ArUco 2.0 / OpenCV 5.0** — ⚠️ 제안 단계, API 또 바뀔 신호

## 8.3 논문 — 우선순위 순

| # | 논문 | URL | 왜 중요 |
|---|---|---|---|
| ⭐1 | **Kadam et al. 2025/26**, *Stereo-Based Single-Shot Hand-to-Eye Calibration*, Computers 15(1):53 | mdpi.com/2073-431X/15/1/53 | **UR10e+ZED2i, 우리 설계와 동일. x/y<1mm, z<2mm** |
| ⭐2 | **Kawawaki et al. 2025**, MDPI Robotics 14(5):65 | mdpi.com/2218-6581/14/5/65 | **현실적 15 mm 기준선 (실제 발표 수치)** |
| ⭐3 | **Collins & Bartoli 2014**, *IPPE*, IJCV 109(3):252–286 | encov.ip.uca.fr/publications/pubfiles/2014_Collins_etal_IJCV_plane.pdf | **flip 모호성 원전 + 해소법** |
| ⭐4 | **Enebuse et al. 2022**, PLOS ONE | pmc.ncbi.nlm.nih.gov/articles/PMC9581431/ | **Tsai 민감성, Park 권장, 운동범위 효과** |
| ⭐5 | **Marvel & Norcross (NIST)**, SSM 구현 가이드 | pmc.ncbi.nlm.nih.gov/articles/PMC5117641/ | **ISO/TS 15066 Z_R/Z_S 가산항** |
| ⭐6 | **Đalić et al. 2024**, PMC10892941 | pmc.ncbi.nlm.nih.gov/articles/PMC10892941/ | **translation-only 우위, 4점 서브밀리** |
| ⭐7 | **Klimchik et al.**, arXiv:1311.6677 | arxiv.org/abs/1311.6677 | **위치-only 의 통계적 근거** |
| 8 | **Krogius, Haggenmiller, Olson 2019**, IROS | docs.wpilib.org/.../krogius2019iros.pdf | tagStandard41h12 원전 |
| 9 | **Wang & Olson 2016**, *AprilTag 2*, IROS | april.eecs.umich.edu/pdfs/wang2016iros.pdf | 단일태그 자세오차 0.5~3° |
| 10 | **Olson 2011**, *AprilTag* 원전 | april.eecs.umich.edu/media/pdfs/olson2011tags.pdf | 49~100 px 운용범위 |
| 11 | **Garrido-Jurado et al. 2014**, ArUco 원전 | cs-courses.mines.edu/csci507/schedule/24/ArUco.pdf | 보드 근거, 85% 가림 실험 |
| 12 | **FMAC 2026**, arXiv:2601.07723 | arxiv.org/html/2601.07723v1 | **회전오차 꼬리(~0.5% 모호성)** |
| 13 | **Jin et al.**, IROS, RGBD fiducial | pengjujin.github.io/files/iros_aptag.pdf | 쌍봉분포 실측, depth 의 진짜 가치 |
| 14 | **Markley et al. 2007**, *Averaging Quaternions*, JGCD 30(4) | acsu.buffalo.edu/~johnc/ave_quat07.pdf | **회전 평균 정본** |
| 15 | **Hartley et al.**, *Rotation Averaging*, IJCV 2013 | users.cecs.anu.edu.au/~hartley/Papers/PDF/Hartley-Trumpf:Rotation-averaging:IJCV.pdf | SO(3) 평균 서베이 |
| 16 | **Tsai & Lenz 1989** | kmlee.gatech.edu/me6406/handeye.pdf | AX=XB 원전, 자세 분산 지침 |
| 17 | **Maithani et al. 2025**, arXiv:2505.16055 | arxiv.org/abs/2505.16055 | 🚨 ZED2i+Franka+BODY_34, **정합 방법 미공개** |
| 18 | **Wershoven** (U. Twente BSc) | essay.utwente.nl/103684 | 🚨 **ZED2+Franka eye-to-hand 3 m 오차** |
| 19 | **LRBO** (Li et al.), arXiv:2311.01335 | arxiv.org/html/2311.01335v3 | ICP 로 0.93 mm (단 ToF) |
| 20 | **Ali et al. 2019**, Sensors 19(12):2837 | mdpi.com/1424-8220/19/12/2837 | robot-world-hand-eye 비교 |
| 21 | **Ch'ng et al. 2019**, arXiv:1909.11888 | arxiv.org/abs/1909.11888 | 모호성 + robust rotation averaging |
| 22 | **PMC6960891**, AprilTag state estimation | pmc.ncbi.nlm.nih.gov/articles/PMC6960891/ | 실제 단일태그 cm급 |
| 23 | **PMC12943937** (2026), ChArUco 기하 | pmc.ncbi.nlm.nih.gov/articles/PMC12943937/ | ⚠️ **수치가 그림에 박힘 — 직접 열람 필요** |
| 24 | **MarkerPose**, arXiv:2105.00368 | arxiv.org/abs/2105.00368 | dense depth vs 코너 삼각측량 |
| 25 | **Azad et al. 2009** (KIT), stereo vs mono | h2t.iar.kit.edu/pdf/Azad2009b.pdf | 🔬 **반대 증거 (2009, 낡음)** |
| 26 | **Cai et al.** (NYUAD), arXiv:2604.11447 | arxiv.org/abs/2604.11447 | 정합 우회 (관절각 리타게팅) |
| 27 | **Wang et al.** (HKUST), arXiv:2508.07611 | arxiv.org/abs/2508.07611 | 정합 우회 (on-robot LiDAR) |
| 28 | **Thumm et al. 2026**, arXiv:2604.15221 | arxiv.org/abs/2604.15221 | 불확실성 보장 HRC |
| 29 | **Busellato et al.**, Uncertainty-Aware Predictive CBFs | sciencedirect.com/science/article/pii/S0921889025003884 | ⚠️ **유료, 초록만** |
| 30 | **Denayer et al. 2024**, Sensors 24(7):2142 | mdpi.com/1424-8220/24/7/2142 | ICP/CAD 정합 비교 |
| 31 | **Muñoz-Salinas et al.**, Mapping from Planar Markers | arxiv.org/abs/1606.00151 | 다중마커 매핑 |
| 32 | **UcoSLAM**, arXiv:1902.03729 | arxiv.org/abs/1902.03729 | 키포인트+마커 융합 |
| 33 | **TagSLAM**, arXiv:1910.00679 | arxiv.org/abs/1910.00679 | 팩터그래프 태그맵 |
| 34 | **Scalable Fiducial Tag Localization**, arXiv:2207.11942 | arxiv.org/abs/2207.11942 | 98% 정합 성공률 |
| 35 | **PMC11348399**, Mean/Variance of Spatial Displacements | pmc.ncbi.nlm.nih.gov/articles/PMC11348399/ | 6-DoF 평균 |
| 36 | **PMC6339217**, Quaternion Kalman + Manifold | pmc.ncbi.nlm.nih.gov/articles/PMC6339217/ | 매니폴드 필터링 |
| 37 | **PMC7506853**, ArUco 3D placement | pmc.ncbi.nlm.nih.gov/articles/PMC7506853/ | 그리드보드 벤치마크 |
| 38 | **PMC7830840**, Smart Artificial Markers | pmc.ncbi.nlm.nih.gov/articles/PMC7830840/ | 마커 매핑/위치추정 |
| 39 | **Furgale et al., FSR 2017**, hand-eye + 시간오프셋 | tisl.cs.utoronto.ca/publication/201709-fsr-hand_eye_calibration/fsr17-hand_eye_calibration.pdf | 비동기 스트림 |
| 🚨40 | **Kallwies, Forkel & Wuensche 2020** (IEEE, 49회 인용) | semanticscholar.org/paper/190a6317ebfbe2c6f29b7684f68a5b5a2104c02c | ⚠️ **유료. 보드-vs-단일 수치의 최유망 후보 — IEEE 접근권 있으면 이것부터** |

**markerless 논문** (§5.1 표의 URL 참조): DREAM (arXiv:1911.09231), RoboPose (arXiv:2104.09359),
CtRNet (arXiv:2302.14332), CtRNet-X (arXiv:2409.10441), SGTAPose (arXiv:2307.12106),
RoboKeyGen (arXiv:2403.18259), HoRoPose (arXiv:2402.05655), FEEPE (arXiv:2503.14051),
Kalib (arXiv:2408.10562), MonoSE(3)-Diffusion (arXiv:2510.10434)

## 8.4 도구 / 저장소
- **`easy_handeye2`** (ROS2, "eye-on-base") — github.com/marcoesposito1988/easy_handeye2 ⭐
- `easy_handeye` (ROS1) + **issue #130** (정확도 발언) — github.com/IFL-CAMP/easy_handeye
- **MoveIt 2 Hand-Eye Calibration 튜토리얼** — moveit.picknik.ai/humble/doc/examples/hand_eye_calibration/hand_eye_calibration_tutorial.html ⭐ (2단계 패턴의 수학)
- `moveit_calibration` — github.com/moveit/moveit_calibration
- `ethz-asl/hand_eye_calibration` — github.com/ethz-asl/hand_eye_calibration
- `mikeferguson/robot_calibration` (ROS2) — github.com/mikeferguson/robot_calibration
- **AprilRobotics/apriltag** — github.com/AprilRobotics/apriltag
- **`apriltag_ros` + `calibrate_bundle.m`** — github.com/AprilRobotics/apriltag_ros/blob/master/apriltag_ros/scripts/calibrate_bundle.m ⭐ (공식 번들 캘리브)
- **`christianrauch/apriltag_ros`** (ROS2 사실상 표준) — github.com/christianrauch/apriltag_ros
- `berndpfrommer/tagslam` — github.com/berndpfrommer/tagslam (⚠️ ROS2 WIP)
- `pupil-apriltags`, `duckietown/lib-dt-apriltags`
- **`tobycollins/IPPE`** — github.com/tobycollins/IPPE ⭐ (저자의 모호성 해소법)
- **`gnastacast/dvrk_vision`** — github.com/gnastacast/dvrk_vision ⭐ (색구슬+Horn 참조구현)
- `NVlabs/DREAM`, `ylabbe/robopose`, `ucsdarclab/CtRNet-robot-pose-estimation`,
  `Oliverbansk/Holistic-Robot-Pose-Estimation`, `tianshuwu/feepe`,
  `robotflow-initiative/Kalib`, `leihui6/LRBO`
- **CMU Robotics Knowledgebase, Registration Techniques** — roboticsknowledgebase.com/wiki/math/registration-techniques/ ⭐

## 8.5 벤더 / 커뮤니티 🗣️ (낮은 권위, 참고용)
- **Optitag**, *Designing the perfect Apriltag* — optitag.io/blogs/news/designing-your-perfect-apriltag ⭐ (크기 공식)
- Optitag, *Using Apriltags with ROS* — optitag.io/blogs/news/using-your-apriltag-with-ros
- **ChiefDelphi**, *Pixels for Apriltag Detection?* — chiefdelphi.com/t/pixels-for-apriltag-detection/424609 ⭐ (32 px 실측)
- **Limelight** docs — docs.limelightvision.io/docs/docs-limelight/pipeline-apriltag/apriltags (해상도↔flip)
- PhotonVision docs — docs.photonvision.org/en/latest/docs/apriltag-pipelines/2D-tracking-tuning.html
- **FTC April Tags Guide** — ftc-docs-cdn.ftclive.org/booklets/en/april_tags.pdf (4in/6in 실제값)
- laserscanning-europe — 측정된 검출거리 표
- dsp.stackexchange, *Intuition about tag pose estimation accuracy* — dsp.stackexchange.com/questions/68661 ⭐ (Nyquist 유도)
- Robotics SE, *Is easier to detect a large or a small marker?* — robotics.stackexchange.com/questions/21508 (20px vs 200px)
- **Zivid**, *The practical guide to 3D hand-eye calibration* — medium.com/zivid/... (10~20 자세)
- **Mech-Mind** TCP touch 문서 — docs.mech-mind.net/en/suite-software-manual/latest/vision-calibration/eth-manual-calib-tcp-touch.html
- Mech-Mind 커뮤니티 — 🗣️ **30 나쁜 자세(4cm) vs 적고 좋은 자세(5mm)**
- industrialmonitordirect.com — 4-point TCP ±0.5 mm
- samarth-robo.github.io, *Camera-Robot Extrinsic Calibration* — AX=XB 유도, 재캘 재생
- robotwiki.cs.lth.se — OpenCV eye-to-hand 레시피 독립 재현
- drmu.net (2023) — `estimateAffine3D` 로 다중카메라 body-tracking extrinsic
- OKLAB 블로그 — ChArUco 재투영오차 밴드
- diva-portal.org 학위논문 — 4 m 단일 ArUco ~10 cm 오차
- Politesi.polimi.it 학위논문 (2025) — 36h11/41h12/52h13 실측 비교
- unipd.it 학위논문 (Montecchio) — HYB-OR + QL2-AVG + FIR 파이프라인
- OpenMV 포럼 — 8cm 태그 @60~80cm 에서 10mm; 지렛대 증폭 경고

## 8.6 이 워크스페이스 내부
- `docs/robot_base_registration.md` — **설계 결정** (이 문서의 짝)
- `ZEDM_포즈추출_초기셋업.md` §8 — **eye-on-base → AR 태그 필드 데이텀 순서 (기결정)**
- `docs/overview.md` — 아키텍처, 데이터 흐름
- `docs/memory.md` — 현재 단계
- `logs/fusion_zed360.json` — ✅ **실측 캘리브 원본** (수정 금지)
- `scripts/zed_make_fusion_config.py` — ✅ config 왕복 경로 참조 구현

---

# §9. 미확인 항목 총목록 ⚠️

> **이 절을 지우지 말 것.** 확신 있어 보이게 다듬으면 이 조사의 가치가 사라진다.
> 리서치 에이전트가 "확인 못 했다"고 한 것을 전부 모았다.

## 9.1 실측으로 풀어야 하는 것 (우리 리그에서)

| # | 항목 | 왜 중요 | 어떻게 확인 |
|---|---|---|---|
| 1 | **`CalibrationParameters` 좌표계** — 클래스 경고는 "항상 IMAGE", 필드 설명은 "user coordinate system". **Stereolabs 문서 내부 모순** | PnP 결과 변환이 틀어짐 | non-IMAGE 좌표계에서 `print(calibration_parameters.stereo_transform)` |
| 2 | **자세 정확도용 픽셀 임계** — 리서치 A: 100~150 px, 리서치 B: 60~120 px. **둘 다 자기 추정치라고 명시.** 권위 있는 출처 없음 | 태그 크기 결정의 핵심 | 태그 크기/거리 스윕 |
| 3 | **5 mm / 1° @ 2~3 m 목표 자체** — **두 리서치 모두 달성 사례를 못 찾음.** 문헌은 그 거리에서 cm 급 시사 | 목표가 비현실적일 수 있음 | 우리 리그 실측 |
| 4 | **Fusion body-tracking 이 월드 Z=up 을 가정하는가** | C-1(JSON 재작성) 의 리스크. **4-DOF 구속하면 무의미해짐** | 기울인 config 로 실험 |
| 5 | **리그를 기울여도 ZED360 캘리브가 유효한가** (`override_gravity=false` 라 IMU 가 roll/pitch 공급) | 리그 재배치 자유도 | 리그 기울여 재현성 측정 |
| 6 | **OpenCV Python ChArUco API 갭이 최신 버전에서 고쳐졌는지** (`detectBoard` 부재 등) | 구현 블로커 | 설치본으로 직접 확인 |
| 7 | **ZED360 auto-discover 순서가 결정론적인가** (원점이 "첫 번째 로드된 카메라") | 재캘리브마다 기준 카메라가 바뀔 수 있음 | 반복 실행 |

## 9.2 유료/접근 불가 — 접근권 있으면 볼 것

| # | 자료 | 왜 |
|---|---|---|
| 🚨1 | **Kallwies, Forkel & Wuensche 2020** (IEEE, 49회 인용) | **보드-vs-단일 회전오차 수치의 최유망 후보.** 이 조사 최대 갭의 유일한 희망 |
| 2 | **Busellato et al.**, Uncertainty-Aware Predictive CBFs | 정합/캘리브 불확실성을 다루는지 확인 필요 |
| 3 | **Ferraguti et al.** (2019/2020) — ISO/TS15066 형식적 CBF | **인용으로만 발견, 직접 못 읽음.** 표준 형식 취급이 중요하면 |
| 4 | **PMC12943937** — ChArUco 자세 vs 각도/거리 | ⚠️ **수치가 그림에 박혀 텍스트 추출 실패.** 직접 열람하면 얻을 수 있음 |

## 9.3 문헌 자체의 갭 (검색 실패가 아님)

| # | 갭 |
|---|---|
| 1 | 🚨 **"보드가 단일마커 대비 회전 RMSE 를 N배 줄인다"는 통제된 연구가 없다.** 두 리서치가 독립적으로 확인 |
| 2 | 🚨 **정합오차 → SSM 필요 분리거리 민감도 분석이 없다.** NIST 가 메커니즘(가산 Z_R/Z_S)만 확립, 곡선은 없음 |
| 3 | 🚨 **ZED Fusion(다중카메라) → 로봇 베이스 선례가 아무 데도 없다.** ZED 로 human-skeleton-in-robot-frame 도 없음 |
| 4 | **1~3 m 작업거리 스테레오 hand-eye 정확도 피어리뷰 수치 없음.** 정량 출처 둘 다 ~500 mm |
| 5 | **"자세 정확도에 필요한 픽셀 수"의 권위 있는 공식/표가 없다.** 검출 임계만 여러 출처가 수렴 |
| 6 | **"1회 캘리브 → 원샷 재캘" 패턴의 표준 명칭이 없다.** 개념은 근거 확실 (MoveIt 수학 + Kadam 구현) |
| 7 | **동일 실제 조건에서 ArUco/AprilTag/ChArUco false-positive 율 % 통합 표가 없다** |
| 8 | **ChArUco-PnP vs ZED-depth head-to-head 비교 연구가 없다.** §4.8 결론은 추론 |
| 9 | **fiducial 자세 전용 "시작 프레임 몇 장" 출처가 없다.** hand-eye 문헌에서 외삽 |
| 10 | **`calibrateRobotWorldHandEye` 의 eye-to-hand 인자 매핑 레시피가 없다.** OpenCV 포럼도 미해결 |
| 11 | **ZED 스테레오 ICP-to-robot-base 발표 결과 없음.** LRBO 는 구조광/ToF |

## 9.4 수치가 추출 안 된 것
- SGTAPose, RoboKeyGen, FEEPE, Kalib, MonoSE(3)-Diffusion 의 mm 정확도
  → **직접 논문 읽기 전엔 구체 수치 인용 금지**
- TagSLAM 정확도
- arXiv:2203.10180 (AprilTag/WhyCode 모호성) 수치
- arXiv:2207.11942 태그맵 자세 정확도 (98% 성공률만 확인)
- Muñoz-Salinas 계열 mm/deg 수치
- MonoSE(3)-Diffusion 코드 가용성

## 9.5 낡았을 가능성
- Optitag 의 "AprilTag-ROS 는 AprilTag 2 패밀리만" 주장 — 유지보수되는 ROS2 포크는
  링크된 C 라이브러리를 따르므로 41h12 기본일 것
- ARTag/AprilTag/CALTag 가림 연구 (2017) — AprilTag 3 이전 검출기
- Azad et al. stereo-vs-mono (2009) — IPPE·현대 ChArUco 이전
- `handeye_calib_camodocal` 유지보수 상태 (README 자체 주장만)
- FMAC 의 AprilTag ~90° 주기 yaw 아티팩트 — **저자도 설명 못 함**

---

## 문서 관리 규칙

- 이 문서는 **원자료**다. 새 조사 결과가 나오면 **해당 절에 추가**하고 등급을 붙인다.
- **§9 의 항목이 실측으로 풀리면**, 그 항목을 지우지 말고 **✅ 로 등급을 올리고 결과·날짜·로그
  경로를 적는다.** 무엇이 언제 확인됐는지가 이력이다.
- 설계 판단이 바뀌면 [robot_base_registration.md](robot_base_registration.md) 를 고치고,
  **이 문서는 근거가 바뀔 때만** 고친다.
- 조사 시점(2026-07-17) 이후 웹 자료는 바뀔 수 있다. SDK 사실은 **pyzed 5.4** 기준이다.





