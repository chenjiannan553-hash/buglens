# Changelog

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [1.1.0] - 2026-11-10

新增 30 条增量能力，逐条清单见 [docs/FEATURES.md](docs/FEATURES.md)。

本批**刻意不做系统级重构**：仓库正被 dsh Super Agent 消费，重构会迫使它重新配置。
因此不改既有三张表的结构（只新增 `templates`）、不改既有命令签名、旧库打开即用。

### 新增

- **批量操作 5 项**：`bulk set-status / assign / tag / untag / rm`，支持
  `--ids 1,2,5-7`、筛选条件圈定、`--dry-run` 预演，删除需 `--yes`
- **查询增强 6 项**：创建/更新时间区间、`--open-only`、`--closed-only`、
  `--sort`（severity / created / updated / title / id）
- **报表 6 项**：`report module / assignee / reporter / aging / trend / sla`，
  均支持 `--json`
- **验收清单 3 项**：`check import`（CSV）、`check progress`、`check template`
- **审计 4 项**：`audit validate / orphans / duplicates / log`，
  校验发现问题退出码 1
- **模板 3 项**：`template save / list / use`，套用时可覆盖任意字段
- **标签与备注 2 项**：`tag list` 标签云、`note` 追加备注（入流转历史）
- **导出 1 项**：`export --format jsonl`

### 修复

- **LIKE 通配符转义**（#1）：`tag` / `keyword` 中的 `_`、`%` 现按字面匹配，
  `a_b` 不再误命中 `axb`
- **示例数据错别字**（#2 / PR #6）：`心头像` → `新头像`

### 验证

- 端到端冒烟 `scripts/smoke-features.py`：30/30 PASS
- 单元测试 150 个全过（原 121 + 新增 29）、ruff 全过
- 既有 121 个测试未改，确认旧调用方式无回归

## [1.0.0] - 2026-11-08

首个可用版本。

### 新增

- **结构化录入**：8 个必填字段强校验，收集式报错（一次报全）
- **状态机**：7 状态显式流转表，非法迁移拒绝并提示可选目标
- **审计留痕**：每次状态变更记录操作人、备注与时间戳
- **指纹查重**：标题/步骤/实际结果加权相似度（55/30/15），阈值可调
- **发布门禁**：5 条规则，阻断项决定进程退出码
- **验收清单**：按版本管理，联动门禁判定
- **多维查询**：状态/级别/模块/处理人/标签/关键词六维组合过滤
- **统计看板**：分布条形图、滞留时长、新增趋势
- **四种导出**：Markdown / CSV（带 BOM）/ HTML（单文件）/ JSON
- **容错导入**：CSV/JSON 双格式，坏行隔离，支持 `--dry-run`
- **本地 Web 看板**：`http.server` 只读服务，仅监听 127.0.0.1
- **示例数据**：`demo` 子命令一键造数据集
- **工程配套**：118 个单测、3 平台 × 3 版本 CI、ruff 静态检查、pre-push 钩子

### 设计取舍

- 无第三方依赖，仅用标准库
- 数据落本地 SQLite 单文件，不联网、无账号体系
- 严重级别固定 S1-S4，不开放自定义
- Web 看板只读，写操作一律走 CLI

[1.0.0]: https://github.com/chenjiannan553-hash/buglens/releases/tag/v1.0.0
