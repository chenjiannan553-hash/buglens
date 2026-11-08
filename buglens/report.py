"""导出：Markdown / CSV / HTML 看板。

三个格式覆盖三种场景：
- Markdown：贴进周报、PR、Issue
- CSV：给别人在 Excel 里继续加工
- HTML：单文件看板，`buglens serve` 也复用它
"""

from __future__ import annotations

import csv
import html
import io
from pathlib import Path

from .models import SEVERITIES, STATUS_LABELS, Bug
from .stats import Summary


EXPORT_FIELDS = [
    "id", "title", "module", "severity", "status", "reporter", "assignee",
    "env", "steps", "actual", "expected", "tags", "created_at", "updated_at",
]


def to_csv(bugs: list[Bug]) -> str:
    """导出 CSV 字符串（含表头，UTF-8 BOM 由写文件方处理）。"""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=EXPORT_FIELDS, lineterminator="\n")
    writer.writeheader()
    for bug in bugs:
        row = bug.to_dict()
        writer.writerow({k: row.get(k, "") for k in EXPORT_FIELDS})
    return buf.getvalue()


def to_markdown(bugs: list[Bug], summary: Summary | None = None, title: str = "缺陷报告") -> str:
    """生成 Markdown 报告：概览 + 明细 + 建议动作。"""
    lines = [f"# {title}", ""]
    if summary:
        lines += [
            f"- 总计：**{summary.total}** 条",
            f"- 未闭环：**{summary.open_count}** 条（{summary.open_rate}%）",
            f"- S1 未闭环：**{summary.open_s1}** 条",
            f"- 未指派：**{summary.unassigned}** 条",
            f"- 平均滞留：**{summary.avg_age_days}** 天",
            "",
            "## 分布",
            "",
            "| 维度 | 值 | 数量 |",
            "| --- | --- | --- |",
        ]
        for sev in SEVERITIES:
            if summary.by_severity.get(sev):
                lines.append(f"| 严重级别 | {sev} | {summary.by_severity[sev]} |")
        for st, n in summary.by_status.items():
            lines.append(f"| 状态 | {STATUS_LABELS.get(st, st)} | {n} |")
        for mod, n in summary.by_module.items():
            lines.append(f"| 模块 | {mod} | {n} |")
        lines.append("")

    lines += [
        "## 明细",
        "",
        "| ID | 级别 | 状态 | 模块 | 标题 | 处理人 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for bug in bugs:
        lines.append(
            f"| #{bug.id} | {bug.severity} | {STATUS_LABELS.get(bug.status, bug.status)} "
            f"| {bug.module} | {_md(bug.title)} | {bug.assignee or '—'} |"
        )

    s1_open = [b for b in bugs if b.severity == "S1" and b.status not in ("closed", "verified")]
    if s1_open:
        lines += ["", "## 需要立刻处理的 S1", ""]
        for bug in s1_open:
            lines += [
                f"### #{bug.id} {bug.title}",
                "",
                f"- 模块：{bug.module}",
                f"- 环境：{bug.env}",
                f"- 复现步骤：{_md(bug.steps)}",
                f"- 实际：{_md(bug.actual)}",
                f"- 期望：{_md(bug.expected)}",
                "",
            ]
    return "\n".join(lines)


def _md(text: str) -> str:
    return str(text).replace("\n", "<br>").replace("|", "\\|")


CSS = """
:root{--bg:#fff;--fg:#1a1a1a;--muted:#666;--line:#e5e5e5;--s1:#c0392b;--s2:#d97706;
--s3:#2563eb;--s4:#6b7280;--card:#fafafa}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:14px/1.6 -apple-system,"PingFang SC","Helvetica Neue",sans-serif}
.wrap{max-width:1080px;margin:0 auto;padding:32px 20px 64px}
h1{font-size:22px;margin:0 0 4px}
.sub{color:var(--muted);font-size:13px;margin-bottom:24px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:28px}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:14px 16px}
.card .k{color:var(--muted);font-size:12px}
.card .v{font-size:24px;font-weight:600;margin-top:4px}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{text-align:left;padding:9px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:500;font-size:12px;
text-transform:uppercase;letter-spacing:.04em;border-bottom:1px solid #ccc}
tr:hover td{background:#fcfcfc}
.sev{display:inline-block;padding:1px 7px;border-radius:10px;font-size:11px;
font-weight:600;color:#fff}
.sev-S1{background:var(--s1)}.sev-S2{background:var(--s2)}
.sev-S3{background:var(--s3)}.sev-S4{background:var(--s4)}
.st{font-size:12px;color:var(--muted)}
.tag{display:inline-block;background:#f0f0f0;border-radius:4px;padding:0 6px;
font-size:11px;color:#555;margin-right:4px}
.empty{color:var(--muted);padding:40px 0;text-align:center}
"""


def to_html(bugs: list[Bug], summary: Summary | None = None, title: str = "缺陷看板") -> str:
    """单文件 HTML 看板，不依赖任何外部资源（离线可看）。"""
    rows = []
    for bug in bugs:
        tags = "".join(f'<span class="tag">{html.escape(t)}</span>' for t in bug.tag_list)
        rows.append(
            "<tr>"
            f"<td>#{bug.id}</td>"
            f'<td><span class="sev sev-{html.escape(bug.severity)}">{html.escape(bug.severity)}</span></td>'
            f"<td>{html.escape(bug.title)}</td>"
            f"<td>{html.escape(bug.module)}</td>"
            f'<td class="st">{html.escape(STATUS_LABELS.get(bug.status, bug.status))}</td>'
            f"<td>{html.escape(bug.assignee or '—')}</td>"
            f"<td>{tags}</td>"
            "</tr>"
        )
    body_rows = "\n".join(rows) or '<tr><td colspan="7" class="empty">暂无缺陷数据</td></tr>'

    cards = ""
    if summary:
        cards = f"""
<div class="cards">
  <div class="card"><div class="k">总缺陷</div><div class="v">{summary.total}</div></div>
  <div class="card"><div class="k">未闭环</div><div class="v">{summary.open_count}</div></div>
  <div class="card"><div class="k">S1 未闭环</div><div class="v">{summary.open_s1}</div></div>
  <div class="card"><div class="k">未指派</div><div class="v">{summary.unassigned}</div></div>
  <div class="card"><div class="k">平均滞留（天）</div><div class="v">{summary.avg_age_days}</div></div>
</div>"""

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
  <h1>{html.escape(title)}</h1>
  <div class="sub">由 buglens 生成 · 共 {len(bugs)} 条记录</div>
  {cards}
  <table>
    <thead>
      <tr><th>ID</th><th>级别</th><th>标题</th><th>模块</th><th>状态</th><th>处理人</th><th>标签</th></tr>
    </thead>
    <tbody>
{body_rows}
    </tbody>
  </table>
</div>
</body>
</html>
"""


def write(path: str | Path, content: str, bom: bool = False) -> Path:
    """写文件，CSV 默认加 BOM 以便 Excel 正确识别中文。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = ("\ufeff" + content) if bom else content
    p.write_text(data, encoding="utf-8")
    return p
