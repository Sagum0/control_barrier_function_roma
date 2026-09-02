"""Piper chunk-sync client의 순차 action 실행 회귀 테스트다."""

from __future__ import annotations

from types import SimpleNamespace
import time
import unittest

import torch

from piper_vla.inference.sync_client import _execute_action_chunk


class _TimedAction:
    """실제 LeRobot TimedAction과 같은 action getter를 제공한다."""

    def __init__(self, values: list[float]) -> None:
        self._action = torch.tensor(values, dtype=torch.float32)

    def get_action(self) -> torch.Tensor:
        return self._action


class _Robot:
    """동기 loop가 발행한 action 순서만 기록하는 가짜 Piper robot이다."""

    action_features = {f"joint_{index}.pos": float for index in range(1, 7)} | {
        "gripper.pos": float
    }

    def __init__(self) -> None:
        self.sent: list[dict[str, float]] = []

    def send_action(self, action: dict[str, float]) -> dict[str, float]:
        self.sent.append(action)
        return action


class SyncClientTest(unittest.TestCase):
    """sync client는 queue 합성 없이 받은 순서 그대로 실행해야 한다."""

    def test_executes_complete_chunk_in_order(self) -> None:
        robot = _Robot()
        client = SimpleNamespace(robot=robot)
        actions = [
            _TimedAction([1, 2, 3, 4, 5, 6, 7]),
            _TimedAction([8, 9, 10, 11, 12, 13, 14]),
        ]

        executed = _execute_action_chunk(client, actions, fps=100, deadline=None)

        self.assertEqual(executed, 2)
        self.assertEqual(robot.sent[0]["joint_1.pos"], 1.0)
        self.assertEqual(robot.sent[1]["joint_1.pos"], 8.0)
        self.assertEqual(robot.sent[1]["gripper.pos"], 14.0)

    def test_expired_episode_does_not_publish_action(self) -> None:
        robot = _Robot()
        client = SimpleNamespace(robot=robot)

        executed = _execute_action_chunk(
            client,
            [_TimedAction([0] * 7)],
            fps=20,
            deadline=time.monotonic() - 1.0,
        )

        self.assertEqual(executed, 0)
        self.assertEqual(robot.sent, [])


if __name__ == "__main__":
    unittest.main()
