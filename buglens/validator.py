"""缺陷信息结构化校验。

立场：信息不结构化 = 没提 Bug。
缺复现环境、步骤、实际结果、期望结果，直接退回，不给"先记下来再说"的口子。
"""

from __future__ import annotations

from .models import FIELD_LABELS, REQUIRED_FIELDS, SEVERITIES

#: 每个字段的最小有效长度。太短视为敷衍填写。
MIN_LENGTH = {
    "title": 6,
    "steps": 10,
    "actual": 4,
    "expected": 4,
    "env": 3,
    "module": 1,
    "reporter": 1,
}

#: 少于这么多步，认为复现路径描述不完整。
MIN_STEPS_LINES = 2


class ValidationError(ValueError):
    """校验失败，errors 里是逐字段的中文说明。"""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("；".join(errors))


def _blank(value: str | None) -> bool:
    return value is None or str(value).strip() == ""


def _step_lines(steps: str) -> list[str]:
    """把步骤按行或分号拆开，过滤空行。"""
    raw = str(steps).replace("；", "\n").replace(";", "\n").splitlines()
    return [line.strip() for line in raw if line.strip()]


def validate_bug_dict(data: dict) -> list[str]:
    """返回错误列表，空列表表示通过。

    一次报全所有问题，不做"改一个再告诉你下一个"的挤牙膏式校验。
    """
    errors: list[str] = []
    missing: set[str] = set()

    for field in REQUIRED_FIELDS:
        if _blank(data.get(field)):
            errors.append(f"缺少必填字段：{FIELD_LABELS.get(field, field)}（{field}）")
            missing.add(field)

    # 缺失的字段跳过长度校验，但已填字段继续检查，保证一轮报全。
    for field, minimum in MIN_LENGTH.items():
        if field in missing:
            continue
        value = str(data.get(field, "") or "").strip()
        if value and len(value) < minimum:
            errors.append(
                f"{FIELD_LABELS.get(field, field)}过短（{len(value)} 字符，至少 {minimum}）："
                f"'{value}'"
            )

    severity = str(data.get("severity", "")).strip().upper()
    if severity and severity not in SEVERITIES:
        errors.append(f"严重级别 '{severity}' 非法，可选：{', '.join(SEVERITIES)}")

    lines = _step_lines(data.get("steps", ""))
    if lines and len(lines) < MIN_STEPS_LINES:
        errors.append(
            f"复现步骤只有 {len(lines)} 步，至少需要 {MIN_STEPS_LINES} 步（一行一步或用分号分隔）"
        )

    actual = str(data.get("actual", "")).strip()
    expected = str(data.get("expected", "")).strip()
    if actual and expected and actual == expected:
        errors.append("实际结果与期望结果完全相同，无法判定为缺陷")

    return errors


def normalize(data: dict) -> dict:
    """清洗输入：去空格、级别大写、标签归一。"""
    out = dict(data)
    for key in ("title", "module", "reporter", "env", "assignee"):
        if key in out and out[key] is not None:
            out[key] = str(out[key]).strip()
    if out.get("severity"):
        out["severity"] = str(out["severity"]).strip().upper()
    if out.get("status"):
        out["status"] = str(out["status"]).strip().lower()
    if out.get("tags"):
        tags = {t.strip() for t in str(out["tags"]).replace("，", ",").split(",") if t.strip()}
        out["tags"] = ",".join(sorted(tags))
    return out


def validate_or_raise(data: dict) -> dict:
    """校验并清洗，失败抛 ValidationError。"""
    errors = validate_bug_dict(data)
    if errors:
        raise ValidationError(errors)
    return normalize(data)
