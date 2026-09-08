#!/usr/bin/env python3
"""ZED 카메라로 ArUco 마커(5x5, 100mm, ID 0/1/2)를 검출해 imshow로 확인하는 테스트.

각 ZED 창마다 검출된 마커 외곽·좌표축·ID·거리(m)를 그려 준다. PLAN05 앵커 도구를
만들기 전에 "검출이 되는가 / 축 방향이 상식적인가 / 거리가 맞는가"를 눈으로 통과시키는 용도.

- depth 는 쓰지 않는다(DEPTH_MODE.NONE): ArUco PnP 는 태그 크기 + intrinsic 만 쓰는 monocular.
- retrieve_image(LEFT) 는 rectified/undistorted → solvePnP 의 distortion 은 0.
- intrinsic 은 calibration_parameters.left_cam(raw 아님), 연 해상도(HD720) 기준.
- 좌표축/tvec 은 OpenCV 카메라 프레임 기준(이 테스트는 프레임 변환 없이 거리만 본다).

실행(conda zed env):
    python3 scripts/aruco_zed_test.py
    python3 scripts/aruco_zed_test.py --serial 13870389   # 한 대만
    q 또는 ESC 로 종료.
"""
import argparse

import cv2
import numpy as np
import pyzed.sl as sl

# 지원되는 5x5 딕셔너리 이름 → cv2 상수
DICT_NAME = "DICT_5X5_100"
MARKER_LENGTH_M = 0.10          # 100mm (검은 사각형 한 변, 흰 여백 제외)
ALLOWED_IDS = {0, 1, 2}


def make_object_points(length):
    """태그 중심을 원점으로 한 정사각 4코너. OpenCV aruco 코너 순서와 맞춘다
    (top-left, top-right, bottom-right, bottom-left). IPPE_SQUARE 규약과 동일."""
    h = length / 2.0
    return np.array([
        [-h,  h, 0.0],
        [ h,  h, 0.0],
        [ h, -h, 0.0],
        [-h, -h, 0.0],
    ], dtype=np.float32)


def make_detector(dict_name):
    """OpenCV 4.7+ (ArucoDetector) 우선, 구버전이면 폴백. 검출 함수를 돌려준다."""
    dict_id = getattr(cv2.aruco, dict_name)
    try:
        aruco_dict = cv2.aruco.getPredefinedDictionary(dict_id)
        detector = cv2.aruco.ArucoDetector(aruco_dict, cv2.aruco.DetectorParameters())

        def detect(gray):
            return detector.detectMarkers(gray)
    except AttributeError:
        aruco_dict = cv2.aruco.Dictionary_get(dict_id)
        params = cv2.aruco.DetectorParameters_create()

        def detect(gray):
            return cv2.aruco.detectMarkers(gray, aruco_dict, parameters=params)
    return detect


def get_K(zed):
    """rectified left 카메라 intrinsic → 3x3 K. distortion 은 rectified라 0."""
    cam = zed.get_camera_information().camera_configuration.calibration_parameters.left_cam
    K = np.array([
        [cam.fx, 0.0,    cam.cx],
        [0.0,    cam.fy, cam.cy],
        [0.0,    0.0,    1.0],
    ], dtype=np.float64)
    return K


def open_cameras(serial_filter):
    """연결된 ZED 를 열어 [(serial, zed), ...] 반환. depth off, HD720@30, METER."""
    cams = []
    for dev in sl.Camera.get_device_list():
        sn = dev.serial_number
        if serial_filter is not None and sn != serial_filter:
            continue
        zed = sl.Camera()
        init = sl.InitParameters()
        init.set_from_serial_number(sn)
        init.camera_resolution = sl.RESOLUTION.HD720
        init.camera_fps = 30
        init.depth_mode = sl.DEPTH_MODE.NONE
        init.coordinate_units = sl.UNIT.METER
        status = zed.open(init)
        if status != sl.ERROR_CODE.SUCCESS:
            print("[open 실패] serial=%s: %s" % (sn, status))
            zed.close()
            continue
        cams.append((sn, zed))
        print("[open] serial=%s" % sn)
    return cams


def main():
    parser = argparse.ArgumentParser(description="ZED ArUco 검출 imshow 테스트")
    parser.add_argument("--serial", type=int, default=None, help="특정 카메라만 (기본: 전부)")
    parser.add_argument("--dict", default=DICT_NAME, help="aruco 딕셔너리 (기본 DICT_5X5_100)")
    parser.add_argument("--size", type=float, default=MARKER_LENGTH_M, help="마커 한 변(m), 검은 사각형만")
    parser.add_argument("--ids", default="0,1,2", help="허용 ID (쉼표 구분). 'all' 이면 전부")
    args = parser.parse_args()

    allowed = None if args.ids.strip() == "all" else {int(x) for x in args.ids.split(",") if x.strip()}

    cams = open_cameras(args.serial)
    if not cams:
        print("카메라를 찾지 못했습니다.")
        return

    detect = make_detector(args.dict)
    obj_pts = make_object_points(args.size)
    dist = np.zeros((5, 1), dtype=np.float64)   # rectified → 왜곡 0
    Ks = {sn: get_K(zed) for sn, zed in cams}

    runtime = sl.RuntimeParameters()
    image = sl.Mat()
    axis_len = args.size * 0.5

    print("q 또는 ESC 로 종료.")
    try:
        while True:
            for sn, zed in cams:
                if zed.grab(runtime) != sl.ERROR_CODE.SUCCESS:
                    continue
                zed.retrieve_image(image, sl.VIEW.LEFT)
                bgra = image.get_data()                       # H x W x 4 (BGRA)
                bgr = cv2.cvtColor(bgra, cv2.COLOR_BGRA2BGR)
                gray = cv2.cvtColor(bgra, cv2.COLOR_BGRA2GRAY)

                corners, ids, _ = detect(gray)
                if ids is not None:
                    for c, marker_id in zip(corners, ids.flatten()):
                        marker_id = int(marker_id)
                        if allowed is not None and marker_id not in allowed:
                            continue
                        ok, rvec, tvec = cv2.solvePnP(
                            obj_pts, c[0], Ks[sn], dist, flags=cv2.SOLVEPNP_IPPE_SQUARE)
                        if not ok:
                            continue
                        cv2.aruco.drawDetectedMarkers(bgr, [c], np.array([[marker_id]]))
                        cv2.drawFrameAxes(bgr, Ks[sn], dist, rvec, tvec, axis_len)
                        dist_m = float(np.linalg.norm(tvec))
                        cx, cy = c[0].mean(axis=0).astype(int)
                        cv2.putText(bgr, "ID %d  %.3f m" % (marker_id, dist_m),
                                    (cx - 50, cy - 12), cv2.FONT_HERSHEY_SIMPLEX,
                                    0.6, (0, 255, 0), 2)
                        print("[%s] ID=%d dist=%.3fm tvec=%s" %
                              (sn, marker_id, dist_m, np.round(tvec.flatten(), 3).tolist()))

                cv2.imshow("ZED %s" % sn, bgr)

            key = cv2.waitKey(1) & 0xFF
            if key in (ord('q'), 27):   # q or ESC
                break
    finally:
        for sn, zed in cams:
            zed.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
