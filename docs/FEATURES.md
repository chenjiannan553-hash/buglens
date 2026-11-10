# 30 条增量能力清单

> 逐条可核对。验收脚本：`python scripts/smoke-features.py`（30/30）
> 单元测试：`python -m unittest discover -s tests -t .`（150 个）
>
> **兼容性约束（刻意不做系统级重构）**
> 这个仓库正被 dsh Super Agent 消费，重构会迫使它重新配置。因此本批能力：
> - 不删除、不改名任何既有子命令与参数；
> - 不改动 `bugs` / `history` / `checklist` 三张表的结构，只新增 `templates` 表（`CREATE TABLE IF NOT EXISTS`）；
> - 旧数据库打开即用，无需迁移脚本；
> - 现有命令的输出格式保持不变。
>
> 若将来确实要重构，正确顺序是：先冻结 Super Agent → 迁移 → 重新配置 → 回归验证，不能反向操作。

## A. 批量操作（5）— `bulk`

| # | 能力 | 命令 | 保护 |
|---|---|---|---|
| 01 | 批量状态流转 | `bulk set-status --ids 1,2 --to triaged` | 逐条走状态机，非法流转单条跳过；`--dry-run` 预演 |
| 02 | 批量指派 | `bulk assign --ids 1,2 --to 张三` | `--dry-run` |
| 03 | 批量加标签 | `bulk tag --ids 1,2 --name 回归` | 自动去重、保持原有顺序 |
| 04 | 批量去标签 | `bulk untag --ids 1,2 --name 回归` | 无变化则跳过 |
| 05 | 批量删除 | `bulk rm --ids 1,2 --yes` | 必须 `--yes` 或 `--dry-run`；未指定范围直接拒绝 |

`--ids` 支持 `1,2,5-7` 区间与自动去重；也可不写 ID，改用筛选条件批量圈定。

## B. 筛选增强（6）— `list`

| # | 能力 | 参数 | 说明 |
|---|---|---|---|
| 06 | 创建时间下界 | `--created-after 2026-11-01` | 日期自动补 `T00:00:00` |
| 07 | 创建时间上界 | `--created-before 2026-11-10` | 日期自动补 `T23:59:59` |
| 08 | 更新时间下界 | `--updated-after 2026-11-01` | 用于看近期有变动的缺陷 |
| 09 | 只看未闭环 | `--open-only` | 排除 verified / closed |
| 10 | 只看已闭环 | `--closed-only` | 与上者互斥 |
| 11 | 自定义排序 | `--sort severity\|created\|updated\|title\|id` | 默认仍是「S1 优先、ID 倒序」 |

## C. 报表（6）— `report`

| # | 能力 | 命令 | 输出 |
|---|---|---|---|
| 12 | 按模块分布 | `report module` | 数量 + 占比条 |
| 13 | 按处理人分布 | `report assignee` | 同上 |
| 14 | 按报告人分布 | `report reporter` | 同上 |
| 15 | 滞留时长分桶 | `report aging` | <24h / 1-3d / 3-7d / 7-30d / >30d |
| 16 | 每日新增闭环趋势 | `report trend --days 14` | 日期、新增、闭环三列 |
| 17 | SLA 超时清单 | `report sla --hours 72` | 按超时时长倒序 |

任何报表都可加 `--json` 输出机器可读结果。

## D. 验收清单（3）— `check`

| # | 能力 | 命令 | 说明 |
|---|---|---|---|
| 18 | CSV 批量导入清单 | `check import --file checks.csv --release 2.5.0` | 列：`item,owner`；支持 UTF-8 BOM |
| 19 | 完成率与未完成项 | `check progress --release 2.5.0` | 列出剩余条目及负责人 |
| 20 | 生成标准清单 | `check template --release 2.5.0` | 内置 5 条发布验收项 |

## E. 审计（4）— `audit`

| # | 能力 | 命令 | 失败语义 |
|---|---|---|---|
| 21 | 全库字段/状态校验 | `audit validate` | 发现问题退出码 1 |
| 22 | 无流转历史记录 | `audit orphans` | 列出孤儿缺陷 ID |
| 23 | 全库查重报告 | `audit duplicates --threshold 0.72` | 复用既有相似度算法 |
| 24 | 流转审计日志 | `audit log` | 按时间正序输出全部 history |

## F. 缺陷模板（3）— `template`

| # | 能力 | 命令 | 说明 |
|---|---|---|---|
| 25 | 从已有缺陷存模板 | `template save --name t1 --id 1` | 自动剔除 ID、状态、时间戳 |
| 26 | 列出模板 | `template list` | 名称 + 创建时间 |
| 27 | 套用模板建缺陷 | `template use --name t1 --title 新标题` | 可覆盖任意字段，落库前走强校验 |

## G. 标签与备注（2）

| # | 能力 | 命令 | 说明 |
|---|---|---|---|
| 28 | 标签云 | `tag list` | 按使用频次倒序 |
| 29 | 追加备注 | `note 1 --text "补充说明"` | 写入流转历史，不改变状态 |

## H. 导出（1）

| # | 能力 | 命令 | 说明 |
|---|---|---|---|
| 30 | JSONL 导出 | `export --format jsonl --out bugs.jsonl` | 一行一个缺陷，便于流式处理 |

---

## 验收记录

| 项 | 结果 |
|---|---|
| `scripts/smoke-features.py` | 30/30 PASS |
| 单元测试 | 150 个全过（原 121 + 新增 29） |
| ruff | All checks passed |
| 既有命令回归 | 未改签名，原 121 个测试全部通过 |
| 旧库兼容 | 仅新增表，`CREATE TABLE IF NOT EXISTS` 自动升级 |
