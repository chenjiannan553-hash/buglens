.PHONY: help test lint smoke demo clean build install

PY ?= python3
DB ?= buglens.db

help:  ## 显示可用命令
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

test:  ## 跑全部单测
	$(PY) -m unittest discover -s tests -t . -v

lint:  ## 静态检查
	$(PY) -m compileall -q buglens
	-$(PY) -m ruff check buglens tests

smoke:  ## 端到端冒烟（含门禁阻断校验）
	rm -f $(DB)
	$(PY) -m buglens demo
	$(PY) -m buglens stats
	$(PY) -m buglens list --severity S1
	$(PY) -m buglens export --format md --out /tmp/buglens-smoke.md
	@echo "--- 门禁应阻断 ---"
	-$(PY) -m buglens gate --release 2.4.0

demo:  ## 生成示例数据
	$(PY) -m buglens demo --force

clean:  ## 清理产物
	rm -rf __pycache__ */__pycache__ */*/__pycache__ build dist *.egg-info .coverage
	rm -f $(DB) buglens-*.md buglens-*.csv buglens-*.json buglens-*.html

build:  ## 构建 wheel
	$(PY) -m pip install --upgrade build
	$(PY) -m build

install:  ## 本地安装
	$(PY) -m pip install -e .
