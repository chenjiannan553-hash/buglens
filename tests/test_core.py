"""查重、门禁、报表、导入四块的测试。"""

from __future__ import annotations

import csv
import io
import json
import tempfile
import unittest
from pathlib import Path

from buglens.dedupe import duplicate_groups, find_similar, similarity
from buglens.gate import evaluate
from buglens.importer import dump_json, parse_csv, parse_json
from buglens.models import Bug
from buglens.report import to_csv, to_html, to_markdown
from buglens.stats import summarize, trend


def bug(i: int, **kw) -> Bug:
    data = dict(
        title=f"登录页在弱网下重复提交导致账号被锁 {i}",
        module="账号",
        severity="S1",
        reporter="张验",
        env="iOS 17.2",
        steps="1. 打开登录页\n2. 连续点击登录 3 次",
        actual="触发风控锁定",
        expected="按钮置灰只提交一次",
    )
    data.update(kw)
    return Bug(id=i, **data)


class TestSimilarity(unittest.TestCase):
    def test_identical_is_high(self):
        a, b = bug(1), bug(2)
        self.assertGreater(similarity(a, b), 0.9)

    def test_different_is_low(self):
        a = bug(1)
        b = bug(2, title="设置页文案错别字", module="设置", steps="1. 进设置\n2. 看标题",
                actual="帐号", expected="账号", severity="S4")
        self.assertLess(similarity(a, b), 0.5)

    def test_same_module_bonus(self):
        a = bug(1, module="账号")
        b = bug(2, module="账号")
        c = bug(3, module="订单")
        self.assertGreater(similarity(a, b), similarity(a, c))

    def test_find_similar_excludes_self(self):
        pool = [bug(1), bug(2)]
        hits = find_similar(pool[0], pool, threshold=0.5)
        self.assertTrue(all(h.id != 1 for h, _ in hits))

    def test_threshold_filters(self):
        pool = [bug(1), bug(2, title="完全不同的另一个问题描述")]
        hits = find_similar(pool[0], pool, threshold=0.99)
        self.assertEqual(hits, [])

    def test_duplicate_groups(self):
        pool = [bug(1), bug(2), bug(3, title="无关缺陷", module="设置", steps="1. a\n2. b",
                                        actual="xx", expected="yy", severity="S4")]
        groups = duplicate_groups(pool, threshold=0.8)
        self.assertTrue(any(len(g) >= 2 for g in groups))

    def test_empty_pool(self):
        self.assertEqual(duplicate_groups([]), [])


class TestGate(unittest.TestCase):
    def test_blocks_on_open_s1(self):
        result = evaluate("2.4.0", [bug(1, status="in_progress")], 5, 5)
        self.assertFalse(result.passed)
        self.assertTrue(any(c.name == "S1 清零" for c in result.blockers))

    def test_passes_when_clean(self):
        bugs = [bug(1, severity="S3", status="closed", assignee="赵码")]
        result = evaluate("2.4.0", bugs, 3, 3)
        self.assertTrue(result.passed)

    def test_s2_threshold(self):
        bugs = [bug(i, severity="S2", status="new", assignee="赵码") for i in range(5)]
        result = evaluate("2.4.0", bugs, 1, 1, max_s2=3)
        self.assertFalse(result.passed)

    def test_unassigned_high_severity_blocks(self):
        result = evaluate("2.4.0", [bug(1, status="new", assignee="")], 1, 1)
        self.assertTrue(any("指派" in c.name for c in result.blockers))

    def test_incomplete_checklist_blocks(self):
        result = evaluate("2.4.0", [], 1, 3)
        self.assertFalse(result.passed)

    def test_missing_checklist_is_warning_only(self):
        result = evaluate("2.4.0", [], 0, 0)
        self.assertTrue(result.passed)
        self.assertEqual(len(result.warnings), 1)

    def test_pending_verification_is_warning(self):
        bugs = [bug(i, severity="S4", status="fixed", assignee="x") for i in range(8)]
        result = evaluate("2.4.0", bugs, 1, 1)
        self.assertTrue(result.passed)
        self.assertTrue(any("待验证" in c.name for c in result.warnings))


class TestReport(unittest.TestCase):
    def test_csv_has_header_and_rows(self):
        """用 csv 解析计数——steps 字段含换行，不能用 splitlines。"""
        text = to_csv([bug(1), bug(2)])
        rows = list(csv.reader(io.StringIO(text)))
        self.assertEqual(len(rows), 3)  # 1 表头 + 2 数据
        self.assertIn("title", rows[0])
        self.assertEqual(rows[1][0], "1")

    def test_markdown_contains_summary(self):
        bugs = [bug(1), bug(2)]
        md = to_markdown(bugs, summarize(bugs))
        self.assertIn("# 缺陷报告", md)
        self.assertIn("S1", md)
        self.assertIn("| #1 |", md)

    def test_markdown_escapes_pipe(self):
        md = to_markdown([bug(1, title="标题里有 | 竖线符号测试")])
        self.assertIn("\\|", md)

    def test_html_is_self_contained(self):
        html = to_html([bug(1)], summarize([bug(1)]))
        self.assertIn("<!DOCTYPE html>", html)
        self.assertNotIn("http://", html.split("<style>")[0])

    def test_html_escapes_script(self):
        html = to_html([bug(1, title="<script>alert(1)</script>")])
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_html_empty_state(self):
        html = to_html([], summarize([]))
        self.assertIn("暂无缺陷数据", html)


class TestStats(unittest.TestCase):
    def test_open_count(self):
        bugs = [bug(1, status="new"), bug(2, status="closed")]
        s = summarize(bugs)
        self.assertEqual(s.total, 2)
        self.assertEqual(s.open_count, 1)

    def test_open_s1(self):
        bugs = [bug(1, severity="S1", status="new")]
        self.assertEqual(summarize(bugs).open_s1, 1)

    def test_unassigned_count(self):
        bugs = [bug(1, status="new", assignee=""), bug(2, status="new", assignee="赵码")]
        self.assertEqual(summarize(bugs).unassigned, 1)

    def test_empty_summary(self):
        s = summarize([])
        self.assertEqual(s.total, 0)
        self.assertEqual(s.open_rate, 0.0)

    def test_trend_length(self):
        self.assertEqual(len(trend([bug(1)], days=7)), 7)


class TestImport(unittest.TestCase):
    def test_csv_roundtrip(self):
        text = to_csv([bug(1)])
        bugs, rep = parse_csv(text)
        self.assertEqual(rep.imported, 1)
        self.assertEqual(rep.skipped, 0)
        self.assertEqual(bugs[0].title, bug(1).title)

    def test_csv_bad_row_skipped(self):
        text = to_csv([bug(1)]) + "坏行,数据,不足\n"
        bugs, rep = parse_csv(text)
        self.assertEqual(rep.imported, 1)
        self.assertEqual(rep.skipped, 1)
        self.assertTrue(rep.errors)

    def test_json_roundtrip(self):
        payload = dump_json([bug(1), bug(2)])
        bugs, rep = parse_json(payload)
        self.assertEqual(rep.imported, 2)

    def test_json_bare_array(self):
        arr = json.dumps([bug(1).to_dict()])
        bugs, rep = parse_json(arr)
        self.assertEqual(rep.imported, 1)

    def test_json_non_array_raises(self):
        with self.assertRaises(ValueError):
            parse_json('"just a string"')

    def test_json_skips_invalid_items(self):
        arr = json.dumps([bug(1).to_dict(), {"title": "太短"}])
        bugs, rep = parse_json(arr)
        self.assertEqual(rep.imported, 1)
        self.assertEqual(rep.skipped, 1)

    def test_bom_stripped(self):
        text = "\ufeff" + to_csv([bug(1)])
        _, rep = parse_csv(text)
        self.assertEqual(rep.imported, 1)


if __name__ == "__main__":
    unittest.main()
