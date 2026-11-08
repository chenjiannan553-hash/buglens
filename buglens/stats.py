"""统计与趋势分析。

所有统计都基于内存中的 Bug 列表，调用方负责先过滤。
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import timedelta

from .models import SEVERITIES, STATUSES, Bug, parse_iso
from .table import bar


@dataclass
class Summary:
    """一次统计的完整结果。"""

    total: int = 0
    by_status: dict[str, int] = field(default_factory=dict)
    by_severity: dict[str, int] = field(default_factory=dict)
    by_module: dict[str, int] = field(default_factory=dict)
    by_assignee: dict[str, int] = field(default_factory=dict)
    open_count: int = 0
    open_s1: int = 0
    unassigned: int = 0
    avg_age_days: float = 0.0
    oldest: list[Bug] = field(default_factory=list)

    @property
    def open_rate(self) -> float:
        return round(self.open_count / self.total * 100, 1) if self.total else 0.0


#: 未关闭的状态集合。
OPEN_STATUSES = {"new", "triaged", "in_progress", "fixed", "reopened"}


def summarize(bugs: list[Bug], top_n: int = 8) -> Summary:
    """汇总分布、未闭环数和滞留时长。"""
    s = Summary(total=len(bugs))
    if not bugs:
        return s

    status_c: Counter[str] = Counter()
    sev_c: Counter[str] = Counter()
    mod_c: Counter[str] = Counter()
    who_c: Counter[str] = Counter()

    ages: list[float] = []
    for bug in bugs:
        status_c[bug.status] += 1
        sev_c[bug.severity] += 1
        mod_c[bug.module] += 1
        who_c[bug.assignee or "未指派"] += 1
        if bug.status in OPEN_STATUSES:
            s.open_count += 1
            if bug.severity == "S1":
                s.open_s1 += 1
            if not bug.assignee:
                s.unassigned += 1
            age = (_now() - parse_iso(bug.created_at)).total_seconds() / 86400
            ages.append(max(age, 0.0))

    s.by_status = {k: status_c[k] for k in STATUSES if status_c[k]}
    for extra in sorted(set(status_c) - set(STATUSES)):
        s.by_status[extra] = status_c[extra]
    s.by_severity = {k: sev_c[k] for k in SEVERITIES if sev_c[k]}
    s.by_module = dict(mod_c.most_common(top_n))
    s.by_assignee = dict(who_c.most_common(top_n))
    s.avg_age_days = round(sum(ages) / len(ages), 1) if ages else 0.0

    open_bugs = [b for b in bugs if b.status in OPEN_STATUSES]
    open_bugs.sort(key=lambda b: parse_iso(b.created_at))
    s.oldest = open_bugs[:5]
    return s


def _now():
    from datetime import datetime

    return datetime.now()


def render_summary(s: Summary) -> str:
    """把 Summary 渲染成终端友好的多段文本。"""
    lines: list[str] = []
    lines.append(f"总计 {s.total} 条缺陷，未闭环 {s.open_count} 条（{s.open_rate}%），"
                 f"其中 S1 未闭环 {s.open_s1} 条。")
    lines.append(f"未指派 {s.unassigned} 条，未闭环平均滞留 {s.avg_age_days} 天。")

    if s.by_severity:
        lines.append("")
        lines.append("按严重级别：")
        top = max(s.by_severity.values())
        for sev in SEVERITIES:
            n = s.by_severity.get(sev, 0)
            if n:
                lines.append(f"  {sev}  {n:>3}  {bar(n, top)}")

    if s.by_status:
        lines.append("")
        lines.append("按状态：")
        top = max(s.by_status.values())
        for st, n in s.by_status.items():
            lines.append(f"  {st:<12} {n:>3}  {bar(n, top)}")

    if s.by_module:
        lines.append("")
        lines.append("按模块（Top）：")
        for mod, n in s.by_module.items():
            lines.append(f"  {mod:<14} {n:>3}")

    if s.oldest:
        lines.append("")
        lines.append("滞留最久的未闭环缺陷：")
        for bug in s.oldest:
            days = (_now() - parse_iso(bug.created_at)).days
            lines.append(f"  #{bug.id:<4} {bug.severity}  {days:>3} 天  {bug.title[:30]}")

    return "\n".join(lines)


def trend(bugs: list[Bug], days: int = 7) -> list[tuple[str, int]]:
    """最近 N 天每天新增数，供折线/柱状展示。"""
    today = _now().date()
    buckets: dict[str, int] = defaultdict(int)
    for offset in range(days - 1, -1, -1):
        key = (today - timedelta(days=offset)).strftime("%m-%d")
        buckets[key] = 0
    for bug in bugs:
        key = parse_iso(bug.created_at).strftime("%m-%d")
        if key in buckets:
            buckets[key] += 1
    return list(buckets.items())
