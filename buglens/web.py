"""只读 Web 看板。

用 http.server 起一个本地服务，页面复用 report.to_html，
不引入 Flask，也不需要前端构建。仅监听 127.0.0.1。
"""

from __future__ import annotations

import http.server
import socketserver
import threading
from pathlib import Path

from .db import Store
from .report import to_html
from .stats import summarize


def make_handler(store: Store, title: str = "缺陷看板"):
    """生成绑定到指定 Store 的请求处理器。"""

    class Handler(http.server.BaseHTTPRequestHandler):
        server_version = "buglens"
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802
            if self.path not in ("/", "/index.html"):
                self.send_error(404, "Not Found")
                return
            bugs = store.list_bugs()
            body = to_html(bugs, summarize(bugs), title=title).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt: str, *args) -> None:
            # 静默，避免刷屏
            return

    return Handler


def serve(store: Store, port: int = 8770, title: str = "缺陷看板", open_browser: bool = True):
    """阻塞启动服务。返回 (server, url)，便于测试里 shutdown。"""
    handler = make_handler(store, title=title)
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.TCPServer(("127.0.0.1", port), handler)
    url = f"http://127.0.0.1:{port}/"
    if open_browser:
        try:
            import webbrowser

            threading.Timer(0.4, lambda: webbrowser.open(url)).start()
        except Exception:
            pass
    return httpd, url
