# buglens

**零依赖的缺陷跟踪与发布验收 CLI。** 把"这个版本能不能上"从口头争论，变成一条有退出码的命令。

![python](https://img.shields.io/badge/python-3.9%2B-blue)
![deps](https://img.shields.io/badge/dependencies-0-brightgreen)
![tests](https://img.shields.io/badge/tests-118%20passed-brightgreen)
![license](https://img.shields.io/badge/license-MIT-blue)

[![CI](https://github.com/OWNER/buglens/actions/workflows/ci.yml/badge.svg)](https://github.com/OWNER/buglens/actions/workflows/ci.yml)

---

## 为什么会有这个工具

大多数团队的 Bug 记录散在聊天框、Excel 和"我记得"里。于是每次发版都会重演同一段对话：

> 「S1 都清了吗？」「应该清了吧。」「你确定？」「……我查查。」

buglens 的判断是：**信息不结构化 = 没提 Bug。证据不足 = 不能上线。** 所以它做了三件不太讨喜的事：

1. **缺字段直接退回**，不给你"先记下来再说"的口子
2. **非法状态流转直接拒绝**，跳过验证的路径物理上不存在
3. **门禁有退出码**，能挂 CI、能挂 pre-push，不靠人盯

它不联网、不上传、不做账号体系。数据就在一个本地 SQLite 文件里，删掉即消失。

---

## 功能

| 模块 | 能力 | 命令 |
| --- | --- | --- |
| 结构化录入 | 8 个必填字段强校验，一次报全所有问题 | `add` / `add -i` |
| 状态机 | 7 状态、显式流转表，非法迁移拒绝并给出可选目标 | `set` |
| 审计留痕 | 每次状态变更记录操作人、备注、时间 | `show` |
| 指纹查重 | 标题 55% + 步骤 30% + 实际结果 15% 加权相似度 | `add` 自动 / `dedupe` |
| 发布门禁 | 5 条规则，阻断项决定退出码 | `gate` |
| 验收清单 | 按版本管理 Checklist，联动门禁 | `check` |
| 多维查询 | 状态/级别/模块/处理人/标签/关键词六维组合 | `list` / `search` |
| 统计看板 | 分布、条形图、滞留时长、新增趋势 | `stats --trend 7` |
| 四种导出 | Markdown / CSV / HTML / JSON | `export` |
| 容错导入 | CSV/JSON 双格式，坏行隔离不污染整批 | `import --dry-run` |
| 本地看板 | 单文件 HTML 可视化，127.0.0.1 只读服务 | `serve` |
| 示例数据 | 一条命令造出可演示的数据集 | `demo` |
| 工程配套 | 118 个单测 + 3 平台 CI + ruff | — |

---

## 30 秒上手

```bash
git clone https://github.com/OWNER/buglens.git
cd buglens

python3 -m buglens demo          # 造示例数据
python3 -m buglens stats         # 看概览
python3 -m buglens gate --release 2.4.0   # 门禁评估
python3 -m buglens serve         # 浏览器看板
```

不需要 `pip install` 任何东西。想装成全局命令：

```bash
pip install .
buglens --help
```

---

## 它到底拦什么

### 录入：缺一项就退回

```console
$ buglens add --title "登录挂了" --module 账号 --reporter 张三 \
    --env "" --steps "点一下" --actual "报错" --expected "不报错"

[X] 录入被退回，以下问题必须补齐：
  - 缺少必填字段：复现环境（env）
  - 标题过短（4 字符，至少 6）：'登录挂了'
  - 复现步骤过短（3 字符，至少 10）：'点一下'
  - 实际结果过短（2 字符，至少 4）：'报错'
  - 期望结果过短（3 字符，至少 4）：'不报错'
  - 复现步骤只有 1 步，至少需要 2 步（一行一步或用分号分隔）

$ echo $?
2
```

注意它**一次报全**，不会让你改一个再问下一个。

### 状态机：跳步不存在

```console
$ buglens set 6 fixed
[X] 不允许 已关闭 → 待验证。可选目标：reopened

$ buglens set 1 fixed --actor 李承 --note "已加防抖"
[OK] #1 修复中 → 待验证
```

```
new ──► triaged ──► in_progress ──► fixed ──► verified ──► closed
 │          │            │            │           │          │
 │          └────────────┴────────────┴───────────┴──────────┘
 │                              (误报/重复，可直达 closed)
 └──► reopened ──► triaged / in_progress
```

### 门禁：有退出码，能挂自动化

```console
$ buglens gate --release 2.4.0

发布门禁评估：2.4.0

  [FAIL] S1 清零 — 未闭环 S1：#8、#3、#1
  [PASS] S2 不超过 3 条 — 当前未闭环 S2 2 条
  [FAIL] 高级别已指派 — 1 条 S1/S2 未指派：#3
  [FAIL] 验收清单完成 — 已完成 0/5
  [PASS] 待验证不堆积 — 1 条待验证

结论：阻断发布。3 项未通过：S1 清零、高级别已指派、验收清单完成

$ echo $?
1
```

规则表：

| # | 规则 | 阻断 | 说明 |
| --- | --- | --- | --- |
| 1 | S1 清零 | 是 | 未闭环 S1 一律阻断，不接受口头豁免 |
| 2 | S2 ≤ 阈值 | 是 | 默认 3，`--max-s2` 可调 |
| 3 | S1/S2 已指派 | 是 | 没人负责的高级别缺陷视为未处理 |
| 4 | 验收清单完成 | 是 | 清单存在且全部勾选 |
| 5 | 待验证不堆积 | 否 | > 5 条给 WARN |

---

## 命令速查

| 命令 | 说明 | 例子 |
| --- | --- | --- |
| `init` | 初始化数据库 | `buglens init` |
| `add` | 录入缺陷 | `buglens add -i` |
| `list` | 条件列表 | `buglens list --severity S1 --status new` |
| `show` | 详情 + 流转历史 | `buglens show 3` |
| `set` | 变更状态 | `buglens set 3 triaged --actor 分诊员` |
| `assign` | 指派 | `buglens assign 3 李承` |
| `search` | 全文搜索 | `buglens search 回调` |
| `stats` | 统计概览 | `buglens stats --trend 14` |
| `dedupe` | 全量查重 | `buglens dedupe --threshold 0.8` |
| `gate` | 发布门禁 | `buglens gate --release 2.4.0 --report gate.txt` |
| `check` | 验收清单 | `buglens check add --release 2.4.0 --item "回归通过"` |
| `export` | 导出 | `buglens export --format html --out board.html` |
| `import` | 导入 | `buglens import data.csv --dry-run` |
| `serve` | 本地看板 | `buglens serve --port 8770` |
| `demo` | 示例数据 | `buglens demo --force` |
| `rm` | 删除 | `buglens rm 5 --yes` |
| `config` | 当前配置 | `buglens config` |

退出码约定：

| 码 | 含义 |
| --- | --- |
| 0 | 成功 / 门禁通过 |
| 1 | 门禁阻断 / 目标不存在 |
| 2 | 校验失败 / 非法状态流转 |
| 3 | 疑似重复，需 `--force` 确认 |

---

## 挂到 Git 钩子上

`scripts/pre-push.sh` 会在推送前跑门禁，阻断项不为零就不让推：

```bash
cp scripts/pre-push.sh .git/hooks/pre-push
chmod +x .git/hooks/pre-push
```

```bash
# .git/hooks/pre-push
RELEASE="${BUGLENS_RELEASE:-next}"
buglens gate --release "$RELEASE" || {
  echo "门禁未通过，推送已中止。加 BUGLENS_SKIP_GATE=1 可临时跳过。"
  exit 1
}
```

---

## 数据模型

```
bugs ──1:N──► history          （状态流转审计）
  │
  └── checklist（按 release 分组，独立表）
```

| 表 | 关键字段 |
| --- | --- |
| `bugs` | title, module, severity(S1-S4), status, reporter, env, steps, actual, expected, assignee, tags |
| `history` | bug_id, from_status, to_status, actor, note, at |
| `checklist` | release, item, done, owner |

数据库默认在 `./buglens.db`，用 `BUGLENS_DB` 环境变量或 `--db` 覆盖。

---

## 代码结构

```
buglens/
├── buglens/
│   ├── cli.py            argparse 入口，17 个子命令
│   ├── models.py         数据类与常量
│   ├── db.py             SQLite 持久化，唯一的数据访问层
│   ├── validator.py      强校验
│   ├── state_machine.py  流转表
│   ├── dedupe.py         difflib 加权相似度
│   ├── gate.py           门禁规则
│   ├── stats.py          统计聚合
│   ├── report.py         md / csv / html 渲染
│   ├── importer.py       csv / json 解析
│   ├── web.py            http.server 只读看板
│   ├── table.py          中文等宽表格
│   └── demo.py           示例数据
├── tests/                118 个单测
├── docs/                 使用手册与架构说明
└── .github/workflows/    CI
```

设计约束：**除 `db.py` 外任何模块都不碰 sqlite**，所以换存储只需改一个文件。

详见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

---

## 已知边界

- 单机单进程，没有并发写保护（SQLite 默认行为，多进程写会串行化）
- 不做账号与权限，"谁是测试谁能验证"靠流程约定而非技术强制
- 查重基于字符串相似度，语义相同但措辞完全不同的重复项会漏
- 看板只读，增删改走 CLI

这些是有意为之的取舍——每一条都是为了让工具能塞进一个文件里跑起来。

---

## License

MIT
