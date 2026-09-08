#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ArUco 큐브 데이텀과 카메라 pose 사이의 순수 변환 함수."""

import argparse
import json
import math
from pathlib import Path

import cv2
import numpy as np


R_BODY_OPTICAL = np.array([
    [0.0, 0.0, 1.0],
    [-1.0, 0.0, 0.0],
    [0.0, -1.0, 0.0],
])
T_BODY_OPTICAL = np.eye(4, dtype=float)
T_BODY_OPTICAL[:3, :3] = R_BODY_OPTICAL


def _vector(value, name):
    v = np.asarray(value, dtype=float)
    if v.shape != (3,) or not np.all(np.isfinite(v)):
        raise ValueError("%s는 유한한 숫자 3개여야 합니다" % name)
    return v


def load_datum(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    if data.get("coordinate_system") != "RIGHT_HANDED_Z_UP_X_FWD":
        raise ValueError("coordinate_system은 RIGHT_HANDED_Z_UP_X_FWD여야 합니다")
    if data.get("unit") != "METER":
        raise ValueError("unit은 METER여야 합니다")

    tag_size = float(data["tag_size_m"])
    if not math.isfinite(tag_size) or tag_size <= 0.0:
        raise ValueError("tag_size_m은 양의 유한값이어야 합니다")

    dictionary = str(data["dictionary"])
    transforms = {}

    for item in data["markers"]:
        marker_id = int(item["id"])
        if marker_id in transforms:
            raise ValueError("마커 ID %d가 중복되었습니다" % marker_id)

        center = _vector(item["center_m"], "marker %d center_m" % marker_id)
        normal = _vector(item["normal"], "marker %d normal" % marker_id)
        up = _vector(item["up"], "marker %d up" % marker_id)

        if not np.isclose(np.linalg.norm(normal), 1.0, atol=1e-6):
            raise ValueError("마커 %d normal은 단위벡터여야 합니다" % marker_id)
        if not np.isclose(np.linalg.norm(up), 1.0, atol=1e-6):
            raise ValueError("마커 %d up은 단위벡터여야 합니다" % marker_id)
        if not np.isclose(np.dot(normal, up), 0.0, atol=1e-6):
            raise ValueError("마커 %d normal과 up은 직교해야 합니다" % marker_id)

        right = np.cross(up, normal)
        r = np.column_stack((right, up, normal))
        if not np.allclose(r.T @ r, np.eye(3), atol=1e-6) or not np.isclose(
                np.linalg.det(r), 1.0, atol=1e-6):
            raise ValueError("마커 %d 축이 오른손 정규직교계를 이루지 않습니다" % marker_id)

        t = np.eye(4, dtype=float)
        t[:3, :3] = r
        t[:3, 3] = center
        transforms[marker_id] = t

    if not transforms:
        raise ValueError("markers가 비어 있습니다")

    return transforms, tag_size, dictionary


def object_points(tag_size_m):
    h = float(tag_size_m) / 2.0
    return np.array([
        [-h, h, 0.0],
        [h, h, 0.0],
        [h, -h, 0.0],
        [-h, -h, 0.0],
    ], dtype=np.float32)


def pnp_cam_optical_T_marker(corners_px, tag_size_m, K):
    corners = np.asarray(corners_px, dtype=np.float64).reshape(4, 2)
    camera_matrix = np.asarray(K, dtype=np.float64).reshape(3, 3)

    result = cv2.solvePnPGeneric(
        object_points(tag_size_m), corners, camera_matrix, None,
        flags=cv2.SOLVEPNP_IPPE_SQUARE)
    ok, rvecs, tvecs = result[:3]
    errors = result[3] if len(result) > 3 else None
    if not ok or len(rvecs) == 0:
        return []

    poses = []
    for i, (rvec, tvec) in enumerate(zip(rvecs, tvecs)):
        r, _ = cv2.Rodrigues(np.asarray(rvec, dtype=float))
        t = np.eye(4, dtype=float)
        t[:3, :3] = r
        t[:3, 3] = np.asarray(tvec, dtype=float).reshape(3)

        if errors is None:
            projected, _ = cv2.projectPoints(
                object_points(tag_size_m), rvec, tvec, camera_matrix, None)
            delta = projected.reshape(4, 2) - corners
            error = float(np.sqrt(np.mean(np.sum(delta * delta, axis=1))))
        else:
            error = float(np.asarray(errors).reshape(-1)[i])
        poses.append((t, error))

    return sorted(poses, key=lambda item: item[1])


def base_T_cam_from_marker(T_base_marker, optical_T_marker):
    cam_body_T_marker = T_BODY_OPTICAL @ np.asarray(optical_T_marker, dtype=float)
    return np.asarray(T_base_marker, dtype=float) @ np.linalg.inv(cam_body_T_marker)


def base_T_world(base_T_cam_body, world_T_cam_body):
    return np.asarray(base_T_cam_body, dtype=float) @ np.linalg.inv(world_T_cam_body)


def _mat_to_quat(r):
    # 대각 원소가 작은 180도 부근에서도 큰 항을 기준으로 계산한다.
    m = np.asarray(r, dtype=float)
    trace = float(np.trace(m))
    if trace > 0.0:
        s = math.sqrt(trace + 1.0) * 2.0
        q = np.array([
            (m[2, 1] - m[1, 2]) / s,
            (m[0, 2] - m[2, 0]) / s,
            (m[1, 0] - m[0, 1]) / s,
            0.25 * s,
        ])
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = math.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2.0
        q = np.array([
            0.25 * s,
            (m[0, 1] + m[1, 0]) / s,
            (m[0, 2] + m[2, 0]) / s,
            (m[2, 1] - m[1, 2]) / s,
        ])
    elif m[1, 1] > m[2, 2]:
        s = math.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2.0
        q = np.array([
            (m[0, 1] + m[1, 0]) / s,
            0.25 * s,
            (m[1, 2] + m[2, 1]) / s,
            (m[0, 2] - m[2, 0]) / s,
        ])
    else:
        s = math.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2.0
        q = np.array([
            (m[0, 2] + m[2, 0]) / s,
            (m[1, 2] + m[2, 1]) / s,
            0.25 * s,
            (m[1, 0] - m[0, 1]) / s,
        ])
    return q / np.linalg.norm(q)


def _quat_to_mat(q):
    x, y, z, w = np.asarray(q, dtype=float) / np.linalg.norm(q)
    return np.array([
        [1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - z * w),
         2.0 * (x * z + y * w)],
        [2.0 * (x * y + z * w), 1.0 - 2.0 * (x * x + z * z),
         2.0 * (y * z - x * w)],
        [2.0 * (x * z - y * w), 2.0 * (y * z + x * w),
         1.0 - 2.0 * (x * x + y * y)],
    ])


def average_poses(poses):
    if not poses:
        raise ValueError("평균할 pose가 없습니다")

    mats = [np.asarray(t, dtype=float) for t in poses]
    if any(t.shape != (4, 4) or not np.all(np.isfinite(t)) for t in mats):
        raise ValueError("pose는 유한한 4x4 행렬이어야 합니다")

    quats = [_mat_to_quat(t[:3, :3]) for t in mats]
    markley = sum(np.outer(q, q) for q in quats)
    _, vectors = np.linalg.eigh(markley)
    q = vectors[:, -1]

    result = np.eye(4, dtype=float)
    result[:3, :3] = _quat_to_mat(q)
    result[:3, 3] = np.median([t[:3, 3] for t in mats], axis=0)
    return result


def mat_to_xyzquat(T):
    t = np.asarray(T, dtype=float)
    if t.shape != (4, 4) or not np.all(np.isfinite(t)):
        raise ValueError("T는 유한한 4x4 행렬이어야 합니다")
    return t[:3, 3].copy(), _mat_to_quat(t[:3, :3])


def _rotation_error_deg(a, b):
    r = a[:3, :3].T @ b[:3, :3]
    cosine = np.clip((np.trace(r) - 1.0) / 2.0, -1.0, 1.0)
    return math.degrees(math.acos(cosine))


def selftest():
    example = Path(__file__).resolve().parents[1] / "logs/base_cube_datum.example.json"
    markers, tag_size, dictionary = load_datum(example)
    assert set(markers) == {0, 1, 2}
    assert dictionary == "DICT_5X5_100"
    assert math.isclose(tag_size, 0.10)
    assert np.allclose(markers[1][:3, 3], [0.0, 0.0, 0.0])
    assert np.allclose(markers[2][:3, 3], [-0.0505, 0.0505, 0.0])
    assert np.allclose(markers[0][:3, 3], [-0.0505, -0.0505, 0.0])
    for t in markers.values():
        assert np.allclose(t[:3, :3].T @ t[:3, :3], np.eye(3), atol=1e-9)
        assert np.isclose(np.linalg.det(t[:3, :3]), 1.0)

    # 실제 카메라 시야처럼 마커 법선이 optical -Z를 향하는 합성 자세다.
    rvec = np.array([2.92, 0.12, -0.08], dtype=float)
    r, _ = cv2.Rodrigues(rvec)
    optical_T_marker = np.eye(4, dtype=float)
    optical_T_marker[:3, :3] = r
    optical_T_marker[:3, 3] = [0.035, -0.025, 0.78]

    expected = markers[1] @ np.linalg.inv(T_BODY_OPTICAL @ optical_T_marker)
    K = np.array([[710.0, 0.0, 640.0], [0.0, 708.0, 360.0], [0.0, 0.0, 1.0]])
    projected, _ = cv2.projectPoints(
        object_points(tag_size), rvec, optical_T_marker[:3, 3], K, None)

    solutions = pnp_cam_optical_T_marker(projected, tag_size, K)
    assert len(solutions) == 2
    recovered = base_T_cam_from_marker(markers[1], solutions[0][0])
    translation_mm = np.linalg.norm(expected[:3, 3] - recovered[:3, 3]) * 1000.0
    rotation_deg = _rotation_error_deg(expected, recovered)
    assert translation_mm < 1.0, translation_mm
    assert rotation_deg < 0.1, rotation_deg

    print("selftest 통과: translation=%.6f mm, rotation=%.6f deg" %
          (translation_mm, rotation_deg))


def main():
    parser = argparse.ArgumentParser(description="ArUco 큐브 데이텀 변환 함수 검증")
    parser.add_argument("--selftest", action="store_true", help="합성 pose 라운드트립 검증")
    args = parser.parse_args()

    if args.selftest:
        selftest()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
