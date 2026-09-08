# SETUP — reproduce cbf_ws on a new PC

This workspace's Python packages **cannot just be copied** — `pyzed` and the ZED SDK
are machine-specific (matched to the GPU/driver/CUDA). Follow the two layers below.

Read first: [docs/memory.md](docs/memory.md) (live state), then this file.

## 0. Hardware assumed
- NVIDIA GPU, Compute Capability ≥ 7.5 (Turing or newer). Reference machine: RTX 6000 Ada.
- NVIDIA driver ≥ 580.65 (for the CUDA 13 build) or ≥ 525.60 (CUDA 12.8 build).
- 2 × ZED Mini (USB3). **Note:** on a single USB3 controller, 2×HD720@**60** exceeds
  bandwidth (collapses to ~6/22 fps); **2×HD720@30 works**. For 2×60, split the cameras
  onto separate USB3 controllers. Single camera @60 is fine. (See docs/worklog/2026-07-16.md.)

## 1. System layer — ZED SDK 5.4 (NOT pip)
```bash
sudo apt update && sudo apt install -y zstd wget
cd ~/Downloads
wget --content-disposition "https://download.stereolabs.com/zedsdk/5.4/cu12/ubuntu22"
chmod +x ZED_SDK_Ubuntu22_cuda12.8_tensorrt10.9_v5.4.0.zstd.run
./ZED_SDK_Ubuntu22_cuda12.8_tensorrt10.9_v5.4.0.zstd.run   # NO sudo; it self-escalates
#   prompts: deps/CUDA/AI models = y ; driver update = n ; Install Python API = n
sudo reboot
```
The installer auto-installs the matching CUDA (no separate CUDA toolkit needed).

## 2. Python layer — conda env `zed`
```bash
conda create -n zed python=3.10 -y
conda activate zed                      # use `conda activate`, not any shell alias
pip install -r requirements.txt         # or: conda env create -f environment.yml
pip install requests                    # only needed by get_python_api.py below
python /usr/local/zed/get_python_api.py # installs pyzed INTO this env (needs SDK from step 1)
python -c "import pyzed.sl as sl; print('pyzed', sl.Camera().get_sdk_version())"  # -> 5.4.0
```
`requirements.txt` holds only what the workspace code imports (numpy, opencv-python);
pyzed comes from the SDK. The broader robot/RealSense stack is deliberately not included.

## 3. Verify cameras
```bash
python scripts/zed_check.py                 # enumerate + per-camera stream test
python scripts/zed_check.py --concurrent --fps 30   # both cameras at once
```

## 4. Run the pipeline
```bash
# single ZED-M pose -> JSONL (34 kp + per-joint conf + timestamp)
python scripts/zed_bodytrack_min.py --fps 30 --duration 60 --record-svo
# visualize (live window, or --save for a video)
python scripts/zed_bodytrack_viz.py --fps 30
python scripts/viz_pose_log.py logs/pose_XXXX.jsonl
```

## 5. Dual-camera fusion (occlusion-robust) — PLAN01
Cameras are placed **left/right of the subject**. Fusion needs the inter-camera calibration:
```bash
# (a) proper: run ZED360, have a person walk slowly through the shared view -> fusion_config.json
/usr/local/zed/tools/ZED360
python scripts/zed_fusion_bodytrack.py --calib fusion_config.json --fps 30
# (b) bootstrap (no walk; approximate, hand-measured left/right poses)
python scripts/zed_fusion_bodytrack.py --manual --fps 30
```
`scripts/zed_fusion_bodytrack.py` is written against the ZED SDK 5.4 Fusion API but is
**not yet hardware-tested** (needs both cameras + a calibration). See the `# VERIFY` notes
in it and [docs/plans/2026_07/16_PLAN01_zed_fusion_dual.md](docs/plans/2026_07/16_PLAN01_zed_fusion_dual.md).

## Key facts (also in docs/memory.md)
- BODY_34 joints used by the barrier: HEAD=26, LEFT_WRIST=7, RIGHT_WRIST=14.
- detection_confidence_threshold: start ~40 indoors (the doc's 52 was a ZED-2i paper value).
- Working distance 1.2–2.0 m; ZED-M 63 mm baseline.
- Full context / roadmap: `ZEDM_포즈추출_초기셋업.md`, `docs/plans/`.
