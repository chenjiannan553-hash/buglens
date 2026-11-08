"""结构化校验的边界测试。"""

from __future__ import annotations

import unittest

from buglens.validator import ValidationError, normalize, validate_bug_dict, validate_or_raise

GOOD = {
    "title": "登录页弱网重复提交导致锁号",
    "module": "账号",
    "severity": "S1",
    "reporter": "张验",
    "env": "iOS 17.2 / App 2.4.0",
    "steps": "1. 输入账号密码\n2. 连续点击登录",
    "actual": "触发风控锁定账号",
    "expected": "按钮置灰只提交一次",
}


class TestRequiredFields(unittest.TestCase):
    def test_good_payload_passes(self):
        self.assertEqual(validate_bug_dict(GOOD), [])

    def test_missing_env_is_rejected(self):
        bad = dict(GOOD, env="")
        errors = validate_bug_dict(bad)
        self.assertTrue(any("复现环境" in e for e in errors))

    def test_all_missing_reported_at_once(self):
        """一轮报全，不做挤牙膏式校验。"""
        errors = validate_bug_dict({})
        self.assertEqual(len(errors), 8)

    def test_whitespace_only_counts_as_missing(self):
        errors = validate_bug_dict(dict(GOOD, env="   "))
        self.assertTrue(any("复现环境" in e for e in errors))


class TestLengthRules(unittest.TestCase):
    def test_short_title_rejected(self):
        errors = validate_bug_dict(dict(GOOD, title="挂了"))
        self.assertTrue(any("标题过短" in e for e in errors))

    def test_short_steps_rejected(self):
        errors = validate_bug_dict(dict(GOOD, steps="点一下"))
        self.assertTrue(any("复现步骤过短" in e for e in errors))

    def test_single_step_rejected(self):
        errors = validate_bug_dict(dict(GOOD, steps="打开页面然后连续点击登录按钮三次触发问题"))
        self.assertTrue(any("只有 1 步" in e for e in errors))

    def test_semicolon_separated_steps_ok(self):
        steps = "打开登录页；输入账号密码；连续点击登录三次"
        self.assertEqual(validate_bug_dict(dict(GOOD, steps=steps)), [])


class TestSemanticRules(unittest.TestCase):
    def test_invalid_severity_rejected(self):
        errors = validate_bug_dict(dict(GOOD, severity="S9"))
        self.assertTrue(any("严重级别" in e for e in errors))

    def test_same_actual_and_expected_rejected(self):
        same = "页面白屏"
        errors = validate_bug_dict(dict(GOOD, actual=same, expected=same))
        self.assertTrue(any("实际结果与期望结果完全相同" in e for e in errors))


class TestNormalize(unittest.TestCase):
    def test_lowercase_severity_uppercased(self):
        self.assertEqual(normalize({"severity": "s2"})["severity"], "S2")

    def test_tags_deduped_and_sorted(self):
        self.assertEqual(normalize({"tags": "登录, 风控,登录"})["tags"], "登录,风控")

    def test_fullwidth_comma_supported(self):
        self.assertEqual(normalize({"tags": "a，b"})["tags"], "a,b")

    def test_strips_whitespace(self):
        self.assertEqual(normalize({"title": "  标题  "})["title"], "标题")


class TestValidateOrRaise(unittest.TestCase):
    def test_raises_with_errors_attribute(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_or_raise({})
        self.assertEqual(len(ctx.exception.errors), 8)

    def test_returns_normalized(self):
        out = validate_or_raise(dict(GOOD, severity="s1"))
        self.assertEqual(out["severity"], "S1")


if __name__ == "__main__":
    unittest.main()
