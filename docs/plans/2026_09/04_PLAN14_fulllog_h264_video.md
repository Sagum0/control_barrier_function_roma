---
date: 2026-09-04
task: fulllog 카메라 MP4 를 mp4v(MPEG-4 Part 2) 대신 H.264 로 저장 — 시스템 ffmpeg 파이프, 없으면 mp4v 폴백
planner: Claude
executor: codex
status: done
---

# PLAN14 — fulllog 카메라 영상 H.264 저장

## 한 줄 결론

`scripts/zed_fusion_fulllog.py` 가 저장하는 카메라별 MP4 는 OpenCV `mp4v`(MPEG-4 Part 2 Simple
Profile) 라 **VS Code 미리보기·브라우저·Windows 기본 플레이어에서 재생이 안 된다**(파일은 무결함,
VLC/ffplay 는 재생됨). conda `zed` 의 cv2 5.0.0 은 H.264 인코더를 열지 못하므로, 프레임을
**시스템 `ffmpeg` 서브프로세스(libx264)로 파이프**해 H.264 MP4 로 쓴다. `ffmpeg` 가 없으면
지금처럼 `mp4v` 로 폴백하고 경고를 찍는다. 프레임 수·`frame_idx` join·파일 이름·JSONL 스키마는
그대로다.

## 왜 이 plan 이 필요한가

- 2026-09-04 실측 `logs/fulllog_20260904_173800/*.mp4`: ffprobe 300 frames/10 s, 전체 디코드 무에러,
  추출 프레임 육안 정상 → **파일은 안 깨졌다.** 사용자가 "깨진다"고 본 것은 재생기가
  MPEG-4 Part 2 를 디코드하지 못하는 현상이다.
- conda `zed` 에서 `cv2.VideoWriter` fourcc 탐침: `avc1`/`H264`/`x264` 전부 `isOpened()=False`
  (cv2 내장 ffmpeg 가 `h264_v4l2m2m` 만 시도하고 실패), `mp4v` 만 성공. **cv2 로는 H.264 불가.**
- 시스템 `ffmpeg` 9.0.1(`/home/pc/.local/bin/ffmpeg`, conda `zed` 안에서도 PATH 에 잡힘)은
  `libx264`·`libopenh264`·`h264_nvenc` 를 갖고 있다. 기존 파일 트랜스코딩 테스트:
  `-fps_mode passthrough -c:v libx264 -preset veryfast -crf 18` 로 300 프레임 보존, 10 s 영상에
  0.43 s(user CPU 3.5 s ≈ 스트림당 코어 35%) → 2 스트림 실시간 여유 충분.

## 지금까지 이어진 맥락 (self-contained)

- `zed_fusion_fulllog.py` 는 dual ZED-M Fusion 로거다. 실행마다 `<outdir>/fulllog_<stamp>/` 에
  JSONL(`frame`/`fused`/`raw`/`metrics` 레코드), `_meta.json`, 카메라별
  `fulllog_<stamp>_cam<serial>.mp4` 를 저장한다. JSONL 의 `frame_idx` 가 MP4 프레임 번호와의
  join 키라 **영상 프레임이 하나라도 빠지거나 중복되면 안 된다.**
- 영상 경로: `_open_video_writers(senders, run_dir, stamp, fps)` (L149-172) 가 카메라 해상도로
  `cv2.VideoWriter(path, fourcc("mp4v"), fps, size)` 를 열고 `videos[serial] = {"path", "writer",
  "image": sl.Mat()}` 를 돌려준다. `_write_video_frame(cv2, video, camera)` (L175-182) 가
  `retrieve_image(LEFT)` → BGRA 검사 → `writer.write(cvtColor(BGRA2BGR))`. `finally` (L390) 에서
  `video["writer"].release()`. `--no-video` 로 전체 비활성.
- SIGINT/SIGTERM 은 stop 플래그만 세우고 `finally` 하나로 정리한다(PLAN13). 이 구조를 유지한다.

## 지금 기준 판단

- **캡처 중 단일 인코드(ffmpeg 파이프)** 를 택한다. 대안인 "mp4v 로 찍고 종료 시 트랜스코딩" 은
  구현이 더 작지만 손실 인코드를 두 번 하고 종료 대기가 생기며 원본/변환본 두 파일이 남는다.
  데이터셋 용도라 한 번만 인코드하는 쪽이 맞다.
- 인코더는 **`libx264`** 기본. `h264_nvenc` 는 ZED NEURAL depth 와 GPU 를 나눠 쓰게 되므로 쓰지 않는다.
- 새 CLI 플래그는 **하나만**: `--video-mp4v`(store_true) — ffmpeg 를 건너뛰고 지금처럼 cv2 `mp4v`
  로 저장하는 탈출구.

## 구현해야 할 것

**`scripts/zed_fusion_fulllog.py` 한 파일만 수정한다.**

1. **ffmpeg writer 클래스 추가** — `cv2.VideoWriter` 와 같은 표면(`isOpened()`, `write(bgr)`,
   `release()`)을 가진 작은 클래스 `_FfmpegH264Writer(path, fps, size)`:
   - `shutil.which("ffmpeg")` 로 실행 파일을 찾고, 없으면 `isOpened()` 가 False.
   - `subprocess.Popen([ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
     "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", "%dx%d" % size, "-r", str(fps), "-i", "-",
     "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
     "-fps_mode", "passthrough", "-movflags", "+faststart", path], stdin=PIPE, stderr=PIPE)`.
   - `write(bgr)`: `bgr` 는 (H,W,3) uint8 → `np.ascontiguousarray(bgr).tobytes()` 를 stdin 에 쓴다.
     `BrokenPipeError` 가 나면 한 번만 경고를 찍고 이후 write 는 무시한다(주 로깅을 죽이지 않는다).
   - `release()`: stdin 을 닫고 `wait(timeout=30)`; 반환 코드가 0 이 아니면 stderr 꼬리를 경고로
     찍는다. 두 번 불려도 안전하게.
   - 종료 시 `-movflags +faststart` 는 ffmpeg 가 moov 를 앞으로 옮기느라 파일을 한 번 더 쓰는
     비용이 있다. 문제되면 빼도 되지만 기본은 켠다.
2. **`_open_video_writers(senders, outdir, stamp, fps, use_mp4v)`** — 인자 하나 추가:
   - `use_mp4v` 가 False 면 `_FfmpegH264Writer` 를 먼저 시도하고, `isOpened()` 가 False 면
     `print("warning: ffmpeg not found; falling back to cv2 mp4v (MPEG-4 Part 2, limited player
     support)")` 후 기존 `cv2.VideoWriter(mp4v)` 로 폴백.
   - `use_mp4v` 가 True 면 지금 그대로.
   - `videos[serial]` dict 에 `"codec": "h264" | "mp4v"` 키를 추가한다. 파일 이름은 불변.
   - 기존처럼 실패 시 열린 writer 들을 release 하고 raise.
3. **`_write_video_frame`** — 변경 없음(`writer.write(bgr)` 인터페이스가 같다). cv2 import 는
   `cvtColor` 때문에 여전히 필요하다.
4. **CLI** — `--video-mp4v` (store_true, help: "use cv2 mp4v instead of ffmpeg H.264 (fallback
   encoder; limited player support)") 추가. `--no-video` 는 그대로.
5. **meta.json** — `video_paths` 의 각 항목에 `"codec"` 키를 추가한다
   (`{"serial_number", "path", "codec"}`). 다른 키는 불변.
6. **시작 로그** — 기존 `print("camera video ->", path)` 줄에 코덱을 덧붙인다
   (예: `camera video [h264] -> …`).
7. **worklog** — `docs/worklog/2026-09-04.md` Changes 표에 한 줄 append.

## 참고해야 할 것

- `scripts/zed_fusion_fulllog.py` L149-172 (`_open_video_writers` — 해상도 취득·writer 생성·실패
  롤백 패턴을 그대로 따른다), L175-182 (`_write_video_frame` — write 에 들어오는 배열이 BGR
  uint8 (H,W,3) 임을 확인), L259-262 (호출 지점, `videos` 의 path 출력), L284-287 (meta
  `video_paths` 구성), L390 (`finally` 의 release), L213 (`--no-video` 정의 위치 — 새 플래그를
  옆에 둔다).
- 현재 import: `os, sys, json, time, math, signal, argparse` 등. `subprocess`, `shutil` 은 새로
  import 한다. `numpy` 는 이미 pyzed 경로로 쓰인다 — 없으면 추가.

## 신경써야 할 것

- **프레임 수 보존이 최우선.** `-fps_mode passthrough`(구 `-vsync 0`) 를 반드시 넣어 ffmpeg 가
  프레임을 복제/삭제하지 않게 한다. 입력은 rawvideo 라 타임스탬프가 없고 `-r fps` 로 고정 간격이
  부여된다 — 이것이 기존 cv2 writer 와 같은 의미다.
- ffmpeg stdin 파이프 쓰기가 막히면(디스크 느림 등) 메인 루프가 블록돼 `received_fps` 가 떨어질
  수 있다. 이번에는 스레드/큐를 도입하지 않는다(non-scope). 대신 라이브 검증에서 metrics
  `received_fps` 가 30 근처인지 본다. 떨어지면 `--video-mp4v` 로 즉시 회귀 가능해야 한다.
- `stderr=PIPE` 로 두면 ffmpeg 가 에러를 많이 찍을 때 파이프가 차서 교착할 수 있다.
  `-loglevel error` 로 출력을 최소화하고, `release()` 에서 `communicate()` 로 읽어 비운다.
- 정상 종료 경로는 `finally` 하나다. 시그널 핸들러 안에서 writer 를 건드리지 않는다.
- `scripts/run_fusion.py`·`zed_fusion_bodytrack.py`·`zed_fusion_viz.py` 수정 금지.
  `logs/**` 의 기존 파일 이동·삭제·재인코딩 금지.
- JSONL 레코드 스키마, MP4 파일 이름, `--no-video`/`--record-svo` 동작 불변.
- 주석 한국어, 기존 파일 스타일. 하드웨어 없음 — 정적 검증까지만.

## 이번에는 하지 않는 것

- 기존 `logs/` 산출물의 일괄 트랜스코딩(사용자가 필요 시 아래 명령으로 수동 수행).
- `h264_nvenc`/`libopenh264` 선택 옵션, 비트레이트·CRF 플래그 노출.
- 인코더 스레드/큐 분리, 프레임 드롭 감지 로직.
- SVO2 경로 변경.

## 근거

- cv2 탐침(2026-09-04, conda zed): `avc1/H264/x264 opened=False`, `mp4v opened=True codec=mpeg4`.
  로그에 `Could not open codec h264_v4l2m2m` — cv2 내장 ffmpeg 에 소프트웨어 H.264 인코더 없음.
- 시스템 ffmpeg 트랜스코딩 테스트: 300 → 300 프레임, H.264 High, 0.43 s/10 s.
- 기존 파일 임시 우회(원본 유지, 옆에 `_h264.mp4` 추가):
  ```bash
  ffmpeg -i IN.mp4 -fps_mode passthrough -c:v libx264 -preset veryfast -crf 18 -pix_fmt yuv420p IN_h264.mp4
  ```

## 검증

- `python3 -m py_compile scripts/zed_fusion_fulllog.py`
- `conda run -n zed python3 scripts/zed_fusion_fulllog.py --help` — `--video-mp4v` 가 보이고
  나머지 옵션 불변.
- 단위 수준(카메라 불필요, conda zed): `_FfmpegH264Writer("/tmp/x.mp4", 30, (1280, 720))` 를 열어
  검은 프레임 90 장 `write` 후 `release` → `ffprobe -show_entries stream=codec_name,nb_frames`
  가 `h264`, `90` 을 돌려준다. 같은 절차를 `use_mp4v=True` 경로로도 돌려 `mpeg4`, `90` 확인.
- `PATH` 에서 ffmpeg 를 감춘 상태(`env PATH=/usr/bin:/bin`)로 writer 를 열면 폴백 경고 후
  `mp4v` 로 열리는지 확인.
- 라이브(사용자): `run_fusion.py fulllog --skip-calib -- --duration 10` → 두 MP4 가 `ffprobe`
  에서 `h264`, `nb_frames` 가 JSONL 마지막 `frame_idx`+1 과 일치, metrics `received_fps` ≈ 30,
  VS Code 미리보기에서 재생됨. `kill <pid>` 종료 후에도 MP4 가 읽힘.

## 다음 단계

- 촬영이 쌓이면 `frame_idx` 로 JSONL↔MP4 를 join 하는 분석 스크립트를 별도 plan 으로.
