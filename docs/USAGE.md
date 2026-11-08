# 使用手册

README 讲"是什么"，这里讲"怎么用"。

---

## 1. 安装方式三选一

```bash
# A. 不安装，直接跑（推荐先这样试）
python3 -m buglens --help

# B. 装成全局命令
pip install .
buglens --help

# C. 可编辑安装，改代码立即生效（二次开发用）
pip install -e .
```

要求 Python ≥ 3.9，无第三方依赖。

---

## 2. 完整工作流

一个缺陷的完整生命周期，对应 7 条命令：

```bash
# 1. 录入（测试）
buglens add -i

# 2. 分诊（测试负责人）
buglens set 1 triaged --actor 张验 --note "已复现，环境信息完整"

# 3. 认领（开发）
buglens assign 1 李承
buglens set 1 in_progress --actor 李承

# 4. 提测（开发）
buglens set 1 fixed --actor 李承 --note "已加防抖，延迟 300ms 置灰"

# 5. 回归（测试）
buglens set 1 verified --actor 张验 --note "iOS/Android 双端验证通过"

# 6. 关闭（随版本）
buglens set 1 closed --actor 张验

# 7. 出报告
buglens export --format html --out 2.4.0-report.html
```

任何一步跳步都会被拒绝。比如跳过 `fixed` 直接 `verified`：

```console
$ buglens set 1 verified
[X] 不允许 待确认 → 已验证。可选目标：triaged, closed, reopened
```

---

## 3. 交互式录入

`buglens add -i` 逐项提示，必填项留空会在最后统一报错：

```console
$ buglens add -i
交互式录入，直接回车表示留空（必填项留空会校验失败）
标题: 支付回调超时未重试导致订单状态不一致
模块: 支付
严重级别 S1-S4 [S3]: S1
报告人: 张验
复现环境: 生产 / 支付网关 v3
复现步骤（一行一步）: 1. 发起支付并完成扣款
复现步骤（一行一步）: 2. 模拟回调超时 10 秒
复现步骤（一行一步）: 
实际结果: 用户已扣款但订单仍是待支付
期望结果: 回调失败进入重试队列，最终一致
处理人（可空）: 李承
标签，逗号分隔（可空）: 支付,一致性

[OK] 已创建缺陷 #9：支付回调超时未重试导致订单状态不一致
已指派给 李承
```

多行字段用「一行一步」的方式连续输入，空行结束。

---

## 4. 非交互式录入（脚本/CI 用）

```bash
buglens add \
  --title "搜索框输入特殊字符返回 500 错误" \
  --module 搜索 \
  --severity S1 \
  --reporter 张验 \
  --env "Web / Chrome 131 / 生产" \
  --steps $'1. 在搜索框输入 %\'\n2. 点击搜索' \
  --actual "接口返回 500，页面白屏" \
  --expected "转义后返回空结果并提示无匹配" \
  --tags "安全,注入"
```

步骤也可以用分号分隔：`--steps "打开首页；输入 %'；点击搜索"`，效果与换行相同。

---

## 5. 查重机制

每次 `add` 都会自动比对已有缺陷。综合相似度算法：

```
score = 0.55 × 标题相似度
      + 0.30 × 步骤相似度
      + 0.15 × 实际结果相似度
      + 0.05  (同模块)
      + 0.03  (同级别)
```

字符串相似度用 `difflib.SequenceMatcher`，先做归一化（去空格、标点、转小写）。

默认阈值 `0.72`。命中时：

```console
$ buglens add --title "登录页弱网重复提交锁号" ...
[!] 检测到疑似重复缺陷，入库前请确认：
  #1 S1 登录页在弱网下重复提交导致账号被锁（相似度 94%）
[X] 已中止入库。确认不是重复请加 --force 重新执行。
```

调阈值：

```bash
buglens add ... --threshold 0.85   # 更严格，少误报
buglens add ... --no-dedupe        # 完全跳过查重
```

全量扫描历史重复：

```bash
buglens dedupe --threshold 0.8
```

---

## 6. 发布门禁怎么用

### 手动评估

```bash
buglens gate --release 2.4.0
buglens gate --release 2.4.0 --max-s2 1        # 更严格
buglens gate --release 2.4.0 --report gate.txt # 落盘存档
```

### 挂 CI

```yaml
- name: 发布门禁
  run: |
    pip install .
    buglens gate --release ${{ github.ref_name }}
```

退出码非 0 会让 pipeline 变红。

### 挂 pre-push

见 `scripts/pre-push.sh`。

### 门禁规则详解

| 规则 | 判定 | 阻断 | 调整方式 |
| --- | --- | --- | --- |
| S1 清零 | 未闭环 S1 数为 0 | 是 | 不可关闭，硬规则 |
| S2 上限 | 未闭环 S2 ≤ 3 | 是 | `--max-s2 N` |
| 高级别已指派 | 无 S1/S2 缺 assignee | 是 | 先 `assign` |
| 验收清单 | 清单非空且全勾 | 是 | `check add` / `check done` |
| 待验证不堆积 | fixed 状态 ≤ 5 | 否 | 会 WARN 但不阻断 |

刻意做了区分：**"清单为空"只给 WARN 而不是 FAIL**。理由是没有清单不代表验收没做，强阻断会逼着人为了过关而随手勾选，那才是真正的风险。

---

## 7. 验收清单

```bash
# 建清单
buglens check add --release 2.4.0 --item "S1/S2 全部闭环" --owner 张验
buglens check add --release 2.4.0 --item "核心链路回归通过"
buglens check add --release 2.4.0 --item "灰度 5% 观察 24 小时"

# 查看
buglens check list --release 2.4.0

# 勾选
buglens check done --release 2.4.0 --id 1
buglens check undo --release 2.4.0 --id 1   # 勾错了撤回
```

清单与门禁联动：`2.4.0` 的清单没勾完，`gate --release 2.4.0` 就不可能通过。

---

## 8. 导入导出

### 从 Excel 批量导入

1. 在 Excel 里按 `buglens export --format csv` 的列头准备数据
2. 存成 UTF-8 CSV
3. 先干跑验证：

```bash
buglens import 缺陷列表.csv --dry-run
```

```console
解析完成：共 42 行，通过 39，退回 3
[!] 以下行被退回（不影响其他行入库）：
  第 7 行：缺少必填字段：复现环境（env）
  第 19 行：复现步骤只有 1 步，至少需要 2 步
  第 33 行：实际结果与期望结果完全相同，无法判定为缺陷

[dry-run] 未写入数据库。去掉 --dry-run 执行正式导入。
```

4. 确认无误后正式导入：

```bash
buglens import 缺陷列表.csv
```

**坏行隔离**：一行不合规不会导致整批失败，但会被明确列出。

### 导出格式对比

| 格式 | 用途 | 特点 |
| --- | --- | --- |
| `md` | 贴周报、PR、Issue | 含概览表、明细表、S1 专章 |
| `csv` | 给 Excel 继续加工 | 带 UTF-8 BOM，Excel 直接双击不乱码 |
| `html` | 发给别人看 | 单文件，样式内联，离线可开 |
| `json` | 程序消费、备份 | 保留中文不转义，`{"bugs": [...]}` |

---

## 9. 本地看板

```bash
buglens serve                      # 默认 8770
buglens serve --port 9000 --no-browser
```

只监听 `127.0.0.1`，不对外暴露。页面每次请求实时读库，改数据刷新即见。

---

## 10. 环境变量

| 变量 | 作用 | 默认 |
| --- | --- | --- |
| `BUGLENS_DB` | 数据库路径 | `./buglens.db` |
| `BUGLENS_RELEASE` | pre-push 钩子用的版本号 | `next` |
| `BUGLENS_SKIP_GATE` | 设为 1 跳过 pre-push 门禁 | 未设置 |

---

## 11. 常见问题

**Q: 数据存在哪？会上传吗？**
A: 就一个 `buglens.db` 文件，在当前目录。全程不联网。

**Q: 想换机器怎么办？**
A: `cp buglens.db` 到新机器即可，或 `export --format json` 导出后 `import`。

**Q: 状态改错了能撤回吗？**
A: 不能直接改历史，但可以走合法路径回去。比如误关了，先 `set N reopened` 再继续。审计记录会保留每一次动作——**痕迹不可篡改是刻意设计**。

**Q: 为什么 `verified` 不能直接到 `in_progress`？**
A: 已验证的缺陷重新出问题，说明是"复发"。语义上应该走 `reopened`，这样统计里能区分"新问题"和"老问题复发"。

**Q: 能多人同时用吗？**
A: 单机单进程。多人协作建议各自维护，或把 db 放共享盘（SQLite 的锁会串行化写入，高并发下会 `database is locked`）。

**Q: 支持哪些严重级别？**
A: 固定 S1-S4，不开放自定义。理由是级别一多就会有人发明 S3.5，而门禁需要一个稳定的比较基准。
