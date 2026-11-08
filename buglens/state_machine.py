"""缺陷状态机。

设计原则：非法流转一律拒绝，不做"好心放行"。
每一次流转都要能解释成业务上说得通的动作。
"""

from __future__ import annotations

from .models import STATUSES, STATUS_LABELS

#: 合法流转表。key 为当前状态，value 为允许迁移到的状态集合。
TRANSITIONS: dict[str, set[str]] = {
    "new": {"triaged", "closed", "reopened"},
    "triaged": {"in_progress", "closed", "new"},
    "in_progress": {"fixed", "triaged", "closed"},
    "fixed": {"verified", "reopened", "in_progress"},
    "verified": {"closed", "reopened"},
    "closed": {"reopened"},
    "reopened": {"triaged", "in_progress", "closed"},
}

#: 各流转需要的最小角色要求，供 CLI 提示用（不做强制鉴权）。
TRANSITION_HINTS = {
    ("new", "triaged"): "分诊人确认复现信息完整",
    ("triaged", "in_progress"): "开发认领并开始修复",
    ("in_progress", "fixed"): "开发自测通过，提交待验证",
    ("fixed", "verified"): "测试在目标环境回归通过",
    ("fixed", "reopened"): "测试回归失败",
    ("verified", "closed"): "验收通过，随版本关闭",
    ("closed", "reopened"): "线上复现，重新打开",
}


class TransitionError(ValueError):
    """非法状态流转。"""


def can_transition(from_status: str, to_status: str) -> bool:
    """判断流转是否合法。同状态视为幂等成功。"""
    if from_status == to_status:
        return True
    if from_status not in TRANSITIONS:
        return False
    return to_status in TRANSITIONS[from_status]


def allowed_targets(from_status: str) -> list[str]:
    """列出当前状态可以去往的状态，按 STATUSES 顺序返回。"""
    targets = TRANSITIONS.get(from_status, set())
    return [s for s in STATUSES if s in targets]


def assert_transition(from_status: str, to_status: str) -> None:
    """非法则抛异常，异常信息带上可选目标，方便直接改命令。"""
    if to_status not in STATUSES:
        raise TransitionError(
            f"未知状态 '{to_status}'，可选：{', '.join(STATUSES)}"
        )
    if can_transition(from_status, to_status):
        return
    targets = allowed_targets(from_status)
    hint = f"可选目标：{', '.join(targets)}" if targets else "该状态为终态区，仅可 reopened"
    raise TransitionError(
        f"不允许 {STATUS_LABELS.get(from_status, from_status)} → "
        f"{STATUS_LABELS.get(to_status, to_status)}。{hint}"
    )
