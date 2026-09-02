"""OpenPI gRPC 응답을 chunk 단위로 기다려 순차 실행하는 Piper client다."""

from __future__ import annotations

import argparse
import math
import pickle  # nosec: 신뢰된 로컬 LeRobot gRPC server 호환 payload다.
import time
from typing import Any, Sequence


ROBOT_DIM = 7
ROBOT_READY_TIMEOUT_SECONDS = 10.0


def build_argument_parser() -> argparse.ArgumentParser:
    """YAML launcher만 호출하는 동기 client 내부 parser를 만든다."""

    parser = argparse.ArgumentParser(description="Piper chunk-synchronous OpenPI client")
    parser.add_argument("--server-address", required=True)
    parser.add_argument("--checkpoint-label", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--actions-per-chunk", type=int, required=True)
    parser.add_argument("--fps", type=int, required=True)
    parser.add_argument("--episode-time-seconds", type=float)
    return parser


def _validate_arguments(namespace: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    """launcher가 넘긴 동기 실행 공통값을 방어적으로 다시 검증한다."""

    if not namespace.server_address.strip():
        parser.error("--server-address는 비어 있을 수 없습니다.")
    if not namespace.checkpoint_label.strip():
        parser.error("--checkpoint-label은 비어 있을 수 없습니다.")
    if not namespace.task.strip():
        parser.error("--task는 비어 있을 수 없습니다.")
    if not 1 <= namespace.actions_per_chunk <= 50:
        parser.error("--actions-per-chunk는 1~50이어야 합니다.")
    if not 1 <= namespace.fps <= 100:
        parser.error("--fps는 1~100이어야 합니다.")
    duration = namespace.episode_time_seconds
    if duration is not None and (not math.isfinite(duration) or duration <= 0.0):
        parser.error("--episode-time-seconds는 유한한 양수여야 합니다.")


def _remaining_seconds(deadline: float | None) -> float | None:
    """유한 episode의 남은 monotonic 시간을 gRPC timeout용으로 반환한다."""

    if deadline is None:
        return None
    return max(0.0, deadline - time.monotonic())


def _wait_for_robot_observation(client: Any) -> dict[str, Any]:
    """ROS bridge 연결 직후 첫 SyncedFrame이 도착할 때까지 제한적으로 기다린다."""

    from lerobot.utils.errors import DeviceNotConnectedError

    deadline = time.monotonic() + ROBOT_READY_TIMEOUT_SECONDS
    while True:
        try:
            return client.robot.get_observation()
        except DeviceNotConnectedError:
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    "10초 안에 feedback/image가 도착하지 않았습니다. "
                    "data_hub와 rosbridge를 확인하세요."
                ) from None
            time.sleep(0.1)


def _receive_action_chunk(
    client: Any,
    *,
    expected_size: int,
    expected_first_timestep: int,
    timeout: float | None,
) -> list[Any]:
    """한 observation의 추론이 끝날 때까지 기다리고 `(N, 7)` action을 검증한다."""

    import torch
    from lerobot.async_inference.helpers import TimedAction
    from lerobot.transport import services_pb2

    call = client.stub.GetActions
    response = (
        call(services_pb2.Empty())
        if timeout is None
        else call(services_pb2.Empty(), timeout=max(timeout, 0.001))
    )
    if not response.data:
        raise RuntimeError("policy server가 빈 action chunk를 반환했습니다.")
    actions = pickle.loads(response.data)  # nosec: localhost의 검증된 server 응답이다.
    if not isinstance(actions, list) or len(actions) != expected_size:
        raise ValueError(
            f"동기 action chunk 길이가 잘못됐습니다: expected={expected_size}, "
            f"actual={len(actions) if isinstance(actions, list) else type(actions).__name__}"
        )
    for index, timed_action in enumerate(actions):
        if not isinstance(timed_action, TimedAction):
            raise TypeError(f"actions[{index}]가 TimedAction이 아닙니다.")
        expected_timestep = expected_first_timestep + index
        if timed_action.get_timestep() != expected_timestep:
            raise ValueError(
                f"actions[{index}] timestep 불일치: "
                f"expected={expected_timestep}, actual={timed_action.get_timestep()}"
            )
        tensor = timed_action.get_action()
        if not isinstance(tensor, torch.Tensor) or tensor.numel() != ROBOT_DIM:
            raise ValueError(f"actions[{index}]은 {ROBOT_DIM}차원 tensor여야 합니다.")
        if not bool(torch.isfinite(tensor).all()):
            raise ValueError(f"actions[{index}]에 NaN 또는 Inf가 있습니다.")
    return actions


def _execute_action_chunk(
    client: Any,
    actions: Sequence[Any],
    *,
    fps: int,
    deadline: float | None,
) -> int:
    """추론이 끝난 chunk를 aggregation 없이 정확한 주기로 순차 실행한다."""

    period = 1.0 / fps
    next_tick = time.monotonic()
    executed = 0
    action_keys = tuple(client.robot.action_features)
    if len(action_keys) != ROBOT_DIM:
        raise ValueError(f"Piper action feature는 {ROBOT_DIM}개여야 합니다: {action_keys}")

    for timed_action in actions:
        if deadline is not None and time.monotonic() >= deadline:
            break
        values = timed_action.get_action().detach().to("cpu").reshape(-1)
        client.robot.send_action(
            {key: float(values[index].item()) for index, key in enumerate(action_keys)}
        )
        executed += 1
        next_tick += period
        sleep_seconds = next_tick - time.monotonic()
        if sleep_seconds > 0.0:
            if deadline is not None:
                sleep_seconds = min(sleep_seconds, max(0.0, deadline - time.monotonic()))
            time.sleep(sleep_seconds)
    return executed


def run_sync_client(namespace: argparse.Namespace) -> int:
    """관측·추론·chunk 실행을 한 thread에서 순서대로 반복한다."""

    import grpc
    import piper_bridge

    piper_bridge.configure_lerobot_async_file_logging()

    from lerobot.async_inference.configs import RobotClientConfig
    from lerobot.async_inference.helpers import TimedObservation
    from lerobot.async_inference.robot_client import RobotClient
    from piper_bridge.config_piper_bridge import PiperBridgeRobotConfig

    # RobotClient 생성자에 필요한 async field는 고정 placeholder다. sync loop는
    # control_loop, action_queue, aggregation 함수를 호출하지 않으므로 동작에 사용되지 않는다.
    config = RobotClientConfig(
        policy_type="pi0",
        pretrained_name_or_path=namespace.checkpoint_label,
        robot=PiperBridgeRobotConfig(),
        actions_per_chunk=namespace.actions_per_chunk,
        task=namespace.task,
        server_address=namespace.server_address,
        policy_device="cuda",
        client_device="cpu",
        chunk_size_threshold=0.0,
        fps=namespace.fps,
        aggregate_fn_name="latest_only",
        debug_visualize_queue_size=False,
    )
    client = RobotClient(config)
    total_actions = 0
    total_chunks = 0
    started = False
    try:
        if not client.start():
            raise ConnectionError(f"policy server 연결 실패: {namespace.server_address}")
        started = True
        first_observation = _wait_for_robot_observation(client)
        episode_start = time.monotonic()
        deadline = (
            None
            if namespace.episode_time_seconds is None
            else episode_start + namespace.episode_time_seconds
        )
        print(
            "[sync] started: observation -> inference wait -> "
            f"{namespace.actions_per_chunk} actions @ {namespace.fps}Hz"
        )

        next_timestep = 0
        pending_observation: dict[str, Any] | None = first_observation
        while deadline is None or time.monotonic() < deadline:
            raw_observation = (
                pending_observation
                if pending_observation is not None
                else client.robot.get_observation()
            )
            pending_observation = None
            raw_observation["task"] = namespace.task
            observation = TimedObservation(
                timestamp=time.time(),
                timestep=next_timestep,
                observation=raw_observation,
                must_go=True,
            )
            if not client.send_observation(observation):
                raise ConnectionError("policy server로 observation 전송에 실패했습니다.")

            remaining = _remaining_seconds(deadline)
            if remaining is not None and remaining <= 0.0:
                break
            try:
                actions = _receive_action_chunk(
                    client,
                    expected_size=namespace.actions_per_chunk,
                    expected_first_timestep=next_timestep,
                    timeout=remaining,
                )
            except grpc.RpcError as error:
                if deadline is not None and time.monotonic() >= deadline:
                    break
                raise ConnectionError(f"동기 action 수신 실패: {error}") from error

            executed = _execute_action_chunk(
                client,
                actions,
                fps=namespace.fps,
                deadline=deadline,
            )
            total_actions += executed
            total_chunks += 1
            next_timestep += executed
            print(
                f"[sync] chunk={total_chunks - 1} received={len(actions)} "
                f"executed={executed} total_actions={total_actions}"
            )
            if executed != len(actions):
                break
    except KeyboardInterrupt:
        print("\n[sync] Ctrl+C: 종료합니다.")
    finally:
        # RobotClient 생성 시 robot은 이미 연결되므로 handshake 실패도 반드시 정리한다.
        client.stop()
        print(
            f"[sync] stopped: started={started} chunks={total_chunks} "
            f"actions={total_actions}"
        )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """CLI 값을 검사하고 동기 client를 실행한다."""

    parser = build_argument_parser()
    namespace = parser.parse_args(argv)
    _validate_arguments(namespace, parser)
    return run_sync_client(namespace)


if __name__ == "__main__":
    raise SystemExit(main())
