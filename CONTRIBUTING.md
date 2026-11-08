# 贡献指南

## 环境

```bash
python3 --version   # 需要 >= 3.9
git clone https://github.com/chenjiannan553-hash/buglens.git
cd buglens
python3 -m unittest discover -s tests -t . -v
```

不需要创建虚拟环境，也不装任何依赖。

## 改动前先看这几条

**1. 不要引入第三方依赖。**
这个项目的核心承诺是"克隆下来就能跑"。`dependencies = []` 不是疏忽，是设计。

**2. 不要在 `db.py` 之外 import sqlite3。**
数据访问集中在一个文件，是换存储的前提。

**3. 领域规则用数据表达，不用 if 链。**
状态流转写在 `TRANSITIONS` 表里，门禁规则写在 `gate.evaluate()` 的顺序条目里。加规则应该是加数据，不是加分支。

**4. 校验规则改动必须同时改测试。**
`tests/test_validator.py` 里每个规则都有正反用例，别只加正向的。

## 提交前检查

```bash
# 1. 全部测试通过
python3 -m unittest discover -s tests -t . 

# 2. 编译检查
python3 -m compileall -q buglens

# 3. 静态检查（可选，CI 会跑）
pip install ruff==0.8.4 && ruff check buglens tests

# 4. 手动冒烟
python3 -m buglens demo --force
python3 -m buglens stats
python3 -m buglens gate --release 2.4.0   # 应返回 1
```

## 提交信息

用 conventional commits 前缀，中文描述：

```
feat(gate): 增加灰度观察时长校验
fix(dedupe): 同模块加权导致跨模块误判
docs(readme): 补充退出码约定
test(cli): 覆盖 check undo 的缺失分支
refactor(table): 抽出 display_width
```

## 新增一个子命令的完整步骤

假设要加 `buglens timeline`：

1. `cli.py` 写 `cmd_timeline(args) -> int`，返回退出码
2. `build_parser()` 里 `sub.add_parser("timeline", ...)` 并 `set_defaults(func=cmd_timeline)`
3. 领域逻辑放独立模块（如 `stats.py`），保持 `cli.py` 只做编排
4. `tests/test_cli.py` 加端到端用例，断言退出码和输出文字
5. README 的命令速查表加一行

## 新增一条门禁规则

1. `gate.evaluate()` 里追加一个 `GateCheck`
2. 明确它是 `blocking=True` 还是 `False`——**这是产品判断，请在 PR 里说明理由**
3. `tests/test_core.py` 的 `TestGate` 加用例
4. `README.md` 的规则表和 `docs/USAGE.md` 的详解同步更新

判定"要不要阻断"时的默认答案是否定的。阻断项越多，越容易被人用 `--force` 绕过，反而更不安全。

## 报告问题

用 issue 模板，请带上：

- 操作系统与 Python 版本
- 完整命令
- 实际输出
- 期望输出

一句话"用不了"没法排查。
