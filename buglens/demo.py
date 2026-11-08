"""示例数据。

`buglens demo` 用它一键造出一个能看、能跑门禁的数据集，
方便第一次接触的人 30 秒内看到全部功能。
"""

from __future__ import annotations

from .models import Bug, ChecklistItem

DEMO_BUGS: list[dict] = [
    {
        "title": "登录页在弱网下重复提交导致账号被锁",
        "module": "账号",
        "severity": "S1",
        "reporter": "张验",
        "env": "iOS 17.2 / App 2.4.0 / 4G 弱网 30% 丢包",
        "steps": "1. 打开登录页输入正确账号密码\n2. 使用 Network Link Conditioner 模拟 30% 丢包\n3. 连续点击登录按钮 3 次",
        "actual": "后端收到 3 次请求，触发风控锁定，用户 30 分钟内无法登录",
        "expected": "按钮点击后立即置灰，只提交一次请求",
        "assignee": "李承",
        "tags": "登录,风控",
        "status": "in_progress",
    },
    {
        "title": "订单详情金额格式化丢失分位小数",
        "module": "订单",
        "severity": "S2",
        "reporter": "王测",
        "env": "Android 14 / App 2.4.0",
        "steps": "1. 下单金额 12.30 元\n2. 进入订单详情页\n3. 观察合计金额",
        "actual": "显示为 12.3 元",
        "expected": "显示为 12.30 元，保留两位小数",
        "assignee": "赵码",
        "tags": "金额,展示",
        "status": "fixed",
    },
    {
        "title": "搜索框输入特殊字符返回 500 错误",
        "module": "搜索",
        "severity": "S1",
        "reporter": "张验",
        "env": "Web / Chrome 131 / 生产",
        "steps": "1. 在搜索框输入 %'\n2. 点击搜索\n3. 观察响应",
        "actual": "接口返回 500，页面白屏",
        "expected": "对特殊字符转义，返回空结果并提示无匹配",
        "assignee": "",
        "tags": "安全,SQL注入",
        "status": "new",
    },
    {
        "title": "个人中心头像上传后不刷新需重启",
        "module": "账号",
        "severity": "S3",
        "reporter": "陈点",
        "env": "iOS 17.2 / App 2.4.0",
        "steps": "1. 进入个人中心\n2. 上传新头像并保存\n3. 返回列表查看头像",
        "actual": "头像仍为旧图，杀掉进程重进才更新",
        "expected": "保存后立即刷新为心头像",
        "assignee": "赵码",
        "tags": "缓存",
        "status": "verified",
    },
    {
        "title": "推送通知点击后跳转到错误页面",
        "module": "消息",
        "severity": "S2",
        "reporter": "王测",
        "env": "Android 14 / App 2.4.0 / 后台状态",
        "steps": "1. 收到订单状态推送\n2. 在通知栏点击该推送\n3. 观察落地页",
        "actual": "跳转到首页而非对应订单详情",
        "expected": "直达该订单详情页",
        "assignee": "李承",
        "tags": "推送,深链",
        "status": "triaged",
    },
    {
        "title": "列表页下拉刷新偶现重复条目",
        "module": "订单",
        "severity": "S3",
        "reporter": "陈点",
        "env": "Android 13 / App 2.3.9",
        "steps": "1. 进入订单列表\n2. 快速下拉刷新 5 次\n3. 观察列表",
        "actual": "偶现同一条订单出现两次",
        "expected": "列表按订单号去重",
        "assignee": "赵码",
        "tags": "列表,并发",
        "status": "closed",
    },
    {
        "title": "设置页文案错别字：帐号 应为 账号",
        "module": "设置",
        "severity": "S4",
        "reporter": "陈点",
        "env": "全平台 / App 2.4.0",
        "steps": "1. 进入设置页\n2. 查看「帐号与安全」标题",
        "actual": "显示为「帐号与安全」",
        "expected": "统一为「账号与安全」",
        "assignee": "",
        "tags": "文案",
        "status": "new",
    },
    {
        "title": "支付回调超时未做重试导致订单状态不一致",
        "module": "支付",
        "severity": "S1",
        "reporter": "张验",
        "env": "生产 / 支付网关 v3",
        "steps": "1. 发起支付并完成扣款\n2. 模拟回调超时 10 秒\n3. 查询订单状态",
        "actual": "用户已扣款但订单仍为待支付，需人工补单",
        "expected": "回调失败进入重试队列，最终一致",
        "assignee": "李承",
        "tags": "支付,一致性",
        "status": "reopened",
    },
]

DEMO_CHECKS: list[tuple[str, str]] = [
    ("2.4.0", "S1/S2 缺陷全部闭环"),
    ("2.4.0", "核心链路回归用例全通过"),
    ("2.4.0", "灰度 5% 观察 24 小时无异常"),
    ("2.4.0", "回滚脚本演练完成"),
    ("2.4.0", "监控告警阈值已更新"),
]


def demo_bugs() -> list[Bug]:
    return [Bug(**item) for item in DEMO_BUGS]


def demo_checks() -> list[ChecklistItem]:
    return [ChecklistItem(release=rel, item=item) for rel, item in DEMO_CHECKS]
