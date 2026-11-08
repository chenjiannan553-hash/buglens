"""重复缺陷检测。

用 difflib 做标题 + 步骤的加权相似度，纯标准库。
目的是在新缺陷入库前提醒"这条可能已经提过了"，而不是自动合并。
"""

from __future__ import annotations

from difflib import SequenceMatcher

from .models import Bug

#: 加权：标题更能代表缺陷本质，步骤其次，实际结果做辅助。
WEIGHT_TITLE = 0.55
WEIGHT_STEPS = 0.30
WEIGHT_ACTUAL = 0.15

#: 高于此分数视为疑似重复，需要人工确认。
DEFAULT_THRESHOLD = 0.72


def _norm(text: str) -> str:
    """去掉空白与常见标点，降低格式差异带来的噪声。"""
    drop = " \t\r\n，。、；：！？,.;:!?-_/\\()（）[]【】\"'`"
    out = []
    for ch in str(text).lower():
        if ch not in drop:
            out.append(ch)
    return "".join(out)


def _ratio(a: str, b: str) -> float:
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def similarity(a: Bug, b: Bug) -> float:
    """两条缺陷的综合相似度，0~1。"""
    score = (
        _ratio(a.title, b.title) * WEIGHT_TITLE
        + _ratio(a.steps, b.steps) * WEIGHT_STEPS
        + _ratio(a.actual, b.actual) * WEIGHT_ACTUAL
    )
    # 同模块同级别是弱信号，加一点点，避免跨模块误判主导排序。
    if a.module == b.module:
        score += 0.05
    if a.severity == b.severity:
        score += 0.03
    return round(min(score, 1.0), 4)


def find_similar(
    target: Bug,
    pool: list[Bug],
    threshold: float = DEFAULT_THRESHOLD,
    limit: int = 5,
) -> list[tuple[Bug, float]]:
    """在候选池里找疑似重复项，按分数降序。"""
    scored: list[tuple[Bug, float]] = []
    for bug in pool:
        if bug.id is not None and bug.id == target.id:
            continue
        score = similarity(target, bug)
        if score >= threshold:
            scored.append((bug, score))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:limit]


def duplicate_groups(
    pool: list[Bug], threshold: float = DEFAULT_THRESHOLD
) -> list[list[tuple[Bug, float]]]:
    """全量两两比对，返回疑似重复的簇，供 `dedupe --all` 使用。"""
    seen: set[int] = set()
    groups: list[list[tuple[Bug, float]]] = []
    for i, a in enumerate(pool):
        if a.id in seen:
            continue
        hits = find_similar(a, pool[i + 1 :], threshold=threshold, limit=20)
        if not hits:
            continue
        group = [(a, 1.0)]
        for bug, score in hits:
            if bug.id not in seen:
                group.append((bug, score))
                seen.add(bug.id)
        if len(group) > 1:
            seen.add(a.id)
            groups.append(group)
    return groups
