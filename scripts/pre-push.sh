#!/usr/bin/env bash
# buglens pre-push 钩子：推送前跑发布门禁，阻断项不为零就不让推。
#
# 安装：
#   cp scripts/pre-push.sh .git/hooks/pre-push && chmod +x .git/hooks/pre-push
#
# 临时跳过：
#   BUGLENS_SKIP_GATE=1 git push

set -u

if [ "${BUGLENS_SKIP_GATE:-0}" = "1" ]; then
  echo "[buglens] BUGLENS_SKIP_GATE=1，跳过门禁检查。"
  exit 0
fi

# 没装 buglens 就静默放行，不阻塞无关仓库。
if ! command -v buglens >/dev/null 2>&1; then
  if [ -d "./buglens" ] && [ -f "./buglens/cli.py" ]; then
    BUGLENS_CMD="python3 -m buglens"
  else
    echo "[buglens] 未检测到 buglens，跳过门禁检查。"
    exit 0
  fi
else
  BUGLENS_CMD="buglens"
fi

RELEASE="${BUGLENS_RELEASE:-next}"

echo "[buglens] 对版本 '$RELEASE' 执行发布门禁..."
$BUGLENS_CMD gate --release "$RELEASE"
CODE=$?

if [ $CODE -ne 0 ]; then
  echo ""
  echo "[buglens] 门禁未通过（退出码 $CODE），推送已中止。"
  echo "[buglens] 处理完阻断项后重试；确需跳过：BUGLENS_SKIP_GATE=1 git push"
  exit 1
fi

echo "[buglens] 门禁通过。"
exit 0
