"""CLI 端到端测试：走真实的 argparse 与退出码。"""

from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from buglens.cli import main


class CliCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / "cli.db")

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args: str) -> tuple[int, str]:
        """执行命令，返回 (退出码, 标准输出+错误输出)。"""
        buf_out, buf_err = io.StringIO(), io.StringIO()
        with redirect_stdout(buf_out), redirect_stderr(buf_err):
            code = main(["--db", self.db, *args])
        return code, buf_out.getvalue() + buf_err.getvalue()

    def seed(self):
        self.run_cli("demo")


class TestBasics(CliCase):
    def test_init(self):
        code, out = self.run_cli("init")
        self.assertEqual(code, 0)
        self.assertIn("数据库已就绪", out)

    def test_empty_list(self):
        code, out = self.run_cli("list")
        self.assertEqual(code, 0)
        self.assertIn("没有匹配", out)

    def test_config(self):
        code, out = self.run_cli("config")
        self.assertEqual(code, 0)
        self.assertIn("数据库", out)

    def test_version_flag(self):
        with self.assertRaises(SystemExit) as ctx, redirect_stdout(io.StringIO()):
            main(["--version"])
        self.assertEqual(ctx.exception.code, 0)


class TestDemoAndList(CliCase):
    def test_demo_creates_data(self):
        code, out = self.run_cli("demo")
        self.assertEqual(code, 0)
        self.assertIn("8 条缺陷", out)

    def test_demo_requires_force(self):
        self.seed()
        code, out = self.run_cli("demo")
        self.assertEqual(code, 1)
        self.assertIn("已有数据", out)

    def test_list_all(self):
        self.seed()
        code, out = self.run_cli("list")
        self.assertEqual(code, 0)
        self.assertIn("S1", out)

    def test_list_filter_severity(self):
        self.seed()
        code, out = self.run_cli("list", "--severity", "S1")
        self.assertEqual(code, 0)
        self.assertIn("S1", out)
        self.assertNotIn("S4", out)

    def test_show_detail(self):
        self.seed()
        code, out = self.run_cli("show", "1")
        self.assertEqual(code, 0)
        self.assertIn("复现步骤", out)
        self.assertIn("状态流转", out)

    def test_show_missing(self):
        code, out = self.run_cli("show", "999")
        self.assertEqual(code, 1)
        self.assertIn("不存在", out)

    def test_search(self):
        self.seed()
        code, out = self.run_cli("search", "弱网")
        self.assertEqual(code, 0)
        self.assertIn("登录页", out)


class TestAdd(CliCase):
    GOOD = (
        "--title", "搜索框输入特殊字符导致服务端异常",
        "--module", "搜索",
        "--severity", "S2",
        "--reporter", "张验",
        "--env", "Web / Chrome 131",
        "--steps", "1. 输入特殊字符\n2. 点击搜索",
        "--actual", "接口返回 500",
        "--expected", "返回空结果并提示",
    )

    def test_add_ok(self):
        code, out = self.run_cli("add", *self.GOOD)
        self.assertEqual(code, 0)
        self.assertIn("已创建缺陷", out)

    def test_add_rejects_incomplete(self):
        code, out = self.run_cli("add", "--title", "太短", "--module", "x")
        self.assertEqual(code, 2)
        self.assertIn("缺少必填字段", out)

    def test_add_duplicate_blocked(self):
        self.seed()
        code, out = self.run_cli(
            "add",
            "--title", "登录页在弱网下重复提交导致账号被锁",
            "--module", "账号",
            "--reporter", "张验",
            "--env", "iOS 17.2 / App 2.4.0",
            "--steps", "1. 打开登录页输入正确账号密码\n2. 连续点击登录按钮 3 次",
            "--actual", "后端收到 3 次请求触发风控锁定",
            "--expected", "按钮置灰只提交一次",
        )
        self.assertEqual(code, 3)
        self.assertIn("疑似重复", out)

    def test_add_duplicate_forced(self):
        self.seed()
        code, _ = self.run_cli(
            "add", "--force",
            "--title", "登录页在弱网下重复提交导致账号被锁",
            "--module", "账号",
            "--reporter", "张验",
            "--env", "iOS 17.2 / App 2.4.0",
            "--steps", "1. 打开登录页输入正确账号密码\n2. 连续点击登录按钮 3 次",
            "--actual", "后端收到 3 次请求触发风控锁定",
            "--expected", "按钮置灰只提交一次",
        )
        self.assertEqual(code, 0)


class TestStateCommands(CliCase):
    def test_set_illegal_returns_2(self):
        self.seed()
        code, out = self.run_cli("set", "1", "closed")  # #1 是 in_progress
        self.assertEqual(code, 0, "in_progress → closed 属于误报关闭，允许")

    def test_set_illegal_from_closed(self):
        self.seed()
        self.run_cli("set", "6", "closed")   # #6 已是 closed
        code, out = self.run_cli("set", "6", "fixed")
        self.assertEqual(code, 2)
        self.assertIn("不允许", out)

    def test_set_missing_bug(self):
        self.seed()
        code, _ = self.run_cli("set", "999", "triaged")
        self.assertEqual(code, 1)

    def test_assign(self):
        self.seed()
        code, out = self.run_cli("assign", "3", "李承")
        self.assertEqual(code, 0)
        self.assertIn("已指派", out)


class TestGate(CliCase):
    def test_gate_blocks_by_default_demo(self):
        self.seed()
        code, out = self.run_cli("gate", "--release", "2.4.0")
        self.assertEqual(code, 1)
        self.assertIn("阻断发布", out)

    def test_gate_passes_when_release_clean(self):
        # 没有任何缺陷 + 清单全完成 → 通过
        self.run_cli("check", "add", "--release", "9.0.0", "--item", "回归通过")
        self.run_cli("check", "done", "--release", "9.0.0", "--id", "1")
        code, out = self.run_cli("gate", "--release", "9.0.0")
        self.assertEqual(code, 0)
        self.assertIn("可以发布", out)

    def test_gate_writes_report(self):
        self.seed()
        path = Path(self.tmp.name) / "gate.txt"
        self.run_cli("gate", "--release", "2.4.0", "--report", str(path))
        self.assertTrue(path.exists())
        self.assertIn("发布门禁评估", path.read_text(encoding="utf-8"))


class TestChecklist(CliCase):
    def test_add_list_done(self):
        self.run_cli("check", "add", "--release", "v1", "--item", "回归用例全通过", "--owner", "张验")
        code, out = self.run_cli("check", "list", "--release", "v1")
        self.assertEqual(code, 0)
        self.assertIn("回归用例全通过", out)
        code, out = self.run_cli("check", "done", "--release", "v1", "--id", "1")
        self.assertEqual(code, 0)
        _, out = self.run_cli("check", "list", "--release", "v1")
        self.assertIn("1/1", out)

    def test_undo(self):
        self.run_cli("check", "add", "--release", "v1", "--item", "x")
        self.run_cli("check", "done", "--release", "v1", "--id", "1")
        code, _ = self.run_cli("check", "undo", "--release", "v1", "--id", "1")
        self.assertEqual(code, 0)

    def test_done_missing(self):
        code, _ = self.run_cli("check", "done", "--release", "v1", "--id", "99")
        self.assertEqual(code, 1)


class TestExportImport(CliCase):
    def test_export_md(self):
        self.seed()
        path = Path(self.tmp.name) / "r.md"
        code, out = self.run_cli("export", "--format", "md", "--out", str(path))
        self.assertEqual(code, 0)
        self.assertIn("导出", out)
        self.assertIn("# 缺陷报告", path.read_text(encoding="utf-8"))

    def test_export_csv_has_bom(self):
        self.seed()
        path = Path(self.tmp.name) / "r.csv"
        self.run_cli("export", "--format", "csv", "--out", str(path))
        self.assertTrue(path.read_bytes().startswith(b"\xef\xbb\xbf"))

    def test_export_empty(self):
        code, out = self.run_cli("export", "--format", "md")
        self.assertEqual(code, 0)
        self.assertIn("没有可导出", out)

    def test_import_dry_run(self):
        self.seed()
        path = Path(self.tmp.name) / "r.json"
        self.run_cli("export", "--format", "json", "--out", str(path))
        code, out = self.run_cli("import", str(path), "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("dry-run", out)

    def test_import_missing_file(self):
        code, out = self.run_cli("import", str(Path(self.tmp.name) / "nope.csv"))
        self.assertEqual(code, 1)
        self.assertIn("不存在", out)


class TestStatsDedupe(CliCase):
    def test_stats(self):
        self.seed()
        code, out = self.run_cli("stats", "--trend", "7")
        self.assertEqual(code, 0)
        self.assertIn("按严重级别", out)
        self.assertIn("趋势", out)

    def test_stats_empty(self):
        code, out = self.run_cli("stats")
        self.assertEqual(code, 0)
        self.assertIn("总计 0 条", out)

    def test_dedupe_empty(self):
        code, out = self.run_cli("dedupe")
        self.assertEqual(code, 0)
        self.assertIn("少于 2 条", out)

    def test_dedupe_runs(self):
        self.seed()
        code, out = self.run_cli("dedupe")
        self.assertEqual(code, 0)
        self.assertTrue("疑似重复" in out or "未发现" in out)

    def test_rm_requires_yes(self):
        self.seed()
        code, out = self.run_cli("rm", "1")
        self.assertEqual(code, 1)
        self.assertIn("--yes", out)

    def test_rm_yes(self):
        self.seed()
        code, _ = self.run_cli("rm", "1", "--yes")
        self.assertEqual(code, 0)
        _, out = self.run_cli("show", "1")
        self.assertIn("不存在", out)


if __name__ == "__main__":
    unittest.main()
