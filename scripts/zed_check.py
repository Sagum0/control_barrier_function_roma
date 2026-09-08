#!/usr/bin/env python3
"""ZED camera hardware check. Run inside the `zed` conda env.

  python scripts/zed_check.py                 # enumerate + test each camera sequentially
  python scripts/zed_check.py --concurrent    # open ALL cameras at once (separate processes)
  python scripts/zed_check.py --concurrent --fps 60   # stress USB3 bandwidth at 60fps

Sequential: opens each AVAILABLE camera BY SERIAL, verifies identity (guards against
the SDK falling back to the first camera), grabs, reports fps.
Concurrent: launches one process per camera (GIL-free) to measure true simultaneous
throughput — this is where a shared USB3 controller shows its bandwidth ceiling.
"""
import argparse
import multiprocessing as mp
import sys
import time

import pyzed.sl as sl


def _open(sn, res, fps):
    z = sl.Camera()
    init = sl.InitParameters()
    if sn:
        init.set_from_serial_number(sn)
    init.camera_resolution = getattr(sl.RESOLUTION, res)
    init.camera_fps = fps
    init.depth_mode = sl.DEPTH_MODE.NONE  # liveness/bandwidth only; no AI model needed
    return z, z.open(init)


def _grab_worker(sn, res, fps, dur, q):
    z, err = _open(sn, res, fps)
    if err != sl.ERROR_CODE.SUCCESS:
        q.put((sn, "OPEN_FAIL", 0, str(err)))
        return
    rt = sl.RuntimeParameters()
    c = e = 0
    t0 = time.time()
    while time.time() - t0 < dur:
        if z.grab(rt) == sl.ERROR_CODE.SUCCESS:
            c += 1
        else:
            e += 1
    dt = time.time() - t0
    z.close()
    q.put((sn, "OK", c / dt if dt else 0, "grabs=%d errors=%d" % (c, e)))


def enumerate_devices():
    devs = sl.Camera.get_device_list()
    print("=== %d ZED device(s) ===" % len(devs))
    for d in devs:
        print("  id=%s serial=%s model=%s state=%s path=%s" % (
            getattr(d, "id", "?"), getattr(d, "serial_number", "?"),
            getattr(d, "camera_model", "?"), getattr(d, "camera_state", "?"),
            getattr(d, "path", "?")))
    return [d for d in devs
            if getattr(d, "camera_state", None) == sl.CAMERA_STATE.AVAILABLE
            and int(getattr(d, "serial_number", 0) or 0) != 0]


def sequential(avail, res, fps, dur):
    print("\n--- sequential (one at a time) ---")
    npass = 0
    for d in avail:
        sn = int(d.serial_number)
        z, err = _open(sn, res, fps)
        if err != sl.ERROR_CODE.SUCCESS:
            print("  S/N %d: OPEN FAIL %s" % (sn, err)); z.close(); continue
        opened = int(getattr(z.get_camera_information(), "serial_number", 0) or 0)
        if opened != sn:
            print("  S/N %d: MISMATCH (SDK opened %d)" % (sn, opened)); z.close(); continue
        rt = sl.RuntimeParameters(); c = 0; t0 = time.time()
        while time.time() - t0 < dur:
            if z.grab(rt) == sl.ERROR_CODE.SUCCESS:
                c += 1
        dt = time.time() - t0
        print("  S/N %d: PASS ~%.1f fps" % (sn, c / dt if dt else 0))
        npass += 1
        z.close()
    print("  %d/%d camera(s) OK sequentially" % (npass, len(avail)))


def concurrent(avail, res, fps, dur):
    print("\n--- concurrent (%d cameras at once, %s@%d) ---" % (len(avail), res, fps))
    q = mp.Queue()
    procs = [mp.Process(target=_grab_worker, args=(int(d.serial_number), res, fps, dur, q)) for d in avail]
    for p in procs:
        p.start()
    for p in procs:
        p.join()
    ok = 0
    while not q.empty():
        sn, status, fps_meas, note = q.get()
        good = status == "OK" and fps_meas >= fps * 0.9
        ok += good
        print("  S/N %s: %s ~%.1f fps (%s)%s" % (
            sn, status, fps_meas, note, "" if good else "  <-- DEGRADED/BANDWIDTH"))
    print("  %d/%d camera(s) sustain %s@%d simultaneously" % (ok, len(avail), res, fps))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--concurrent", action="store_true")
    ap.add_argument("--res", default="HD720")
    ap.add_argument("--fps", type=int, default=60)
    ap.add_argument("--duration", type=float, default=6.0)
    args = ap.parse_args()

    try:
        print("SDK", sl.Camera.get_sdk_version())
    except Exception:
        pass
    avail = enumerate_devices()
    if not avail:
        print("No AVAILABLE cameras."); sys.exit(1)
    if args.concurrent:
        concurrent(avail, args.res, args.fps, args.duration)
    else:
        sequential(avail, args.res, args.fps, args.duration)


if __name__ == "__main__":
    main()
