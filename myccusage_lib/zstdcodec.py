"""
myccusage_lib.zstdcodec:
零第三方依赖的 Zstandard 多帧解码内核。

背景：
DeepSeek Harness (dsh) 的会话日志统一以「追加型多帧 concatenated Zstandard」落盘
(`session.v4.jsonl.zstd`)，每完成一次 append 批次就追加一个独立 frame。这类容器的
读取不能用"一次性整体解压"处理，必须逐帧扫描边界、逐帧解压、遇残缺尾帧即安全停止。

三级降级策略 (全部为系统自带能力，不引入任何 pip 依赖)：
1. `ctypes` 直调系统 libzstd —— 最快 (6ms / 3MB)，覆盖 macOS / Linux / Windows；
2. 系统 `zstd` 命令行 —— libzstd 不可加载时的兜底 (约慢 3~5 倍)；
3. 两者皆无 → `available()` 返回 False，由上层适配器据此优雅跳过该 Agent。

设计约束：
- 只读、不写任何文件，绝不修改 dsh 的原始数据；
- 容忍残缺尾帧 (进程正在追加时读到半个 frame 属正常现象)，绝不因此抛异常；
- 解压缓冲在模块内复用，避免每帧一次 `malloc` 带来的抖动。
"""

from __future__ import annotations

import os
import sys
import shutil
import ctypes
import ctypes.util
import subprocess

# Zstandard 帧魔数的小端表示 (0xFD2FB528)
ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"

# 单帧解压的初始缓冲 (16MB) 与上限 (256MB)。
# dsh 实测单帧最大约 108KB，此处留足三个数量级的余量；
# 超限时视为异常帧直接停止，而不是无限扩容把内存吃满。
_INITIAL_FRAME_CAP = 16 << 20
_MAX_FRAME_CAP = 256 << 20

# libzstd 常见路径候选（按优先级）。find_library 在部分 Linux 发行版上找不到
# 只装了 runtime 的 libzstd.so.1，故显式补齐 soname 兜底。
_LIB_CANDIDATES = (
    "libzstd.so.1",
    "libzstd.so",
    "libzstd.1.dylib",
    "libzstd.dylib",
    "libzstd.dll",
)

_ZSTD_CLI_CANDIDATES = (
    "/opt/homebrew/bin/zstd",
    "/usr/local/bin/zstd",
    "/usr/bin/zstd",
    "/opt/anaconda3/bin/zstd",
)


class _LibZstd:
    """
    libzstd 的 ctypes 轻量封装。

    只绑定解码所需的四个符号，避免把整个 C ABI 铺开：
    - `ZSTD_findFrameCompressedSize`：拿到当前帧的压缩字节数（用于逐帧定位）
    - `ZSTD_decompress`：解压单帧
    - `ZSTD_isError`：错误判定
    - `ZSTD_getErrorName`：错误名（仅用于诊断日志）
    """

    __slots__ = ("lib", "out_buf", "out_cap", "src_buf", "src_cap")

    def __init__(self, lib):
        self.lib = lib
        self.out_cap = _INITIAL_FRAME_CAP
        self.out_buf = ctypes.create_string_buffer(self.out_cap)
        self.src_cap = _INITIAL_FRAME_CAP
        self.src_buf = ctypes.create_string_buffer(self.src_cap)

    def _grow_out(self) -> bool:
        """当前输出缓冲装不下这一帧时翻倍扩容，超过上限则放弃。"""
        if self.out_cap >= _MAX_FRAME_CAP:
            return False
        self.out_cap = min(self.out_cap * 2, _MAX_FRAME_CAP)
        self.out_buf = ctypes.create_string_buffer(self.out_cap)
        return True

    def _ensure_src(self, need: int) -> bool:
        """保证源缓冲容得下整个压缩文件（避免逐帧切片产生副本）。"""
        if need <= self.src_cap:
            return True
        if need > _MAX_FRAME_CAP:
            return False
        self.src_cap = min(max(need, self.src_cap * 2), _MAX_FRAME_CAP)
        self.src_buf = ctypes.create_string_buffer(self.src_cap)
        return True

    def decompress_frames(self, raw: bytes) -> bytes:
        """
        解压一个「多帧拼接」的 Zstandard 容器，返回拼接后的明文。

        逐帧推进：`ZSTD_findFrameCompressedSize` 给出帧边界，`ZSTD_decompress`
        解出该帧后指针前移。任一帧解析失败即停止 —— 这正好覆盖了
        "写入方正在追加、读到半个 frame" 的残缺尾帧场景。
        """
        n = len(raw)
        if n == 0 or not self._ensure_src(n):
            return b""
        lib = self.lib
        ctypes.memmove(self.src_buf, raw, n)
        base = ctypes.addressof(self.src_buf)

        parts = []
        pos = 0
        while pos < n:
            frame_size = lib.ZSTD_findFrameCompressedSize(base + pos, n - pos)
            if lib.ZSTD_isError(frame_size) or frame_size <= 0:
                break
            while True:
                written = lib.ZSTD_decompress(
                    self.out_buf, self.out_cap, base + pos, frame_size
                )
                if not lib.ZSTD_isError(written):
                    parts.append(ctypes.string_at(self.out_buf, written))
                    break
                # 输出缓冲不足是唯一可恢复的错误：扩容后重试同一帧
                if not self._grow_out():
                    return b"".join(parts)
            pos += frame_size
        return b"".join(parts)


_lib_handle: _LibZstd | None = None
_lib_probed = False
_cli_path: str | None = None
_cli_probed = False


def _try_load_libzstd() -> _LibZstd | None:
    """按「find_library → 显式 soname 列表」的顺序尝试加载 libzstd。"""
    names = []
    found = ctypes.util.find_library("zstd")
    if found:
        names.append(found)
    names.extend(_LIB_CANDIDATES)

    for name in names:
        try:
            lib = ctypes.CDLL(name)
        except OSError:
            continue
        try:
            lib.ZSTD_findFrameCompressedSize.restype = ctypes.c_size_t
            lib.ZSTD_findFrameCompressedSize.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
            lib.ZSTD_decompress.restype = ctypes.c_size_t
            lib.ZSTD_decompress.argtypes = [
                ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t,
            ]
            lib.ZSTD_isError.restype = ctypes.c_uint
            lib.ZSTD_isError.argtypes = [ctypes.c_size_t]
            lib.ZSTD_getErrorName.restype = ctypes.c_char_p
            lib.ZSTD_getErrorName.argtypes = [ctypes.c_size_t]
        except AttributeError:
            continue
        return _LibZstd(lib)
    return None


def _cli() -> str | None:
    """定位系统 zstd 命令行（libzstd 不可用时的兜底路径）。"""
    global _cli_path, _cli_probed
    if _cli_probed:
        return _cli_path
    _cli_probed = True
    exe = shutil.which("zstd")
    if exe:
        _cli_path = exe
        return _cli_path
    for cand in _ZSTD_CLI_CANDIDATES:
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            _cli_path = cand
            break
    return _cli_path


def backend() -> str:
    """返回当前生效的解码后端名：`libzstd` / `cli` / `none`。"""
    global _lib_handle, _lib_probed
    if not _lib_probed:
        _lib_probed = True
        _lib_handle = _try_load_libzstd()
    if _lib_handle is not None:
        return "libzstd"
    return "cli" if _cli() else "none"


def available() -> bool:
    """当前环境是否具备 Zstandard 解码能力（libzstd 或 zstd CLI 任一可用即可）。"""
    return backend() != "none"


def decompress(raw: bytes) -> bytes:
    """
    解压一个多帧 Zstandard 字节流。

    调用方应先通过 `is_zstd()` 判定内容类型；本函数不做格式嗅探，
    直接按 zstd 容器处理（非 zstd 数据会解出空字节串而非抛异常）。
    """
    if not raw:
        return b""
    b = backend()
    if b == "libzstd" and _lib_handle is not None:
        return _lib_handle.decompress_frames(raw)
    if b == "cli":
        exe = _cli()
        if not exe:
            return b""
        try:
            proc = subprocess.run(
                [exe, "-dc", "-q"],
                input=raw,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=30,
            )
            return proc.stdout or b""
        except (OSError, subprocess.SubprocessError):
            return b""
    return b""


def is_zstd(head: bytes) -> bool:
    """按帧魔数判定一段字节流的开头是否为 Zstandard 帧。"""
    return head[:4] == ZSTD_MAGIC


def decompress_file(path: str) -> bytes:
    """
    读取并解压一个可能为 zstd 的日志文件，返回明文 JSONL 字节流。

    - 明文 `.jsonl` 直接原样返回（dsh 支持 `compression: 'none'` 配置）；
    - `read` 阶段任何 I/O 异常都返回空字节串，交由上层把该会话视为"暂不可读"，
      绝不让单文件故障拖垮整个 Agent 的统计。
    """
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError:
        return b""
    if not raw:
        return b""
    if not is_zstd(raw):
        return raw
    return decompress(raw)


def platform_hint() -> str:
    """返回一句可读的后端与平台说明，供 CLI/日志诊断使用。"""
    return f"{backend()}@{sys.platform}"
