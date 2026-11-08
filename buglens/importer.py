"""导入：CSV / JSON 双向。

导入前一律先校验，坏数据不进库；返回逐行结果，方便定位是哪一行有问题。
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .models import Bug
from .validator import ValidationError, validate_or_raise


@dataclass
class ImportReport:
    """导入结果：成功多少、失败多少、为什么失败。"""

    total: int = 0
    imported: int = 0
    skipped: int = 0
    errors: list[tuple[int, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.skipped == 0


def _from_dict(data: dict[str, Any]) -> Bug:
    cleaned = validate_or_raise(data)
    return Bug(
        title=cleaned["title"],
        module=cleaned["module"],
        severity=cleaned.get("severity", "S3"),
        status=cleaned.get("status", "new") or "new",
        reporter=cleaned["reporter"],
        env=cleaned["env"],
        steps=cleaned["steps"],
        actual=cleaned["actual"],
        expected=cleaned["expected"],
        assignee=cleaned.get("assignee", "") or "",
        tags=cleaned.get("tags", "") or "",
    )


def parse_csv(text: str) -> tuple[list[Bug], ImportReport]:
    """解析 CSV 文本，逐行校验。"""
    report = ImportReport()
    bugs: list[Bug] = []
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    for i, row in enumerate(reader, start=2):  # 第 1 行是表头
        report.total += 1
        payload = {k: (v or "").strip() for k, v in row.items() if k}
        if not payload.get("title"):
            report.skipped += 1
            report.errors.append((i, "整行为空或缺少 title"))
            continue
        try:
            bugs.append(_from_dict(payload))
            report.imported += 1
        except ValidationError as exc:
            report.skipped += 1
            report.errors.append((i, str(exc)))
    return bugs, report


def parse_json(text: str) -> tuple[list[Bug], ImportReport]:
    """解析 JSON 数组（或 {"bugs": [...]} 包装）。"""
    report = ImportReport()
    data = json.loads(text)
    if isinstance(data, dict):
        data = data.get("bugs", [])
    if not isinstance(data, list):
        raise ValueError("JSON 顶层必须是数组，或包含 bugs 数组的对象")

    bugs: list[Bug] = []
    for i, item in enumerate(data, start=1):
        report.total += 1
        if not isinstance(item, dict):
            report.skipped += 1
            report.errors.append((i, "元素不是对象"))
            continue
        try:
            bugs.append(_from_dict(item))
            report.imported += 1
        except (ValidationError, KeyError) as exc:
            report.skipped += 1
            report.errors.append((i, str(exc)))
    return bugs, report


def load(path: str | Path) -> tuple[list[Bug], ImportReport]:
    """按扩展名选择解析器。"""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"文件不存在：{p}")
    text = p.read_text(encoding="utf-8-sig")
    if p.suffix.lower() == ".json":
        return parse_json(text)
    if p.suffix.lower() in (".csv", ".tsv"):
        return parse_csv(text)
    raise ValueError(f"不支持的格式：{p.suffix}，仅支持 .csv / .tsv / .json")


def dump_json(bugs: list[Bug]) -> str:
    """导出 JSON，保留中文不转义。"""
    return json.dumps(
        {"bugs": [b.to_dict() for b in bugs]},
        ensure_ascii=False,
        indent=2,
    )
