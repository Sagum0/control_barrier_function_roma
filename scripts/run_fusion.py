#!/usr/bin/env python3
"""ZED360 캘리브레이션을 강제한 뒤 Fusion 스크립트를 실행한다."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import time


DEFAULT_ZED360 = "/usr/local/zed/tools/ZED360"
DEFAULT_CALIB = "logs/fusion_zed360.json"
COORD_NAME = "RIGHT_HANDED_Z_UP_X_FWD"
UNIT_NAME = "METER"
TARGETS = {
    "viz": "zed_fusion_viz.py",
    "bodytrack": "zed_fusion_bodytrack.py",
    "fulllog": "zed_fusion_fulllog.py",
}
CONFIG_FLAGS = ("--config", "--calib")


class LauncherError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _split_passthrough(argv):
    if "--" not in argv:
        return argv, []
    idx = argv.index("--")
    return argv[:idx], argv[idx + 1:]


def _parse_args(argv):
    launcher_argv, passthrough = _split_passthrough(argv)
    parser = argparse.ArgumentParser(
        description="ZED360 캘리브레이션 후 Dual ZED-M Fusion을 실행한다.",
        epilog="Fusion 스크립트 인자는 '--' 뒤에 그대로 전달한다. 예: scripts/run_fusion.py viz -- --view front --save",
    )
    parser.add_argument("target", nargs="?", choices=sorted(TARGETS), default="viz",
                        help="실행할 Fusion 대상 스크립트 (default: viz)")
    parser.add_argument("--calib", default=None, metavar="PATH",
                        help="ZED360 export 대상이자 Fusion 입력 config (default: %s)" % DEFAULT_CALIB)
    parser.add_argument("--zed360", default=DEFAULT_ZED360, metavar="PATH",
                        help="ZED360 GUI 실행 파일 (default: %s)" % DEFAULT_ZED360)
    parser.add_argument("--skip-calib", action="store_true",
                        help="ZED360을 생략하고 기존 --calib 파일을 재사용한다.")
    parser.add_argument("--max-age", type=float, default=None, metavar="MIN",
                        help="config가 MIN분 이내이고 유효하면 ZED360을 생략한다.")
    args = parser.parse_args(launcher_argv)
    if args.max_age is not None and args.max_age < 0:
        parser.error("--max-age must be >= 0")
    return args, passthrough


def _repo_root():
    return Path(__file__).resolve().parents[1]


def _calib_path(value):
    if value:
        return Path(value).expanduser().resolve()
    return (_repo_root() / DEFAULT_CALIB).resolve()


def _check_passthrough(passthrough):
    for item in passthrough:
        for flag in CONFIG_FLAGS:
            if item == flag or item.startswith(flag + "="):
                raise LauncherError(2, "error: --config/--calib 은 런처가 주입합니다. '--' 뒤 인자에서 제거하세요.")


def _load_zed_sdk():
    try:
        import pyzed.sl as sl
    except Exception as exc:
        raise LauncherError(1, "error: pyzed.sl import 실패. ZED SDK/zed Python 환경에서 실행하세요: %s" % exc)
    return sl


def _constants(sl):
    return (
        sl.COORDINATE_SYSTEM.RIGHT_HANDED_Z_UP_X_FWD,
        sl.UNIT.METER,
    )


def _connected_serials(sl):
    serials = []
    states = {}
    try:
        devices = sl.Camera.get_device_list()
    except Exception as exc:
        raise LauncherError(1, "error: ZED 카메라 목록을 읽지 못했습니다: %s" % exc)

    for dev in devices:
        serial = int(getattr(dev, "serial_number", 0) or 0)
        if not serial:
            continue
        serials.append(serial)
        states[serial] = getattr(dev, "camera_state", None)

    serials = sorted(set(serials))
    if len(serials) < 2:
        raise LauncherError(1, "error: Fusion에는 ZED 카메라 2대 이상이 필요합니다. 현재 감지: %s" % serials)

    print("연결된 ZED serial:", serials)
    for serial in serials:
        state = states.get(serial)
        if state is not None:
            print("  S/N %s state=%s" % (serial, state))
    return serials


def _read_config(sl, calib):
    coord, unit = _constants(sl)
    try:
        configs = sl.read_fusion_configuration_file(str(calib), coord, unit)
    except Exception as exc:
        raise LauncherError(1, "error: Fusion config를 읽지 못했습니다: %s (%s)" % (calib, exc))
    if len(configs) < 2:
        raise LauncherError(1, "error: Fusion config에는 카메라가 2대 이상 필요합니다: %s" % calib)
    return configs


def _validate_config(sl, calib, connected_serials):
    if not calib.exists():
        raise LauncherError(1, "error: 캘리브 config 파일이 없습니다: %s" % calib)

    configs = _read_config(sl, calib)
    config_serials = sorted({int(conf.serial_number) for conf in configs})
    connected = set(connected_serials)
    missing = [serial for serial in config_serials if serial not in connected]
    if missing:
        raise LauncherError(
            1,
            "error: config serial이 현재 연결된 카메라와 일치하지 않습니다. config=%s connected=%s missing=%s"
            % (config_serials, sorted(connected), missing),
        )

    extras = sorted(connected - set(config_serials))
    if extras:
        print("warning: 연결됐지만 config에 없는 카메라가 있습니다:", extras)

    print("config 검증 통과: %s (%s, %s) serial=%s" % (calib, COORD_NAME, UNIT_NAME, config_serials))
    return configs


def _age_minutes(path):
    return max(0.0, (time.time() - path.stat().st_mtime) / 60.0)


def _is_fresh_by_age(path, max_age):
    if max_age is None or not path.exists():
        return False
    return _age_minutes(path) <= max_age


def _display_available():
    return bool(os.environ.get("DISPLAY"))


def _warn_manual_config(calib):
    if calib.name == "fusion_manual.json":
        print("warning: logs/fusion_manual.json 은 placeholder/manual config 입니다. 실사용은 ZED360 export 결과를 권장합니다.")


def _run_zed360(zed360, calib):
    print("")
    print("ZED360 이 열립니다.")
    print("  1. 두 카메라를 추가하세요.")
    print("  2. 사람이 공간을 걸어 캘리브레이션하세요.")
    print("  3. config 를 다음 경로로 Export/Save 하세요: %s" % calib)
    print("  4. 저장 후 ZED360 을 종료하세요.")
    print("")

    start_time = time.time()
    try:
        result = subprocess.run([str(zed360)])
    except FileNotFoundError:
        raise LauncherError(2, "error: ZED360 실행 파일을 찾지 못했습니다: %s" % zed360)
    except OSError as exc:
        raise LauncherError(2, "error: ZED360 실행 실패: %s (%s)" % (zed360, exc))

    if result.returncode != 0:
        print("warning: ZED360 종료 코드가 0이 아닙니다: %s" % result.returncode)

    if not calib.exists() or calib.stat().st_mtime < start_time:
        raise LauncherError(3, "error: 새 캘리브 config 가 %s 로 저장되지 않았습니다. Export 경로를 확인하세요." % calib)


def _should_skip_by_max_age(sl, calib, connected_serials, max_age):
    if not _is_fresh_by_age(calib, max_age):
        return False
    try:
        _validate_config(sl, calib, connected_serials)
    except LauncherError as exc:
        print("warning: --max-age 후보 config가 유효하지 않아 ZED360 캘리브레이션을 진행합니다: %s" % exc)
        return False
    print("캘리브 config가 %.1f분 이내라 ZED360을 생략합니다: %s" % (_age_minutes(calib), calib))
    return True


def _run_fusion(target, calib, passthrough):
    script = Path(__file__).resolve().parent / TARGETS[target]
    cmd = [sys.executable, str(script), "--config", str(calib)] + list(passthrough)
    print("Fusion 실행:", " ".join(cmd))
    return subprocess.run(cmd).returncode


def main(argv=None):
    args, passthrough = _parse_args(sys.argv[1:] if argv is None else argv)
    calib = _calib_path(args.calib)
    zed360 = Path(args.zed360).expanduser()

    try:
        _check_passthrough(passthrough)
        _warn_manual_config(calib)

        if args.skip_calib and not calib.exists():
            raise LauncherError(1, "error: --skip-calib 이지만 config 파일이 없습니다: %s" % calib)

        needs_calib_by_age = not args.skip_calib and not _is_fresh_by_age(calib, args.max_age)
        if needs_calib_by_age and not _display_available():
            raise LauncherError(2, "error: DISPLAY가 없어 ZED360 GUI 캘리브레이션을 실행할 수 없습니다. 디스플레이 세션에서 실행하거나 --skip-calib 을 사용하세요.")

        sl = _load_zed_sdk()
        connected = _connected_serials(sl)

        skip_calib = False
        if args.skip_calib:
            _validate_config(sl, calib, connected)
            print("warning: --skip-calib 사용. 기존 config를 재사용합니다: %s (age=%.1f분)" % (calib, _age_minutes(calib)))
            skip_calib = True
        elif _should_skip_by_max_age(sl, calib, connected, args.max_age):
            skip_calib = True

        if not skip_calib:
            if not _display_available():
                raise LauncherError(2, "error: DISPLAY가 없어 ZED360 GUI 캘리브레이션을 실행할 수 없습니다. 디스플레이 세션에서 실행하거나 --skip-calib 을 사용하세요.")
            _run_zed360(zed360, calib)
            _validate_config(sl, calib, connected)

        return _run_fusion(args.target, calib, passthrough)

    except LauncherError as exc:
        print(exc)
        return exc.code


if __name__ == "__main__":
    sys.exit(main())
