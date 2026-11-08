"""状态机流转测试。"""

from __future__ import annotations

import unittest

from buglens.models import STATUSES
from buglens.state_machine import (
    TransitionError,
    allowed_targets,
    assert_transition,
    can_transition,
)


class TestTransitions(unittest.TestCase):
    def test_normal_happy_path(self):
        path = ["new", "triaged", "in_progress", "fixed", "verified", "closed"]
        for src, dst in zip(path, path[1:]):
            with self.subTest(src=src, dst=dst):
                self.assertTrue(can_transition(src, dst))

    def test_same_status_is_idempotent(self):
        for status in STATUSES:
            with self.subTest(status=status):
                self.assertTrue(can_transition(status, status))

    def test_cannot_skip_verification(self):
        """new 不能直接跳到 closed 之外的终点，也不能跳到 fixed。"""
        self.assertFalse(can_transition("new", "fixed"))
        self.assertFalse(can_transition("new", "verified"))

    def test_closed_can_only_reopen(self):
        targets = allowed_targets("closed")
        self.assertEqual(targets, ["reopened"])

    def test_reopened_is_not_dead_end(self):
        self.assertTrue(can_transition("reopened", "in_progress"))

    def test_assert_raises_with_hint(self):
        with self.assertRaises(TransitionError) as ctx:
            assert_transition("new", "verified")
        msg = str(ctx.exception)
        self.assertIn("可选目标", msg)

    def test_unknown_status_rejected(self):
        with self.assertRaises(TransitionError) as ctx:
            assert_transition("new", "done")
        self.assertIn("未知状态", str(ctx.exception))

    def test_nonexistent_from_status(self):
        self.assertFalse(can_transition("ghost", "closed"))

    def test_every_status_has_entry(self):
        for status in STATUSES:
            with self.subTest(status=status):
                self.assertIsInstance(allowed_targets(status), list)


if __name__ == "__main__":
    unittest.main()
