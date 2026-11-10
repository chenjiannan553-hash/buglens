"""增量能力集合：批量操作、报表、审计、模板、标签与备注。

设计约束：只读取现有表、只新增 ``templates`` 表，不改任何既有表结构，
也不改动既有命令的参数签名，保证 Super Agent 正在消费的旧库与调用方式不受影响。
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta
from typing import Any, Iterable

from .dedupe import duplicate_groups
from .models import Bug, STATUSES, parse_iso

#: 未闭环状态，SLA / 滞留口径统一在这里定义。
OPEN_STATUSES = ("new", "triaged", "in_progress", "fixed", "reopened")
CLOSED_STATUSES = ("verified", "closed")

#: 滞留时长分桶边界（小时）。
AGING_BUCKETS = (24, 72, 168, 720)


# ---------------------------------------------------------------- 批量操作


def parse_ids(raw: str | None) -> list[int]:
    """把 ``1,2,5-7`` 解析成去重后的升序 ID 列表。"""
    if not raw:
        return []
    result: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, _, b = part.partition("-")
            try:
                lo, hi = int(a), int(b)
            except ValueError as exc:
                raise ValueError(f"无法解析 ID 区间 {part!r}") from exc
            if lo > hi:
                lo, hi = hi, lo
            result.update(range(lo, hi + 1))
        else:
            try:
                result.add(int(part))
            except ValueError as exc:
                raise ValueError(f"无法解析 ID {part!r}") from exc
    return sorted(result)


def select_bugs(store: Any, ids: list[int], **filters: Any) -> list[Bug]:
    """按显式 ID 与筛选条件取交集；两者都没给时抛错，避免误操作全库。"""
    if not ids and not any(filters.values()):
        raise ValueError("必须指定 --ids，或至少给出一个筛选条件")
    candidates = store.list_bugs(**filters)
    if not ids:
        return candidates
    wanted = set(ids)
    return [bug for bug in candidates if bug.id in wanted]


def bulk_set_status(
    store: Any, bugs: list[Bug], to_status: str, actor: str, note: str, dry_run: bool
) -> list[str]:
    """批量状态流转，逐条走状态机校验并留痕；不合法的单条跳过而不中断整批。"""
    from .state_machine import can_transition

    lines: list[str] = []
    for bug in bugs:
        if bug.id is None:
            continue
        if not can_transition(bug.status, to_status):
            lines.append(f"跳过 #{bug.id}：{bug.status} → {to_status} 不符合状态机")
            continue
        if dry_run:
            lines.append(f"[预演] #{bug.id} {bug.status} → {to_status}")
        else:
            store.update_status(bug.id, to_status, actor, note or "批量流转")
            lines.append(f"已流转 #{bug.id} {bug.status} → {to_status}")
    return lines


def bulk_assign(store: Any, bugs: list[Bug], assignee: str, dry_run: bool) -> list[str]:
    lines: list[str] = []
    for bug in bugs:
        if bug.id is None:
            continue
        if dry_run:
            lines.append(f"[预演] #{bug.id} → {assignee}")
        else:
            store.assign(bug.id, assignee)
            lines.append(f"已指派 #{bug.id} → {assignee}")
    return lines


def merge_tags(existing: str, tag: str, remove: bool = False) -> str:
    """加/去标签，保持逗号分隔、去重、顺序稳定。"""
    items = [t.strip() for t in existing.split(",") if t.strip()]
    if remove:
        items = [t for t in items if t != tag]
    elif tag not in items:
        items.append(tag)
    return ",".join(dict.fromkeys(items))


def bulk_tag(
    store: Any, bugs: list[Bug], tag: str, remove: bool, dry_run: bool
) -> list[str]:
    lines: list[str] = []
    for bug in bugs:
        if bug.id is None:
            continue
        new_tags = merge_tags(bug.tags, tag, remove=remove)
        if new_tags == bug.tags:
            lines.append(f"跳过 #{bug.id}：标签无变化")
            continue
        if dry_run:
            lines.append(f"[预演] #{bug.id} {bug.tags!r} → {new_tags!r}")
        else:
            store.set_tags(bug.id, new_tags)
            lines.append(f"已更新 #{bug.id} 标签：{new_tags or '(空)'}")
    return lines


def bulk_remove(store: Any, bugs: list[Bug], dry_run: bool) -> list[str]:
    lines: list[str] = []
    for bug in bugs:
        if bug.id is None:
            continue
        if dry_run:
            lines.append(f"[预演] 删除 #{bug.id} {bug.title}")
        else:
            store.delete_bug(bug.id)
            lines.append(f"已删除 #{bug.id}")
    return lines


# ---------------------------------------------------------------- 报表


def group_counts(bugs: Iterable[Bug], attr: str) -> list[tuple[str, int]]:
    """按任意字段分组计数，按数量倒序、名称正序。"""
    counter: Counter[str] = Counter()
    for bug in bugs:
        value = str(getattr(bug, attr, "") or "(空)")
        counter[value] += 1
    return sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))


def age_hours(bug: Bug, now: datetime | None = None) -> float:
    """未闭环缺陷的滞留小时数。"""
    return max(0.0, ((now or datetime.now()) - parse_iso(bug.created_at)).total_seconds() / 3600)


def aging_buckets(bugs: Iterable[Bug], now: datetime | None = None) -> list[tuple[str, int]]:
    """滞留时长分桶：<24h / 1-3d / 3-7d / 7-30d / >30d。"""
    labels = ["<24小时", "1-3天", "3-7天", "7-30天", ">30天"]
    counts = [0] * len(labels)
    for bug in bugs:
        if bug.status not in OPEN_STATUSES:
            continue
        hours = age_hours(bug, now)
        idx = 0
        for i, boundary in enumerate(AGING_BUCKETS):
            if hours >= boundary:
                idx = i + 1
        counts[idx] += 1
    return list(zip(labels, counts))


def daily_trend(bugs: Iterable[Bug], days: int = 14) -> list[tuple[str, int, int]]:
    """最近 N 天的 (日期, 新增, 闭环)，按日期正序。"""
    today = datetime.now().date()
    start = today - timedelta(days=days - 1)
    added: Counter[str] = Counter()
    closed: Counter[str] = Counter()
    for bug in bugs:
        key = parse_iso(bug.created_at).date()
        if start <= key <= today:
            added[key.isoformat()] += 1
        if bug.status in CLOSED_STATUSES:
            key2 = parse_iso(bug.updated_at).date()
            if start <= key2 <= today:
                closed[key2.isoformat()] += 1
    result = []
    for i in range(days):
        day = (start + timedelta(days=i)).isoformat()
        result.append((day, added.get(day, 0), closed.get(day, 0)))
    return result


def sla_breaches(
    bugs: Iterable[Bug], limit_hours: float, now: datetime | None = None
) -> list[tuple[Bug, float]]:
    """超过 SLA 阈值仍未闭环的缺陷，按超时时长倒序。"""
    hits = [
        (bug, age_hours(bug, now))
        for bug in bugs
        if bug.status in OPEN_STATUSES and age_hours(bug, now) >= limit_hours
    ]
    return sorted(hits, key=lambda pair: -pair[1])


# ---------------------------------------------------------------- 审计


def validate_all(store: Any) -> list[str]:
    """检查必填字段、状态合法性、时间戳可解析性。返回问题清单，空列表表示健康。"""
    from .models import REQUIRED_FIELDS

    problems: list[str] = []
    for bug in store.list_bugs():
        if bug.id is None:
            continue
        for name in REQUIRED_FIELDS:
            if not str(getattr(bug, name, "")).strip():
                problems.append(f"#{bug.id} 缺必填字段 {name}")
        if bug.status not in STATUSES:
            problems.append(f"#{bug.id} 状态非法：{bug.status}")
        if bug.severity not in ("S1", "S2", "S3", "S4"):
            problems.append(f"#{bug.id} 严重级别非法：{bug.severity}")
        for field in ("created_at", "updated_at"):
            raw = str(getattr(bug, field, ""))
            try:
                datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S")
            except (ValueError, TypeError):
                problems.append(f"#{bug.id} {field} 时间格式异常：{raw}")
    return problems


def find_orphans(store: Any) -> list[int]:
    """找出没有任何流转历史的缺陷 ID。"""
    return [bug.id for bug in store.list_bugs() if bug.id is not None and not store.history(bug.id)]


def duplicate_report(bugs: list[Bug], threshold: float) -> list[str]:
    groups = duplicate_groups(bugs, threshold=threshold)
    return [
        "疑似重复：" + ", ".join("#" + str(bug.id) for bug, _score in group)
        for group in groups
    ]


def audit_log(store: Any) -> list[dict[str, Any]]:
    """全库流转审计记录，按时间正序。"""
    return [entry.__dict__ for entry in store.all_history()]


# ---------------------------------------------------------------- 模板与标签


def save_template(store: Any, name: str, bug: Bug) -> None:
    data = bug.to_dict()
    for key in ("id", "created_at", "updated_at", "status"):
        data.pop(key, None)
    store.save_template(name, json.dumps(data, ensure_ascii=False))


def use_template(store: Any, name: str, **overrides: Any) -> Bug:
    raw = store.load_template(name)
    if raw is None:
        raise KeyError(f"模板 {name!r} 不存在")
    data = json.loads(raw)
    data.update({k: v for k, v in overrides.items() if v is not None})
    allowed = set(Bug.__dataclass_fields__)
    return Bug(**{k: v for k, v in data.items() if k in allowed})


def tag_cloud(bugs: Iterable[Bug]) -> list[tuple[str, int]]:
    counter: Counter[str] = Counter()
    for bug in bugs:
        counter.update(bug.tag_list)
    return sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
