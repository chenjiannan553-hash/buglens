"""SQLite 持久化层测试。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from buglens.db import Store
from buglens.models import Bug


def make_bug(**kw) -> Bug:
    data = dict(
        title="登录页弱网重复提交导致锁号",
        module="账号",
        severity="S1",
        reporter="张验",
        env="iOS 17.2",
        steps="1. 输入账号\n2. 连续点击登录",
        actual="锁号",
        expected="只提交一次",
    )
    data.update(kw)
    return Bug(**data)


class StoreCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "t.db")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()


class TestCrud(StoreCase):
    def test_add_and_get(self):
        bug_id = self.store.add_bug(make_bug())
        bug = self.store.get_bug(bug_id)
        self.assertIsNotNone(bug)
        self.assertEqual(bug.title, "登录页弱网重复提交导致锁号")
        self.assertEqual(bug.status, "new")

    def test_add_writes_initial_history(self):
        bug_id = self.store.add_bug(make_bug())
        history = self.store.history(bug_id)
        self.assertEqual(len(history), 1)
        self.assertIsNone(history[0].from_status)
        self.assertEqual(history[0].to_status, "new")

    def test_get_missing_returns_none(self):
        self.assertIsNone(self.store.get_bug(9999))

    def test_delete(self):
        bug_id = self.store.add_bug(make_bug())
        self.assertTrue(self.store.delete_bug(bug_id))
        self.assertIsNone(self.store.get_bug(bug_id))

    def test_delete_missing_returns_false(self):
        self.assertFalse(self.store.delete_bug(4242))

    def test_persists_across_reopen(self):
        bug_id = self.store.add_bug(make_bug())
        self.store.close()
        again = Store(Path(self.tmp.name) / "t.db")
        self.assertIsNotNone(again.get_bug(bug_id))
        again.close()
        self.store = Store(Path(self.tmp.name) / "t.db")


class TestQuery(StoreCase):
    def setUp(self):
        super().setUp()
        self.s1 = self.store.add_bug(make_bug(severity="S1", module="账号", tags="登录,风控"))
        self.s3 = self.store.add_bug(
            make_bug(title="设置页错别字", severity="S3", module="设置", tags="文案")
        )
        self.store.add_bug(make_bug(title="订单金额格式错误", severity="S2", module="订单"))

    def test_filter_by_severity(self):
        self.assertEqual(len(self.store.list_bugs(severity="S1")), 1)

    def test_filter_by_module(self):
        self.assertEqual(len(self.store.list_bugs(module="账号")), 1)

    def test_filter_by_tag(self):
        self.assertEqual(len(self.store.list_bugs(tag="文案")), 1)

    def test_tag_no_partial_match(self):
        """tag 精确匹配，避免 '文' 命中 '文案'。"""
        self.assertEqual(len(self.store.list_bugs(tag="文")), 0)

    def test_keyword_searches_steps(self):
        hits = self.store.list_bugs(keyword="连续点击")
        self.assertEqual(len(hits), 3)

    def test_ordering_s1_first(self):
        bugs = self.store.list_bugs()
        self.assertEqual(bugs[0].severity, "S1")

    def test_limit(self):
        self.assertEqual(len(self.store.list_bugs(limit=2)), 2)

    def test_assign(self):
        self.store.assign(self.s3, "赵码")
        self.assertEqual(self.store.get_bug(self.s3).assignee, "赵码")

    def test_filter_by_assignee(self):
        self.store.assign(self.s3, "赵码")
        self.assertEqual(len(self.store.list_bugs(assignee="赵码")), 1)

    def test_tag_underscore_is_literal(self):
        """issue #1：a_b 不能因为 _ 是通配符而误命中 axb。"""
        self.store.add_bug(make_bug(title="下划线标签的缺陷", tags="a_b"))
        self.store.add_bug(make_bug(title="近似标签的缺陷", tags="axb"))
        hits = self.store.list_bugs(tag="a_b")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].tags, "a_b")

    def test_tag_percent_is_literal(self):
        """tag 里的 % 应按字面匹配，不能变成全匹配。"""
        self.store.add_bug(make_bug(title="百分号标签的缺陷", tags="100%"))
        self.assertEqual(len(self.store.list_bugs(tag="%")), 0)
        self.assertEqual(len(self.store.list_bugs(tag="100%")), 1)

    def test_keyword_wildcards_are_literal(self):
        """全文搜索里的 _ 和 % 同样必须按字面处理。"""
        self.store.add_bug(make_bug(title="包含 a_b 字样的缺陷"))
        self.store.add_bug(make_bug(title="包含 axb 字样的缺陷"))
        self.assertEqual(len(self.store.list_bugs(keyword="a_b")), 1)
        self.assertEqual(len(self.store.list_bugs(keyword="%")), 0)


class TestStatusHistory(StoreCase):
    def test_update_status_records_history(self):
        bug_id = self.store.add_bug(make_bug())
        self.store.update_status(bug_id, "triaged", actor="分诊员", note="信息完整")
        history = self.store.history(bug_id)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[1].from_status, "new")
        self.assertEqual(history[1].to_status, "triaged")
        self.assertEqual(history[1].actor, "分诊员")

    def test_update_missing_bug_raises(self):
        with self.assertRaises(KeyError):
            self.store.update_status(9999, "closed", actor="x")


class TestChecklist(StoreCase):
    def test_add_and_list(self):
        self.store.add_check("2.4.0", "回归全通过", owner="张验")
        items = self.store.list_checks("2.4.0")
        self.assertEqual(len(items), 1)
        self.assertFalse(items[0].done)

    def test_mark_done_and_progress(self):
        cid = self.store.add_check("2.4.0", "回归全通过")
        self.store.add_check("2.4.0", "灰度观察")
        self.assertTrue(self.store.check_item(cid))
        self.assertEqual(self.store.check_progress("2.4.0"), (1, 2))

    def test_releases_listed(self):
        self.store.add_check("2.4.0", "a")
        self.store.add_check("2.5.0", "b")
        self.assertIn("2.4.0", self.store.releases())
        self.assertIn("2.5.0", self.store.releases())

    def test_progress_empty_release(self):
        self.assertEqual(self.store.check_progress("none"), (0, 0))


class TestMaintenance(StoreCase):
    def test_counts(self):
        self.store.add_bug(make_bug())
        self.assertEqual(self.store.counts().get("new"), 1)

    def test_bulk_insert(self):
        n = self.store.bulk_insert([make_bug(), make_bug(title="第二条缺陷标题")])
        self.assertEqual(n, 2)
        self.assertEqual(len(self.store.list_bugs()), 2)

    def test_reset_clears_all(self):
        self.store.add_bug(make_bug())
        self.store.add_check("2.4.0", "x")
        self.store.reset()
        self.assertEqual(len(self.store.list_bugs()), 0)
        self.assertEqual(len(self.store.list_checks("2.4.0")), 0)

    def test_modules(self):
        self.store.add_bug(make_bug(module="账号"))
        self.store.add_bug(make_bug(module="订单", title="另一个缺陷标题"))
        self.assertEqual(sorted(self.store.modules()), ["订单", "账号"])


if __name__ == "__main__":
    unittest.main()
