"""
myccusage_lib.web.server:
轻量嵌入式 Web 服务与 RESTful API:
- 基于 Python 标准库 http.server.ThreadingHTTPServer
- 提供 /api/agents, /api/data, /api/all, /api/refresh, /api/ping, /api/leave 接口
- 自动托管静态资源 (HTML5 SPA)
- 网页关闭心跳联动退出守护 (关闭网页自动安全退出后台)
- 零第三方外部依赖 (Zero pip dependencies)
"""

import os
import sys
import json
import time
import threading
import mimetypes
import webbrowser
from urllib.parse import urlparse, parse_qs
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from ..core import (
    SUPPORTED_AGENTS,
    get_daily_data,
    get_session_data,
    get_all_agents_summary
)

# 定位静态资源目录，使用绝对路径以避免运行目录不同导致的文件找不到问题
STATIC_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "static")

class DataCache:
    """
    轻量线程安全内存缓存池:
    - 用于 Web 服务运行期间对会话数据提供亚毫秒级（< 1ms）快速响应
    - 针对 (agent, mode, sort) 建立 30 秒短 TTL 缓存，消除反复切 Tab 与刷新的子进程开销
    - 当用户点击“刷新”或执行强制同步时，支持精准或全局失效
    """
    _lock = threading.Lock()  # 线程锁，防止并发读写引发的数据竞争和竞态条件
    _cache = {}  # 缓存字典，存储格式为 key: (timestamp, data)
    TTL = 30.0   # 缓存生存时间，设置短 TTL 是为了兼顾数据新鲜度和响应性能

    @classmethod
    def get(cls, key):
        """
        获取缓存数据。如果过期则清除对应键，避免返回陈旧数据。
        """
        with cls._lock:
            if key in cls._cache:
                ts, val = cls._cache[key]
                if time.time() - ts < cls.TTL:  # 判断是否在有效期内
                    return val
                del cls._cache[key]  # 超时则清理
            return None

    @classmethod
    def set(cls, key, data):
        """
        写入缓存数据，同时记录当前时间戳以备过期检查。
        """
        with cls._lock:
            cls._cache[key] = (time.time(), data)

    @classmethod
    def invalidate(cls, agent=None):
        """
        手动使缓存失效，支持按 agent 精准清理或全局清空。
        主要用于用户主动触发刷新时，强制获取最新数据。
        """
        with cls._lock:
            if agent is None or agent == "all":
                cls._cache.clear()  # 清空所有缓存
            else:
                to_del = [k for k in cls._cache if k[0] == agent]
                for k in to_del:
                    del cls._cache[k]  # 仅清理指定 agent 相关的缓存

class ServerState:
    """
    维护服务器的全局运行状态。
    作为单例状态机，供不同线程（如请求处理线程和看门狗线程）共享和同步。
    """
    has_client_connected = False  # 标记是否已有客户端连接过，避免刚启动未打开页面就直接触发退出
    last_heartbeat_time = 0.0     # 记录最后一次心跳的时间戳
    server = None                 # HTTP 服务器实例引用，用于安全关闭
    shutdown_initiated = False    # 防止重复执行关机流程的标记
    HEARTBEAT_TIMEOUT = 6.0       # 6秒无心跳则判定所有网页已关闭，这是一个经过权衡的容错时间

def watchdog_loop(server):
    """
    看门狗守护线程的工作逻辑。
    定期检查心跳超时情况，以此判断前端页面是否全部关闭，实现“用完即走”的无感后台退出。
    """
    while not ServerState.shutdown_initiated:
        time.sleep(1.0)  # 每秒轮询一次，降低 CPU 占用
        if ServerState.has_client_connected:
            # 计算距离上次心跳过去的时间
            elapsed = time.time() - ServerState.last_heartbeat_time
            if elapsed > ServerState.HEARTBEAT_TIMEOUT:
                ServerState.shutdown_initiated = True
                print("\n🌐 检测到浏览器网页已关闭，后台服务已自动安全退出。")
                # 在新线程中执行 shutdown，避免阻塞看门狗线程本身，也防止 HTTP Server 死锁
                threading.Thread(target=server.shutdown, daemon=True).start()
                break

class DashboardRequestHandler(BaseHTTPRequestHandler):
    """
    仪表盘请求处理类，处理所有的 HTTP GET/POST 请求，分发 RESTful API 与静态文件。
    """
    def log_message(self, format, *args):
        """
        覆盖默认的日志方法，保持控制台清爽，仅记录非 200/304 请求或简要日志，过滤高频 ping 心跳。
        这样可以避免日志刷屏，提升终端使用体验。
        """
        if len(args) >= 2 and str(args[1]) not in ("200", "304"):
            sys.stderr.write(f"[{self.log_date_time_string()}] {format % args}\n")

    def send_json(self, data, status=200):
        """
        统一封装 JSON 响应发送逻辑，处理 CORS 头和防缓存机制。
        """
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")  # 允许跨域，方便前端在 dev 模式下调试
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")  # 强力防缓存，确保每次拿到最新数据
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        """
        处理 CORS 预检请求。
        """
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        """
        处理 POST 请求。主要用于接收无状态的动作，如刷新和离线通知。
        """
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        # 网页卸载离线通知 (Beacon API)，前端页面即将关闭时的即时通知
        if path == "/api/leave":
            self.send_json({"left": True})
            return

        if path == "/api/refresh":
            agent = query.get("agent", ["agy"])[0]
            if agent not in SUPPORTED_AGENTS and agent != "all":
                self.send_json({"error": f"不支持的 Agent: {agent}"}, 400)
                return
            try:
                # 显式刷新穿透失效对应缓存，使得下一步请求必须真实读取数据
                DataCache.invalidate(agent)
                if agent == "all":
                    # 重新拉取所有 Agent 数据以生成总览
                    for ag in SUPPORTED_AGENTS:
                        get_daily_data(ag, force_refresh=True)
                    res = get_all_agents_summary()
                    DataCache.set(("all", "summary", False), res)
                else:
                    # 单独刷新某个 Agent 的数据
                    res = get_daily_data(agent, force_refresh=True)
                    DataCache.set((agent, "daily", False), res)
                self.send_json({"success": True, "data": res})
            except Exception as e:
                self.send_json({"error": str(e)}, 500)
            return

        self.send_json({"error": "Not Found"}, 404)

    def do_GET(self):
        """
        处理 GET 请求。主要包括 API 路由解析和静态文件映射。
        """
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        # 心跳保活接口，由前端定时器高频调用
        if path == "/api/ping":
            ServerState.has_client_connected = True  # 记录至少一次客户端连接
            ServerState.last_heartbeat_time = time.time()  # 更新心跳时间，重置看门狗
            self.send_json({"pong": True})
            return

        # 1. API 路由设计
        if path == "/api/agents":
            # 返回所有支持的 Agent 列表，动态生成导航菜单
            agents_list = []
            for k, v in SUPPORTED_AGENTS.items():
                agents_list.append({
                    "id": k,
                    "name": v["name"],
                    "subcmd": v["subcmd"]
                })
            self.send_json({"agents": agents_list})
            return

        if path == "/api/all":
            # 返回全局概览数据，优先走缓存以应对并发请求
            try:
                cache_key = ("all", "summary", False)
                cached = DataCache.get(cache_key)
                if cached is not None:
                    self.send_json(cached)
                    return
                res = get_all_agents_summary()
                DataCache.set(cache_key, res)
                self.send_json(res)
            except Exception as e:
                self.send_json({"error": str(e)}, 500)
            return

        if path == "/api/data":
            # 返回特定 Agent 的消费明细
            agent = query.get("agent", ["agy"])[0]
            mode = query.get("mode", ["daily"])[0]  # daily 或 session 模式
            sort_by_tokens = query.get("sort", ["time"])[0] == "tokens"

            if agent not in SUPPORTED_AGENTS:
                self.send_json({"error": f"不支持的 Agent: {agent}"}, 400)
                return

            cache_key = (agent, mode, sort_by_tokens)
            cached = DataCache.get(cache_key)
            if cached is not None:
                self.send_json(cached)
                return

            try:
                # 依据前端请求模式路由到底层的计算方法
                if mode == "session":
                    data = get_session_data(agent, sort_by_tokens=sort_by_tokens)
                else:
                    data = get_daily_data(agent, sort_by_tokens=sort_by_tokens)
                DataCache.set(cache_key, data)
                self.send_json(data)
            except Exception as e:
                self.send_json({"error": str(e)}, 500)
            return

        # 2. 静态文件路由服务
        clean_path = path.lstrip("/")
        # 对于根路径或不存在的路径，默认返回 SPA 的入口文件，实现单页应用的 history 路由 fallback
        if not clean_path or clean_path == "index.html":
            file_path = os.path.join(STATIC_DIR, "index.html")
        else:
            file_path = os.path.join(STATIC_DIR, clean_path)

        # 安全性兼具实用性：如果目录不存在或者是目录而不是文件，都回退到 index.html
        if not os.path.exists(file_path) or os.path.isdir(file_path):
            file_path = os.path.join(STATIC_DIR, "index.html")

        if os.path.exists(file_path):
            # 动态推断文件类型，确保前端加载 JS/CSS 时的 MIME 头正确
            mime_type, _ = mimetypes.guess_type(file_path)
            if not mime_type:
                mime_type = "application/octet-stream"
            # 为文本类资产指定 UTF-8 编码，防止乱码
            if mime_type.startswith("text/") or mime_type in ("application/javascript", "application/json"):
                mime_type += "; charset=utf-8"

            try:
                with open(file_path, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", mime_type)
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            except Exception as e:
                self.send_json({"error": f"读取静态文件失败: {e}"}, 500)
        else:
            self.send_json({"error": "静态文件未找到"}, 404)

def start_server(port=8488, default_agent="agy", auto_open=True):
    """
    启动本地 HTTP 服务器，完成组件初始化并调度守护线程。
    """
    # 端口自增重试逻辑：为了在默认端口被占用时自动降级寻找可用端口，无需用户手动介入
    server_address = ("127.0.0.1", port)
    server = None
    for p in range(port, port + 10):
        try:
            server_address = ("127.0.0.1", p)
            # 使用 ThreadingHTTPServer 支持并发请求处理，避免阻塞
            server = ThreadingHTTPServer(server_address, DashboardRequestHandler)
            port = p
            break
        except OSError:
            continue  # 尝试下一个端口

    if not server:
        print(f"❌ 无法绑定端口 {port} ~ {port + 9}，请使用 --port 指定其他可用端口", file=sys.stderr)
        sys.exit(1)

    url = f"http://127.0.0.1:{port}"
    print("=" * 78)
    print("  🚀 myccusage Web Dashboard 已启动")
    print("=" * 78)
    print(f"  📡 本地地址: {url}")
    print(f"  📊 默认 Agent: {SUPPORTED_AGENTS.get(default_agent, {}).get('name', default_agent)}")
    print("  💡 按 Ctrl+C 停止服务，或直接关闭浏览器网页自动退出")
    print("=" * 78)

    # 注册全局状态，使得其他线程（如看门狗）能够安全访问当前服务器实例
    ServerState.server = server
    ServerState.has_client_connected = False
    ServerState.last_heartbeat_time = time.time()
    ServerState.shutdown_initiated = False

    # 启动看门狗守护线程 (网页关闭联动安全退出)
    # 使用 daemon=True，以便主线程退出时看门狗自动终结
    watchdog = threading.Thread(target=watchdog_loop, args=(server,), daemon=True)
    watchdog.start()

    # 启动后台异步预热线程 (预加载默认 Agent 会话数据入内存，实现首屏秒开体验)
    def warmup_worker():
        try:
            w_agent = default_agent or "agy"
            data = get_daily_data(w_agent)
            DataCache.set((w_agent, "daily", False), data)
        except Exception:
            pass  # 预热失败忽略，不阻断主流程

    threading.Thread(target=warmup_worker, daemon=True).start()

    if auto_open:
        try:
            # 自动调用系统默认浏览器打开地址，降低用户使用门槛
            webbrowser.open(url)
        except Exception:
            pass

    try:
        # 进入阻塞循环，响应 HTTP 请求
        server.serve_forever()
    except KeyboardInterrupt:
        # 捕捉 Ctrl-C 信号，优雅退出
        print("\n👋 已安全停止 myccusage Web Dashboard 服务。")
    finally:
        # 释放底层 socket 资源
        server.server_close()
