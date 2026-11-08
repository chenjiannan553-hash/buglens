"""数据模型与常量定义。

只依赖标准库，保证 pip 之外克隆即可运行。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

#: 严重级别，从高到低。S1 为阻断级，发布门禁会卡住它。
SEVERITIES = ("S1", "S2", "S3", "S4")

#: 严重级别释义，用于报告和 CLI 提示。
SEVERITY_LABELS = {
    "S1": "阻断：核心链路不可用 / 数据丢失 / 安全漏洞",
    "S2": "严重：主流程受损，无绕过方案",
    "S3": "一般：有绕过方案，影响体验",
    "S4": "轻微：文案、样式、边缘问题",
}

#: 缺陷状态，顺序即默认展示顺序。
STATUSES = (
    "new",
    "triaged",
    "in_progress",
    "fixed",
    "verified",
    "closed",
    "reopened",
)

STATUS_LABELS = {
    "new": "待确认",
    "triaged": "已分诊",
    "in_progress": "修复中",
    "fixed": "待验证",
    "verified": "已验证",
    "closed": "已关闭",
    "reopened": "重新打开",
}

#: 必填字段：缺任何一个都不允许入库。
REQUIRED_FIELDS = ("title", "module", "severity", "reporter", "env", "steps", "actual", "expected")

FIELD_LABELS = {
    "title": "标题",
    "module": "模块",
    "severity": "严重级别",
    "reporter": "报告人",
    "env": "复现环境",
    "steps": "复现步骤",
    "actual": "实际结果",
    "expected": "期望结果",
    "assignee": "处理人",
    "tags": "标签",
}

ISO = "%Y-%m-%dT%H:%M:%S"


def now_iso() -> str:
    """当前时间的 ISO 字符串（本地时区，秒级）。"""
    return datetime.now().replace(microsecond=0).strftime(ISO)


def parse_iso(value: str) -> datetime:
    """把库里的 ISO 字符串转回 datetime，容错返回当前时间。"""
    for fmt in (ISO, "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except (ValueError, TypeError):
            continue
    return datetime.now()


@dataclass
class Bug:
    """一条缺陷记录。字段与 SQLite 表一一对应。"""

    title: str
    module: str
    severity: str = "S3"
    status: str = "new"
    reporter: str = ""
    env: str = ""
    steps: str = ""
    actual: str = ""
    expected: str = ""
    assignee: str = ""
    tags: str = ""
    id: int | None = None
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "module": self.module,
            "severity": self.severity,
            "status": self.status,
            "reporter": self.reporter,
            "env": self.env,
            "steps": self.steps,
            "actual": self.actual,
            "expected": self.expected,
            "assignee": self.assignee,
            "tags": self.tags,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_row(cls, row: Any) -> "Bug":
        data = dict(row)
        allowed = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in allowed})

    @property
    def tag_list(self) -> list[str]:
        return [t.strip() for t in self.tags.split(",") if t.strip()]


@dataclass
class HistoryEntry:
    """状态流转审计记录。每次状态变更必须留痕。"""

    bug_id: int
    from_status: str | None
    to_status: str
    actor: str
    note: str = ""
    at: str = field(default_factory=now_iso)
    id: int | None = None


@dataclass
class ChecklistItem:
    """发布验收清单条目。"""

    release: str
    item: str
    done: bool = False
    owner: str = ""
    created_at: str = field(default_factory=now_iso)
    id: int | None = None


def utc_stamp() -> str:
    """给导出文件名用的紧凑时间戳。"""
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
