"""30 条增量能力的单元测试：覆盖真实写库路径、拦截逻辑与 CLI 集成。"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from buglens import cli
from buglens.db import Store
from buglens.extras import (
    aging_buckets,
    audit_log,
    bulk_assign,
    bulk_remove,
    bulk_set_status,
    bulk_tag,
    daily_trend,
    duplicate_report,
    find_orphans,
    group_counts,
    merge_tags,
    parse_ids,
    save_template,
    select_bugs,
    sla_breaches,
    tag_cloud,
    use_template,
    validate_all,
)
from buglens.models import Bug
from buglens.state_machine import allowed_targets
from tests.test_db import make_bug


class ExtrasCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "t.db")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def seed(self, n: int = 3, **kw) -> list[Bug]:
        ids = [self.store.add_bug(make_bug(title=f"缺陷-{i}", **kw)) for i in range(n)]
        return [self.store.get_bug(i) for i in ids]

    def age(self, bug_id: int, days: int) -> None:
        """add_bug 会强制写当前时间，测滞留只能直接改库。"""
        old = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")
        self.store.conn.execute(
            "UPDATE bugs SET created_at = ?, updated_at = ? WHERE id = ?",
            (old, old, bug_id),
        )
        self.store.conn.commit()

    def capture(self, *argv: str) -> tuple[int, str]:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            rc = cli.main(["--db", str(self.store.path), *argv])
        return rc, buf.getvalue()


class TestParseAndSelect(ExtrasCase):
    def test_parse_ids_plain_range_and_dedupe(self):
        self.assertEqual(parse_ids("1,2,5-7,6"), [1, 2, 5, 6, 7])
        self.assertEqual(parse_ids("7-5"), [5, 6, 7])
        self.assertEqual(parse_ids(""), [])

    def test_parse_ids_rejects_garbage(self):
        with self.assertRaises(ValueError):
            parse_ids("1,abc")

    def test_select_requires_scope(self):
        with self.assertRaises(ValueError):
            select_bugs(self.store, [])

    def test_select_intersects_ids_and_filters(self):
        self.seed(2)
        self.store.add_bug(make_bug(title="另一条", severity="S4"))
        picked = select_bugs(self.store, [1, 2, 3], severity="S4")
        self.assertEqual([b.id for b in picked], [3])


class TestMergeTags(ExtrasCase):
    def test_merge_add_remove_dedupe(self):
        self.assertEqual(merge_tags("a,b", "c"), "a,b,c")
        self.assertEqual(merge_tags("a,b", "a"), "a,b")
        self.assertEqual(merge_tags("a,b,c", "b", remove=True), "a,c")


class TestBulkWrites(ExtrasCase):
    def test_bulk_set_status_writes_and_blocks_illegal(self):
        bugs = self.seed(2)
        target = allowed_targets("new")[0]
        lines = bulk_set_status(self.store, bugs, target, "tester", "", False)
        self.assertEqual(len([x for x in lines if x.startswith("已流转")]), 2)
        self.assertEqual(self.store.get_bug(bugs[0].id).status, target)
        # 再从目标状态尝试一个不合法的目标，应被跳过
        illegal = next((s for s in ("new", "closed") if s not in allowed_targets(target)), None)
        if illegal:
            lines2 = bulk_set_status(self.store, [self.store.get_bug(bugs[0].id)], illegal,
                                     "tester", "", False)
            self.assertTrue(lines2[0].startswith("跳过"))

    def test_bulk_assign_writes(self):
        bugs = self.seed(2)
        bulk_assign(self.store, bugs, "李四", False)
        self.assertEqual(self.store.get_bug(bugs[1].id).assignee, "李四")

    def test_bulk_tag_adds_and_removes(self):
        bugs = self.seed(1)
        bulk_tag(self.store, bugs, "回归", False, False)
        self.assertIn("回归", self.store.get_bug(bugs[0].id).tags)
        refreshed = [self.store.get_bug(bugs[0].id)]
        bulk_tag(self.store, refreshed, "回归", True, False)
        self.assertNotIn("回归", self.store.get_bug(bugs[0].id).tags)

    def test_bulk_remove_respects_dry_run(self):
        bugs = self.seed(2)
        bulk_remove(self.store, bugs, dry_run=True)
        self.assertEqual(len(self.store.list_bugs()), 2)
        bulk_remove(self.store, bugs, dry_run=False)
        self.assertEqual(len(self.store.list_bugs()), 0)


class TestListFilters(ExtrasCase):
    def test_date_bounds(self):
        old_id = self.store.add_bug(make_bug(title="老缺陷"))
        self.age(old_id, 10)
        self.store.add_bug(make_bug(title="新缺陷"))
        today = datetime.now().strftime("%Y-%m-%d")
        self.assertEqual(len(self.store.list_bugs(created_before=today,
                                                  created_after="2020-01-01",
                                                  keyword="老缺陷")), 1)
        self.assertEqual(len(self.store.list_bugs(updated_after=today)), 1)

    def test_open_closed_only(self):
        self.seed(2)
        self.store.update_status(1, "closed", "tester")
        self.assertEqual(len(self.store.list_bugs(open_only=True)), 1)
        self.assertEqual(len(self.store.list_bugs(closed_only=True)), 1)

    def test_sort_created_and_id(self):
        self.seed(2)
        by_id = self.store.list_bugs(sort="id")
        self.assertGreater(by_id[0].id, by_id[1].id)
        self.assertEqual([b.id for b in self.store.list_bugs(sort="created")],
                         [b.id for b in by_id])


class TestReports(ExtrasCase):
    def test_group_counts(self):
        self.seed(2, module="账号")
        self.store.add_bug(make_bug(title="另一模块", module="支付"))
        counts = dict(group_counts(self.store.list_bugs(), "module"))
        self.assertEqual(counts["账号"], 2)
        self.assertEqual(counts["支付"], 1)

    def test_aging_buckets_counts_open_only(self):
        now = datetime.now()
        self.age(self.store.add_bug(make_bug(title="老缺陷")), 10)
        buckets = dict(aging_buckets(self.store.list_bugs(), now))
        self.assertEqual(buckets["7-30天"], 1)
        self.assertEqual(sum(buckets.values()), 1)

    def test_daily_trend_length(self):
        self.seed(1)
        trend = daily_trend(self.store.list_bugs(), days=7)
        self.assertEqual(len(trend), 7)
        self.assertEqual(sum(row[1] for row in trend), 1)

    def test_sla_breaches(self):
        self.age(self.store.add_bug(make_bug(title="超时缺陷")), 5)
        hits = sla_breaches(self.store.list_bugs(), limit_hours=24)
        self.assertEqual(len(hits), 1)
        self.assertGreater(hits[0][1], 24)

    def test_tag_cloud(self):
        self.store.add_bug(make_bug(title="带标签", tags="a,b"))
        self.store.add_bug(make_bug(title="也带标签", tags="a"))
        self.assertEqual(dict(tag_cloud(self.store.list_bugs())), {"a": 2, "b": 1})


class TestAudit(ExtrasCase):
    def test_validate_all_is_clean_on_valid_data(self):
        self.seed(2)
        self.assertEqual(validate_all(self.store), [])

    def test_validate_all_detects_bad_status(self):
        self.seed(1)
        self.store.conn.execute("UPDATE bugs SET status = '???' WHERE id = 1")
        self.store.conn.commit()
        problems = validate_all(self.store)
        self.assertTrue(any("状态非法" in p for p in problems))

    def test_find_orphans(self):
        self.seed(1)
        self.store.conn.execute("DELETE FROM history WHERE bug_id = 1")
        self.store.conn.commit()
        self.assertEqual(find_orphans(self.store), [1])

    def test_audit_log_contains_notes(self):
        self.seed(1)
        self.assertTrue(self.store.add_note(1, "tester", "补充说明"))
        self.assertEqual(len(audit_log(self.store)), 2)
        self.assertEqual(self.store.history(1)[-1].note, "补充说明")

    def test_duplicate_report_format(self):
        self.seed(2)
        lines = duplicate_report(self.store.list_bugs(), threshold=0.1)
        self.assertTrue(all(line.startswith("疑似重复：#") for line in lines))


class TestTemplates(ExtrasCase):
    def test_save_use_with_override(self):
        self.seed(1)
        save_template(self.store, "tpl", self.store.get_bug(1))
        self.assertEqual(len(self.store.list_templates()), 1)
        bug = use_template(self.store, "tpl", title="覆盖后的标题", severity="S4")
        self.assertEqual(bug.title, "覆盖后的标题")
        self.assertEqual(bug.severity, "S4")
        self.assertIsNone(bug.id)

    def test_use_missing_template(self):
        with self.assertRaises(KeyError):
            use_template(self.store, "不存在")


class TestCliIntegration(ExtrasCase):
    def test_check_import_progress_template(self):
        csv_path = Path(self.tmp.name) / "checks.csv"
        csv_path.write_text("item,owner\n回归主链路,测试组\n核对发布说明,产品组\n", encoding="utf-8")
        rc, text = self.capture("check", "import", "--file", str(csv_path), "--release", "R1")
        self.assertEqual(rc, 0)
        self.assertIn("已导入 2 条", text)
        rc, text = self.capture("check", "progress", "--release", "R1")
        self.assertIn("0/2", text)
        rc, text = self.capture("check", "template", "--release", "R2")
        self.assertEqual(rc, 0)
        self.assertEqual(len(self.store.list_checks("R2")), 5)

    def test_export_jsonl_is_parseable(self):
        self.seed(2)
        out_path = Path(self.tmp.name) / "out.jsonl"
        rc, _ = self.capture("export", "--format", "jsonl", "--out", str(out_path))
        self.assertEqual(rc, 0)
        rows = [json.loads(line) for line in out_path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(rows), 2)
        self.assertIn("title", rows[0])

    def test_note_and_bulk_cli_write(self):
        self.seed(2)
        rc, _ = self.capture("note", "1", "--text", "CLI 备注")
        self.assertEqual(rc, 0)
        self.assertEqual(self.store.history(1)[-1].note, "CLI 备注")
        target = allowed_targets("new")[0]
        rc, text = self.capture("bulk", "set-status", "--ids", "1,2", "--to", target)
        self.assertEqual(rc, 0)
        self.assertIn("已流转", text)
        self.assertEqual(self.store.get_bug(2).status, target)

    def test_bulk_rm_requires_confirmation(self):
        self.seed(1)
        rc, text = self.capture("bulk", "rm", "--ids", "1")
        self.assertEqual(rc, 1)
        self.assertIn("--yes", text)
        self.assertEqual(len(self.store.list_bugs()), 1)

    def test_report_json_flag(self):
        self.seed(1)
        rc, text = self.capture("report", "module", "--json")
        self.assertEqual(rc, 0)
        self.assertIn('"kind": "module"', text)


if __name__ == "__main__":
    unittest.main()
