## 改了什么

<!-- 一句话说明这个 PR 解决什么问题 -->

## 类型

- [ ] 新功能
- [ ] 修 bug
- [ ] 重构（无行为变化）
- [ ] 文档
- [ ] 测试

## 自检清单

- [ ] `python3 -m unittest discover -s tests -t .` 全绿
- [ ] `python3 -m compileall -q buglens` 无错误
- [ ] 没有引入第三方依赖
- [ ] 没有在 `db.py` 之外 import sqlite3
- [ ] 新增/变更的规则同时更新了测试和文档
- [ ] 手动跑过 `buglens demo --force && buglens gate --release 2.4.0`

## 涉及门禁规则变化？（仅当改动 `gate.py`）

- [ ] 是（请在下方说明为什么这条规则应该/不应该阻断）
- [ ] 否

<!-- 规则变更理由 -->
