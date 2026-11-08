"""终端表格渲染。

中文字符占两列宽，直接用 ljust 会错位，这里按显示宽度补齐。
"""

from __future__ import annotations

import unicodedata
from typing import Iterable, Sequence

#: 超过此宽度的单元格会被截断，避免表格横向爆炸。
MAX_CELL_WIDTH = 34


def display_width(text: str) -> int:
    """按终端显示宽度计算字符串长度（宽字符算 2）。"""
    width = 0
    for ch in str(text):
        width += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return width


def truncate(text: str, width: int = MAX_CELL_WIDTH) -> str:
    """按显示宽度截断并补省略号。"""
    text = str(text).replace("\n", " ")
    if display_width(text) <= width:
        return text
    out, w = [], 0
    for ch in text:
        cw = 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
        if w + cw > width - 1:
            break
        out.append(ch)
        w += cw
    return "".join(out) + "…"


def pad(text: str, width: int, align: str = "left") -> str:
    text = str(text)
    gap = max(width - display_width(text), 0)
    if align == "right":
        return " " * gap + text
    return text + " " * gap


def render_table(
    headers: Sequence[str],
    rows: Iterable[Sequence[str]],
    aligns: Sequence[str] | None = None,
) -> str:
    """渲染等宽表格，带分隔线。"""
    rows = [[str(c) for c in row] for row in rows]
    cols = len(headers)
    aligns = list(aligns or ["left"] * cols)

    widths = [display_width(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row[:cols]):
            widths[i] = max(widths[i], display_width(cell))

    def line(char: str = "-") -> str:
        return "+".join(char * (w + 2) for w in widths)

    def fmt(cells: Sequence[str]) -> str:
        parts = [
            " " + pad(cells[i] if i < len(cells) else "", widths[i], aligns[i]) + " "
            for i in range(cols)
        ]
        return "|" + "|".join(parts) + "|"

    out = [line("-"), fmt(list(headers)), line("=")]
    for row in rows:
        out.append(fmt(row))
    out.append(line("-"))
    return "\n".join(out)


def bar(value: int, total: int, width: int = 24, char: str = "#") -> str:
    """横向条形图，用于统计展示。"""
    if total <= 0:
        return ""
    filled = round(value / total * width)
    return char * max(filled, 0) + "·" * max(width - filled, 0)
