"""发布门禁。

规则明确、可解释、可复现：
1. S1 未清零 → 阻断（不接受"先上线再修"的口头豁免）
2. 未指派的高级别缺陷 → 阻断
3. 验收清单未完成 → 阻断
4. S2 超出阈值 → 阻断（阈值可配置）
全部通过才返回 0，否则返回 1，便于直接挂到 CI / pre-push。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import Bug
from .stats import OPEN_STATUSES


@dataclass
class GateCheck:
    """单条门禁规则的结论。"""

    name: str
    passed: bool
    detail: str
    blocking: bool = True


@dataclass
class GateResult:
    """一次门禁评估的完整结果。"""

    release: str
    checks: list[GateCheck] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks if c.blocking)

    @property
    def blockers(self) -> list[GateCheck]:
        return [c for c in self.checks if c.blocking and not c.passed]

    @property
    def warnings(self) -> list[GateCheck]:
        return [c for c in self.checks if not c.blocking and not c.passed]


def evaluate(
    release: str,
    bugs: list[Bug],
    checks_done: int,
    checks_total: int,
    max_s2: int = 3,
    max_unassigned: int = 0,
) -> GateResult:
    """按既定规则评估，返回逐条结论。"""
    result = GateResult(release=release)
    open_bugs = [b for b in bugs if b.status in OPEN_STATUSES]

    # 规则 1：S1 必须清零
    s1 = [b for b in open_bugs if b.severity == "S1"]
    result.checks.append(
        GateCheck(
            name="S1 清零",
            passed=not s1,
            detail="无未闭环 S1" if not s1 else
            "未闭环 S1：" + "、".join(f"#{b.id}" for b in s1),
        )
    )

    # 规则 2：S2 数量上限
    s2 = [b for b in open_bugs if b.severity == "S2"]
    result.checks.append(
        GateCheck(
            name=f"S2 不超过 {max_s2} 条",
            passed=len(s2) <= max_s2,
            detail=f"当前未闭环 S2 {len(s2)} 条",
        )
    )

    # 规则 3：高级别必须有责任人
    unassigned = [b for b in open_bugs if not b.assignee and b.severity in ("S1", "S2")]
    result.checks.append(
        GateCheck(
            name="高级别已指派",
            passed=len(unassigned) <= max_unassigned,
            detail="全部有责任人" if not unassigned else
            f"{len(unassigned)} 条 S1/S2 未指派：" + "、".join(f"#{b.id}" for b in unassigned),
        )
    )

    # 规则 4：验收清单完成
    if checks_total > 0:
        result.checks.append(
            GateCheck(
                name="验收清单完成",
                passed=checks_done == checks_total,
                detail=f"已完成 {checks_done}/{checks_total}",
            )
        )
    else:
        result.checks.append(
            GateCheck(
                name="验收清单存在",
                passed=False,
                detail="该版本没有任何验收清单条目，无法证明验收动作发生过",
                blocking=False,
            )
        )

    # 规则 5：待验证堆积（仅提醒，不阻断）
    pending = [b for b in open_bugs if b.status == "fixed"]
    result.checks.append(
        GateCheck(
            name="待验证不堆积",
            passed=len(pending) <= 5,
            detail=f"{len(pending)} 条待验证",
            blocking=False,
        )
    )

    return result


def render(result: GateResult) -> str:
    """门禁结论的文本报告。"""
    lines = [f"发布门禁评估：{result.release}", ""]
    for check in result.checks:
        mark = "PASS" if check.passed else ("FAIL" if check.blocking else "WARN")
        lines.append(f"  [{mark}] {check.name} — {check.detail}")
    lines.append("")
    if result.passed:
        lines.append("结论：可以发布。以上阻断项全部通过。")
    else:
        lines.append(f"结论：阻断发布。{len(result.blockers)} 项未通过："
                     + "、".join(c.name for c in result.blockers))
    return "\n".join(lines)
