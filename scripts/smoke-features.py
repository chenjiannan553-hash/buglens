"""30 条增量能力的端到端冒烟验收。

用法：python scripts/smoke-features.py
在临时目录建库、灌 demo 数据，逐条执行 CLI 命令并核对退出码。
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable


def run(db: Path, *argv: str) -> tuple[int, str]:
    cmd = [PY, "-m", "buglens", "--db", str(db), *argv]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=60)
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        db = tmpdir / "smoke.db"
        rc, text = run(db, "demo")
        if rc != 0:
            print("demo 初始化失败：", text)
            return 1

        csv_file = tmpdir / "checks.csv"
        csv_file.write_text("item,owner\n回归主链路,测试组\n核对发布说明,产品组\n", encoding="utf-8")
        out_file = tmpdir / "out.jsonl"

        cases: list[tuple[str, tuple[str, ...]]] = [
            ("01 bulk set-status", ("bulk", "set-status", "--ids", "1,2", "--to", "triaged", "--dry-run")),
            ("02 bulk assign", ("bulk", "assign", "--ids", "1", "--to", "张三", "--dry-run")),
            ("03 bulk tag", ("bulk", "tag", "--ids", "1", "--name", "回归", "--dry-run")),
            ("04 bulk untag", ("bulk", "untag", "--ids", "1", "--name", "回归", "--dry-run")),
            ("05 bulk rm", ("bulk", "rm", "--ids", "99", "--dry-run")),
            ("06 list created-after", ("list", "--created-after", "2020-01-01")),
            ("07 list created-before", ("list", "--created-before", "2030-01-01")),
            ("08 list updated-after", ("list", "--updated-after", "2020-01-01")),
            ("09 list open-only", ("list", "--open-only")),
            ("10 list closed-only", ("list", "--closed-only")),
            ("11 list sort", ("list", "--sort", "created")),
            ("12 report module", ("report", "module")),
            ("13 report assignee", ("report", "assignee")),
            ("14 report reporter", ("report", "reporter")),
            ("15 report aging", ("report", "aging")),
            ("16 report trend", ("report", "trend", "--days", "7")),
            ("17 report sla", ("report", "sla", "--hours", "1")),
            ("18 check import", ("check", "import", "--file", str(csv_file), "--release", "R1")),
            ("19 check progress", ("check", "progress", "--release", "R1")),
            ("20 check template", ("check", "template", "--release", "R2")),
            ("21 audit validate", ("audit", "validate")),
            ("22 audit orphans", ("audit", "orphans")),
            ("23 audit duplicates", ("audit", "duplicates")),
            ("24 audit log", ("audit", "log")),
            ("25 template save", ("template", "save", "--name", "t1", "--id", "1")),
            ("26 template list", ("template", "list")),
            ("27 template use", ("template", "use", "--name", "t1", "--title", "模板生成的缺陷")),
            ("28 tag list", ("tag", "list")),
            ("29 note", ("note", "1", "--text", "冒烟备注")),
            ("30 export jsonl", ("export", "--format", "jsonl", "--out", str(out_file))),
        ]

        passed = 0
        for name, argv in cases:
            rc, text = run(db, *argv)
            ok = rc == 0
            passed += ok
            first = text.splitlines()[0][:64] if text else "(无输出)"
            print(f"{'PASS' if ok else 'FAIL'}  {name:<26} rc={rc}  {first}")

        if out_file.exists():
            lines = out_file.read_text(encoding="utf-8").strip().splitlines()
            print(f"\nexport jsonl 实际写出 {len(lines)} 行 JSON")
        print(f"\n结果：{passed}/{len(cases)} 条通过")
        return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
