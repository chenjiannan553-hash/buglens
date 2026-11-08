"""命令行入口。

子命令一览（`buglens --help` 可见）：
  init / add / list / show / set / assign / search / stats
  dedupe / gate / check / export / import / serve / demo / rm / config
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .db import Store, default_db_path
from .dedupe import DEFAULT_THRESHOLD, duplicate_groups, find_similar
from .demo import demo_bugs, demo_checks
from .gate import evaluate, render as render_gate
from .importer import dump_json, load
from .models import (
    SEVERITIES,
    STATUSES,
    STATUS_LABELS,
    Bug,
    utc_stamp,
)
from .report import to_csv, to_html, to_markdown, write
from .state_machine import TransitionError, assert_transition
from .stats import render_summary, summarize, trend
from .table import bar, render_table, truncate
from .validator import ValidationError, validate_or_raise


# ---------------------------------------------------------------- 输出辅助


def _configure_stdio() -> None:
    """统一标准输出编码。

    Windows 控制台默认代码页是 cp936/cp1252，直接打印中文会抛
    UnicodeEncodeError。这里显式指定 UTF-8 并放宽错误策略：
    宁可显示成问号，也不能让工具崩在最后一步。
    """
    for stream in (sys.stdout, sys.stderr):
        if stream is None:
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            # 被重定向到 StringIO 时没有 reconfigure，忽略即可
            try:
                stream.reconfigure(errors="replace")
            except Exception:
                pass


def out(text: str = "") -> None:
    print(text)


def ok(text: str) -> None:
    print(f"[OK] {text}")


def warn(text: str) -> None:
    print(f"[!] {text}")


def err(text: str) -> None:
    print(f"[X] {text}", file=sys.stderr)


def bug_table(bugs: list[Bug], limit: int = 40) -> str:
    headers = ["ID", "级别", "状态", "模块", "标题", "处理人"]
    rows = []
    for bug in bugs[:limit]:
        rows.append([
            f"#{bug.id}",
            bug.severity,
            STATUS_LABELS.get(bug.status, bug.status),
            truncate(bug.module, 10),
            truncate(bug.title, 38),
            truncate(bug.assignee or "—", 8),
        ])
    table = render_table(headers, rows)
    if len(bugs) > limit:
        table += f"\n（共 {len(bugs)} 条，仅显示前 {limit} 条，用 --limit 调整）"
    return table


# ---------------------------------------------------------------- 子命令实现


def cmd_init(args) -> int:
    store = Store(args.db)
    total = len(store.list_bugs())
    ok(f"数据库已就绪：{store.path}")
    out(f"当前缺陷数：{total}")
    store.close()
    return 0


def cmd_add(args) -> int:
    data = {
        "title": args.title,
        "module": args.module,
        "severity": args.severity,
        "reporter": args.reporter,
        "env": args.env,
        "steps": args.steps,
        "actual": args.actual,
        "expected": args.expected,
        "assignee": args.assignee or "",
        "tags": args.tags or "",
        "status": "new",
    }

    if args.interactive:
        out("交互式录入，直接回车表示留空（必填项留空会校验失败）")
        prompts = [
            ("title", "标题"),
            ("module", "模块"),
            ("severity", "严重级别 S1-S4"),
            ("reporter", "报告人"),
            ("env", "复现环境"),
            ("steps", "复现步骤（一行一步）"),
            ("actual", "实际结果"),
            ("expected", "期望结果"),
            ("assignee", "处理人（可空）"),
            ("tags", "标签，逗号分隔（可空）"),
        ]
        for key, label in prompts:
            current = data.get(key) or ""
            hint = f" [{current}]" if current else ""
            raw = input(f"{label}{hint}: ").strip()
            if raw:
                data[key] = raw
            elif not current:
                data[key] = ""

    try:
        cleaned = validate_or_raise(data)
    except ValidationError as exc:
        err("录入被退回，以下问题必须补齐：")
        for item in exc.errors:
            out(f"  - {item}")
        return 2

    bug = Bug(
        title=cleaned["title"], module=cleaned["module"],
        severity=cleaned["severity"], reporter=cleaned["reporter"],
        env=cleaned["env"], steps=cleaned["steps"],
        actual=cleaned["actual"], expected=cleaned["expected"],
        assignee=cleaned.get("assignee", ""), tags=cleaned.get("tags", ""),
        status="new",
    )

    store = Store(args.db)
    if not args.no_dedupe:
        hits = find_similar(bug, store.list_bugs(), threshold=args.threshold)
        if hits:
            warn("检测到疑似重复缺陷，入库前请确认：")
            for other, score in hits:
                out(f"  #{other.id} {other.severity} {other.title}（相似度 {score:.0%}）")
            if not args.force:
                err("已中止入库。确认不是重复请加 --force 重新执行。")
                store.close()
                return 3

    bug_id = store.add_bug(bug, actor=bug.reporter)
    ok(f"已创建缺陷 #{bug_id}：{bug.title}")
    if bug.assignee:
        store.assign(bug_id, bug.assignee)
        out(f"已指派给 {bug.assignee}")
    store.close()
    return 0


def cmd_list(args) -> int:
    store = Store(args.db)
    bugs = store.list_bugs(
        status=args.status, severity=args.severity, module=args.module,
        assignee=args.assignee, tag=args.tag, keyword=args.keyword,
        limit=args.limit,
    )
    if not bugs:
        out("没有匹配的缺陷。")
        store.close()
        return 0
    out(bug_table(bugs, limit=args.limit or 40))
    store.close()
    return 0


def cmd_show(args) -> int:
    store = Store(args.db)
    bug = store.get_bug(args.id)
    if not bug:
        err(f"缺陷 #{args.id} 不存在")
        store.close()
        return 1

    out(f"#{bug.id}  {bug.title}")
    out("=" * 60)
    pairs = [
        ("严重级别", f"{bug.severity} — {SEVERITY_HINT.get(bug.severity, '')}"),
        ("状态", f"{STATUS_LABELS.get(bug.status, bug.status)}（{bug.status}）"),
        ("模块", bug.module),
        ("报告人", bug.reporter or "—"),
        ("处理人", bug.assignee or "未指派"),
        ("标签", ", ".join(bug.tag_list) or "—"),
        ("创建时间", bug.created_at),
        ("更新时间", bug.updated_at),
    ]
    for key, value in pairs:
        out(f"  {key:<8}{value}")
    out("")
    for label, field in (("复现环境", bug.env), ("复现步骤", bug.steps),
                         ("实际结果", bug.actual), ("期望结果", bug.expected)):
        out(f"[{label}]")
        for line in str(field).splitlines():
            out(f"  {line}")
        out("")

    history = store.history(bug.id)
    if history:
        out("[状态流转]")
        rows = [
            [
                h.at.replace("T", " "),
                STATUS_LABELS.get(h.from_status or "-", h.from_status or "-"),
                STATUS_LABELS.get(h.to_status, h.to_status),
                h.actor,
                truncate(h.note or "", 24),
            ]
            for h in history
        ]
        out(render_table(["时间", "从", "到", "操作人", "备注"], rows))
    store.close()
    return 0


SEVERITY_HINT = {
    "S1": "核心链路不可用 / 数据丢失 / 安全漏洞",
    "S2": "主流程受损且无绕过方案",
    "S3": "有绕过方案，影响体验",
    "S4": "文案 / 样式 / 边缘问题",
}


def cmd_set(args) -> int:
    store = Store(args.db)
    bug = store.get_bug(args.id)
    if not bug:
        err(f"缺陷 #{args.id} 不存在")
        store.close()
        return 1
    try:
        assert_transition(bug.status, args.status)
    except TransitionError as exc:
        err(str(exc))
        store.close()
        return 2
    if bug.status == args.status:
        out(f"#{args.id} 已经是 {STATUS_LABELS.get(args.status, args.status)}，无需变更。")
        store.close()
        return 0
    store.update_status(args.id, args.status, actor=args.actor, note=args.note or "")
    ok(f"#{args.id} {STATUS_LABELS.get(bug.status, bug.status)} → "
       f"{STATUS_LABELS.get(args.status, args.status)}")
    store.close()
    return 0


def cmd_assign(args) -> int:
    store = Store(args.db)
    if not store.get_bug(args.id):
        err(f"缺陷 #{args.id} 不存在")
        store.close()
        return 1
    store.assign(args.id, args.assignee)
    ok(f"#{args.id} 已指派给 {args.assignee}")
    store.close()
    return 0


def cmd_search(args) -> int:
    store = Store(args.db)
    bugs = store.list_bugs(keyword=args.keyword, limit=args.limit)
    if not bugs:
        out(f"没有包含「{args.keyword}」的缺陷。")
        store.close()
        return 0
    out(bug_table(bugs, limit=args.limit or 40))
    store.close()
    return 0


def cmd_stats(args) -> int:
    store = Store(args.db)
    bugs = store.list_bugs()
    summary = summarize(bugs)
    out(render_summary(summary))
    if args.trend:
        out("")
        out(f"最近 {args.trend} 天新增趋势：")
        points = trend(bugs, days=args.trend)
        top = max((n for _, n in points), default=0)
        for label, n in points:
            out(f"  {label}  {n:>3}  {bar(n, top or 1, width=20)}")
    store.close()
    return 0


def cmd_dedupe(args) -> int:
    store = Store(args.db)
    bugs = store.list_bugs()
    if len(bugs) < 2:
        out("缺陷少于 2 条，无需查重。")
        store.close()
        return 0
    groups = duplicate_groups(bugs, threshold=args.threshold)
    if not groups:
        ok(f"在阈值 {args.threshold:.0%} 下未发现疑似重复。")
        store.close()
        return 0
    warn(f"发现 {len(groups)} 组疑似重复：")
    for idx, group in enumerate(groups, 1):
        out(f"\n第 {idx} 组")
        rows = [[f"#{b.id}", b.severity, truncate(b.title, 40),
                 f"{score:.0%}" if b.id != group[0][0].id else "基准"] for b, score in group]
        out(render_table(["ID", "级别", "标题", "相似度"], rows))
    store.close()
    return 0


def cmd_gate(args) -> int:
    store = Store(args.db)
    bugs = store.list_bugs()
    done, total = store.check_progress(args.release)
    result = evaluate(args.release, bugs, done, total, max_s2=args.max_s2)
    out(render_gate(result))
    store.close()
    if args.report:
        path = Path(args.report)
        path.write_text(render_gate(result), encoding="utf-8")
        out(f"\n门禁报告已写入 {path}")
    return 0 if result.passed else 1


def cmd_check(args) -> int:
    store = Store(args.db)
    if args.action == "add":
        cid = store.add_check(args.release, args.item, owner=args.owner or "")
        ok(f"已加入验收清单 #{cid}（{args.release}）：{args.item}")
    elif args.action == "list":
        items = store.list_checks(args.release)
        if not items:
            out(f"{args.release} 还没有验收清单条目。")
            store.close()
            return 0
        rows = [
            ["x" if it.done else " ", f"#{it.id}", truncate(it.item, 40), it.owner or "—"]
            for it in items
        ]
        out(render_table(["完成", "ID", "条目", "负责人"], rows))
        done, total = store.check_progress(args.release)
        out(f"\n进度：{done}/{total}")
    elif args.action == "done":
        if store.check_item(args.id, done=True):
            ok(f"清单 #{args.id} 标记为完成")
        else:
            err(f"清单 #{args.id} 不存在")
            store.close()
            return 1
    elif args.action == "undo":
        if store.check_item(args.id, done=False):
            ok(f"清单 #{args.id} 取消完成")
        else:
            err(f"清单 #{args.id} 不存在")
            store.close()
            return 1
    store.close()
    return 0


def cmd_export(args) -> int:
    store = Store(args.db)
    bugs = store.list_bugs(status=args.status, severity=args.severity)
    if not bugs:
        out("没有可导出的缺陷。")
        store.close()
        return 0
    stamp = utc_stamp()
    fmt = args.format
    default_name = f"buglens-{stamp}.{fmt}"
    path = Path(args.out) if args.out else Path.cwd() / default_name

    if fmt == "csv":
        write(path, to_csv(bugs), bom=True)
    elif fmt == "md":
        write(path, to_markdown(bugs, summarize(bugs), title=args.title))
    elif fmt == "html":
        write(path, to_html(bugs, summarize(bugs), title=args.title))
    elif fmt == "json":
        write(path, dump_json(bugs))
    else:
        err(f"未知格式 {fmt}")
        store.close()
        return 2
    ok(f"已导出 {len(bugs)} 条到 {path}")
    store.close()
    return 0


def cmd_import(args) -> int:
    try:
        bugs, rep = load(args.file)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        err(str(exc))
        return 1

    out(f"解析完成：共 {rep.total} 行，通过 {rep.imported}，退回 {rep.skipped}")
    if rep.errors:
        warn("以下行被退回（不影响其他行入库）：")
        for lineno, msg in rep.errors[:20]:
            out(f"  第 {lineno} 行：{msg}")
        if len(rep.errors) > 20:
            out(f"  …… 另有 {len(rep.errors) - 20} 条")

    if args.dry_run:
        out("\n[dry-run] 未写入数据库。去掉 --dry-run 执行正式导入。")
        return 0 if rep.imported else 2

    if not bugs:
        err("没有任何合法数据，导入中止。")
        return 2

    store = Store(args.db)
    n = store.bulk_insert(bugs)
    ok(f"已导入 {n} 条缺陷")
    store.close()
    return 0


def cmd_serve(args) -> int:
    from .web import serve

    store = Store(args.db)
    count = len(store.list_bugs())
    httpd, url = serve(store, port=args.port, title=args.title,
                       open_browser=not args.no_browser)
    out(f"看板已启动：{url}")
    out(f"数据：{store.path}（{count} 条）")
    out("按 Ctrl+C 停止。")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        out("\n已停止。")
    finally:
        httpd.server_close()
        store.close()
    return 0


def cmd_demo(args) -> int:
    store = Store(args.db)
    if store.list_bugs() and not args.force:
        err("数据库里已有数据。确认要覆盖请加 --force（会清空现有缺陷与清单）。")
        store.close()
        return 1
    store.reset()
    n = store.bulk_insert(demo_bugs(), actor="demo")
    for item in demo_checks():
        cid = store.add_check(item.release, item.item)
        if args.mark_first_done and cid == 1:
            store.check_item(cid, True)
    ok(f"已生成示例数据：{n} 条缺陷、{len(demo_checks())} 条验收清单")
    out(f"数据库：{store.path}")
    out("下一步可以试：buglens stats / buglens gate --release 2.4.0 / buglens serve")
    store.close()
    return 0


def cmd_rm(args) -> int:
    store = Store(args.db)
    bug = store.get_bug(args.id)
    if not bug:
        err(f"缺陷 #{args.id} 不存在")
        store.close()
        return 1
    if not args.yes:
        err(f"即将删除 #{bug.id} {bug.title}。确认请加 --yes。")
        store.close()
        return 1
    store.delete_bug(args.id)
    ok(f"已删除 #{args.id}")
    store.close()
    return 0


def cmd_config(args) -> int:
    store = Store(args.db)
    info = {
        "数据库": str(store.path),
        "缺陷数": len(store.list_bugs()),
        "验收版本": store.releases(),
        "版本": __version__,
        "默认库路径": str(default_db_path()),
    }
    for key, value in info.items():
        out(f"{key:<10}{value}")
    store.close()
    return 0


# ---------------------------------------------------------------- 参数解析


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="buglens",
        description="缺陷跟踪与发布验收 CLI —— 结构化录入、状态机、查重、门禁、看板。",
        epilog="示例：buglens demo && buglens stats && buglens gate --release 2.4.0",
    )
    p.add_argument("--version", action="version", version=f"buglens {__version__}")
    p.add_argument("--db", help="指定数据库文件（默认 ./buglens.db）")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("init", help="初始化数据库")
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("add", help="录入一条缺陷（强校验）")
    sp.add_argument("--title")
    sp.add_argument("--module")
    sp.add_argument("--severity", default="S3", choices=list(SEVERITIES))
    sp.add_argument("--reporter")
    sp.add_argument("--env")
    sp.add_argument("--steps", help="复现步骤，一行一步，用 \\n 或分号分隔")
    sp.add_argument("--actual")
    sp.add_argument("--expected")
    sp.add_argument("--assignee")
    sp.add_argument("--tags")
    sp.add_argument("-i", "--interactive", action="store_true", help="交互式逐项录入")
    sp.add_argument("--force", action="store_true", help="忽略疑似重复提醒")
    sp.add_argument("--no-dedupe", action="store_true", help="跳过查重")
    sp.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    sp.set_defaults(func=cmd_add)

    sp = sub.add_parser("list", help="按条件列出缺陷")
    sp.add_argument("--status", choices=list(STATUSES))
    sp.add_argument("--severity", choices=list(SEVERITIES))
    sp.add_argument("--module")
    sp.add_argument("--assignee")
    sp.add_argument("--tag")
    sp.add_argument("--keyword")
    sp.add_argument("--limit", type=int)
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("show", help="查看缺陷详情与流转历史")
    sp.add_argument("id", type=int)
    sp.set_defaults(func=cmd_show)

    sp = sub.add_parser("set", help="变更缺陷状态（状态机校验）")
    sp.add_argument("id", type=int)
    sp.add_argument("status", choices=list(STATUSES))
    sp.add_argument("--actor", default="cli")
    sp.add_argument("--note", default="")
    sp.set_defaults(func=cmd_set)

    sp = sub.add_parser("assign", help="指派处理人")
    sp.add_argument("id", type=int)
    sp.add_argument("assignee")
    sp.set_defaults(func=cmd_assign)

    sp = sub.add_parser("search", help="全文搜索")
    sp.add_argument("keyword")
    sp.add_argument("--limit", type=int)
    sp.set_defaults(func=cmd_search)

    sp = sub.add_parser("stats", help="统计概览")
    sp.add_argument("--trend", type=int, default=0, help="附带最近 N 天新增趋势")
    sp.set_defaults(func=cmd_stats)

    sp = sub.add_parser("dedupe", help="重复缺陷检测")
    sp.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    sp.set_defaults(func=cmd_dedupe)

    sp = sub.add_parser("gate", help="发布门禁评估（不通过退出码 1）")
    sp.add_argument("--release", required=True, help="版本号，如 2.4.0")
    sp.add_argument("--max-s2", type=int, default=3, help="允许的未闭环 S2 上限")
    sp.add_argument("--report", help="把门禁结论写成文件")
    sp.set_defaults(func=cmd_gate)

    sp = sub.add_parser("check", help="验收清单管理")
    sp.add_argument("action", choices=["add", "list", "done", "undo"])
    sp.add_argument("--release", default="default")
    sp.add_argument("--item")
    sp.add_argument("--owner")
    sp.add_argument("--id", type=int)
    sp.set_defaults(func=cmd_check)

    sp = sub.add_parser("export", help="导出报告")
    sp.add_argument("--format", choices=["md", "csv", "html", "json"], default="md")
    sp.add_argument("--out")
    sp.add_argument("--status")
    sp.add_argument("--severity")
    sp.add_argument("--title", default="缺陷报告")
    sp.set_defaults(func=cmd_export)

    sp = sub.add_parser("import", help="从 CSV/JSON 导入")
    sp.add_argument("file")
    sp.add_argument("--dry-run", action="store_true", help="只校验不写库")
    sp.set_defaults(func=cmd_import)

    sp = sub.add_parser("serve", help="启动本地只读看板")
    sp.add_argument("--port", type=int, default=8770)
    sp.add_argument("--title", default="缺陷看板")
    sp.add_argument("--no-browser", action="store_true")
    sp.set_defaults(func=cmd_serve)

    sp = sub.add_parser("demo", help="生成示例数据")
    sp.add_argument("--force", action="store_true")
    sp.add_argument("--mark-first-done", action="store_true",
                    help="顺手勾掉第一条验收项，便于演示未完成门禁")
    sp.set_defaults(func=cmd_demo)

    sp = sub.add_parser("rm", help="删除缺陷")
    sp.add_argument("id", type=int)
    sp.add_argument("--yes", action="store_true")
    sp.set_defaults(func=cmd_rm)

    sp = sub.add_parser("config", help="查看当前配置与统计口径")
    sp.set_defaults(func=cmd_config)

    return p


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except BrokenPipeError:
        return 0
    except KeyboardInterrupt:
        out("\n已中断。")
        return 130
    except ValidationError as exc:
        err("校验失败：")
        for item in exc.errors:
            out(f"  - {item}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
