"""零依赖 Chromium IndexedDB (LevelDB) 定向提取解码内核。

对标 zstdcodec.py 的地位：纯 Python、无第三方依赖、只读。
设计原则（见 docs/豆包工作统计适配架构与施工计划.md）：
  * 只做"定向提取"，不做完整 V8 反序列化 —— 成本随扫描字节数线性，与结构深度无关。
  * 热路径（WAL .log）：值未压缩，裸字节结构化提取。
  * 冷路径（SSTable .ldb）：块 Snappy 压缩，解压后值原样可搜，无需重建键。
  * 自指污染防护：usage 必须与 message_id(UUID) 等轮次身份字段共现才入账，
    绝不按裸关键词计数（豆包存储会实时记录当前对话，裸关键词会命中自身命令回声）。

本模块不含任何采集/固化/配置逻辑（那是 adapters/doubao_capture.py 的职责）。
"""

from __future__ import annotations

import os
import re
import struct

__all__ = [
    "snappy_decompress",
    "iter_table_blocks",
    "wal_complete_end",
    "iter_wal_batches",
    "extract_usage_records",
    "extract_conversation_meta",
]


# ---------------------------------------------------------------------------
# Snappy raw block 解压（冷路径专用，~60 行核心）
# ---------------------------------------------------------------------------
def snappy_decompress(data: bytes) -> bytes:
    """解压 Snappy raw block（非 framing 格式）。失败抛 ValueError。"""
    n = len(data)
    i = 0
    # preamble: varint  uncompressed length
    ulen = 0
    shift = 0
    while True:
        if i >= n:
            raise ValueError("snappy: truncated preamble")
        b = data[i]
        i += 1
        ulen |= (b & 0x7F) << shift
        if not b & 0x80:
            break
        shift += 7
        if shift > 35:
            raise ValueError("snappy: bad varint")
    out = bytearray()
    while i < n:
        tag = data[i]
        i += 1
        kind = tag & 0x03
        if kind == 0:  # literal
            lit_len = (tag >> 2) + 1
            if lit_len > 60:
                extra = lit_len - 60
                if i + extra > n:
                    raise ValueError("snappy: truncated literal len")
                lit_len = int.from_bytes(data[i:i + extra], "little") + 1
                i += extra
            if i + lit_len > n:
                raise ValueError("snappy: truncated literal")
            out += data[i:i + lit_len]
            i += lit_len
        else:
            if kind == 1:  # copy 1-byte offset
                if i >= n:
                    raise ValueError("snappy: truncated copy1")
                length = 4 + ((tag >> 2) & 0x07)
                offset = ((tag >> 5) << 8) | data[i]
                i += 1
            elif kind == 2:  # copy 2-byte offset
                if i + 2 > n:
                    raise ValueError("snappy: truncated copy2")
                length = (tag >> 2) + 1
                offset = int.from_bytes(data[i:i + 2], "little")
                i += 2
            else:  # kind == 3, copy 4-byte offset
                if i + 4 > n:
                    raise ValueError("snappy: truncated copy4")
                length = (tag >> 2) + 1
                offset = int.from_bytes(data[i:i + 4], "little")
                i += 4
            if offset == 0 or offset > len(out):
                raise ValueError("snappy: bad copy offset")
            start = len(out) - offset
            if offset >= length:
                out += out[start:start + length]  # 无重叠快路径
            else:
                for k in range(length):  # 重叠拷贝逐字节
                    out.append(out[start + k])
    if len(out) != ulen:
        raise ValueError(f"snappy: length mismatch {len(out)} != {ulen}")
    return bytes(out)


# ---------------------------------------------------------------------------
# 基础 varint
# ---------------------------------------------------------------------------
def _varint(b: bytes, i: int) -> tuple[int, int]:
    r = 0
    s = 0
    while True:
        x = b[i]
        i += 1
        r |= (x & 0x7F) << s
        if not x & 0x80:
            return r, i
        s += 7
        if s > 63:
            raise ValueError("varint overflow")


# ---------------------------------------------------------------------------
# SSTable (.ldb) 读取：footer → index → data blocks（冷路径追平）
# ---------------------------------------------------------------------------
_TABLE_MAGIC = b"\x57\xfb\x80\x8b\x24\x75\x47\xdb"


def _read_block(data: bytes, off: int, size: int) -> bytes:
    """读取一个块并按 trailer type 解压（0=raw, 1=snappy）。"""
    if off + size + 5 > len(data):
        raise ValueError("table: block out of range")
    raw = data[off:off + size]
    btype = data[off + size]
    if btype == 0:
        return raw
    if btype == 1:
        return snappy_decompress(raw)
    raise ValueError(f"table: unsupported block compression {btype}")


def _block_entries(block: bytes):
    """遍历块内条目 (key, value)，处理前缀压缩与 restart array。"""
    n = len(block)
    if n < 4:
        return
    num_restarts = struct.unpack_from("<I", block, n - 4)[0]
    entries_end = n - 4 - 4 * num_restarts
    i = 0
    key = b""
    while i < entries_end:
        shared, i = _varint(block, i)
        unshared, i = _varint(block, i)
        vlen, i = _varint(block, i)
        key = key[:shared] + block[i:i + unshared]
        i += unshared
        value = block[i:i + vlen]
        i += vlen
        yield key, value


def iter_table_blocks(path: str):
    """yield 一个 .ldb 文件内所有数据块的解压字节（供定向提取）。"""
    with open(path, "rb") as f:
        data = f.read()
    if len(data) < 48 or data[-8:] != _TABLE_MAGIC:
        return
    footer = data[-48:]
    p = 0
    _mi_off, p = _varint(footer, p)
    _mi_size, p = _varint(footer, p)
    idx_off, p = _varint(footer, p)
    idx_size, p = _varint(footer, p)
    index = _read_block(data, idx_off, idx_size)
    for _key, handle in _block_entries(index):
        q = 0
        off, q = _varint(handle, q)
        size, q = _varint(handle, q)
        try:
            yield _read_block(data, off, size)
        except (ValueError, IndexError):
            continue  # 单块损坏不影响整体


# ---------------------------------------------------------------------------
# WAL (.log) 帧解析：32KB 块，头 7 字节 (crc4 + len2 + type1)
# ---------------------------------------------------------------------------
_BLOCK = 32768


def iter_wal_batches(data: bytes):
    """yield (record_end_offset, writebatch_payload)。只产出完整逻辑记录。

    type: 1=full, 2=first, 3=middle, 4=last。容忍尾部撕裂写（遇到非法帧即停）。
    """
    n = len(data)
    pos = 0
    buf = b""
    assembling = False
    while pos + 7 <= n:
        block_off = pos % _BLOCK
        if block_off + 7 > _BLOCK:  # 块尾不足 7 字节头，跳到下一块
            pos += _BLOCK - block_off
            continue
        _crc, length, typ = struct.unpack_from("<IHB", data, pos)
        if typ == 0 and length == 0:  # 块尾零填充
            pos += _BLOCK - block_off
            continue
        if typ not in (1, 2, 3, 4) or pos + 7 + length > n:
            break
        frag = data[pos + 7:pos + 7 + length]
        pos += 7 + length
        if typ == 1:
            yield pos, frag
        elif typ == 2:
            buf = frag
            assembling = True
        elif typ == 3:
            if assembling:
                buf += frag
        elif typ == 4:
            if assembling:
                yield pos, buf + frag
            buf = b""
            assembling = False


def wal_complete_end(data: bytes) -> int:
    """返回最后一条完整逻辑记录之后的字节偏移（供 offset 追踪，避免撕裂写入账）。"""
    end = 0
    for rec_end, _payload in iter_wal_batches(data):
        end = rec_end
    return end


# ---------------------------------------------------------------------------
# 结构化定向提取（热/冷路径共用）
# ---------------------------------------------------------------------------
# usage 五元组：高度特异的数值模式，自身命令回声（含 \d+ 正则文本）不会命中。
_USAGE_RE = re.compile(
    rb'\{"system_prompt":(\d+),"messages":(\d+),"skills":(\d+),'
    rb'"tools":(\d+),"total_window_size":(\d+)\}'
)
# 轮次身份：message_id 为 36 位 UUID。V8 字符串 = tag 0x22('\"') + 长度字节 + 内容；
# 长度字节用 '.' 通配（随 id 长度变化），内容模式本身高度特异。
_MSGID_RE = re.compile(rb'message_id".([0-9a-fA-F-]{36})')
_CONVID_RE = re.compile(rb'conversation_id".(\d{6,20})')
_MODELID_RE = re.compile(rb'model_id".(\d{1,6})')
_SECTION_RE = re.compile(rb'section_tag_1h".(\d{6,20}_\d{10})')
# create_time_ms：V8 double tag 'N'(0x4E) + 8 字节 IEEE754 LE。
_CTIME_RE = re.compile(rb'create_time_msN(.{8})', re.DOTALL)

_ID_WINDOW = 6000  # usage 与身份字段的共现窗口（实测身份字段均在 ±3KB 内）


def _find_near(pat: re.Pattern, blob: bytes, center: int):
    lo = max(0, center - _ID_WINDOW)
    hi = min(len(blob), center + _ID_WINDOW)
    return pat.search(blob, lo, hi)


def extract_usage_records(blob: bytes) -> list[dict]:
    """从原始/解压字节中提取 usage 轮次记录。

    硬约束：usage 必须与 message_id(UUID) 共现才入账（自指污染防护）。
    返回 list[dict]，每项含 usage 五元组 + 轮次身份 + 时间戳(ms)。
    同一 message_id 的多个快照版本都会产出，去重/取最大由调用方负责。
    """
    out = []
    for m in _USAGE_RE.finditer(blob):
        center = m.start()
        mid = _find_near(_MSGID_RE, blob, center)
        if not mid:
            continue  # 无轮次身份 → 视为回声/噪声，丢弃
        sp, msgs, skills, tools, tw = (int(x) for x in m.groups())
        rec = {
            "message_id": mid.group(1).decode("ascii"),
            "system_prompt": sp,
            "messages": msgs,
            "skills": skills,
            "tools": tools,
            "total_window_size": tw,
            "context_total": sp + msgs + skills + tools,
        }
        conv = _find_near(_CONVID_RE, blob, center)
        if conv:
            rec["conversation_id"] = conv.group(1).decode("ascii")
        sec = _find_near(_SECTION_RE, blob, center)
        if sec:
            rec["section_tag"] = sec.group(1).decode("ascii")
        model = _find_near(_MODELID_RE, blob, center)
        if model:
            rec["model_id"] = model.group(1).decode("ascii")
        ct = _find_near(_CTIME_RE, blob, center)
        if ct:
            try:
                rec["create_time_ms"] = int(struct.unpack("<d", ct.group(1))[0])
            except struct.error:
                pass
        out.append(rec)
    return out


# 会话清单：conversation-list-data-* 键下的 name/create_time/update_time。
def extract_conversation_meta(blob: bytes) -> list[dict]:
    """提取会话清单条目（id + name + create/update 时间）。

    会话名是 V8 字符串，长度字节可变；用 conversation_id 锚点 + 邻近 name 字段提取。
    仅用于标题兜底，缺失不影响 usage 主链路。
    """
    out = []
    # 锚点：conversation_id 后跟数字字符串（tag 0x22 + 长度字节通配）。
    for m in re.finditer(rb'conversation_id".(\d{6,20})', blob):
        cid = m.group(1).decode("ascii")
        window = blob[m.start():m.start() + 2000]
        rec = {"conversation_id": cid}
        # name 字段：V8 字符串有三种 tag —— '"'(0x22) Latin1 / 'c'(0x63) UTF16LE / 'S'(0x53) UTF8，
        # 后跟 varint 长度（双字节串为字节数）。中文会话名走 'c' 分支。
        nm = re.search(rb'name(["cS])', window)
        if nm:
            tag = nm.group(1)
            try:
                ln, j = _varint(window, nm.end())
                raw = window[j:j + ln]
                if tag == b'"':
                    rec["name"] = raw.decode("latin-1")
                elif tag == b"c":
                    rec["name"] = raw.decode("utf-16-le")
                else:
                    rec["name"] = raw.decode("utf-8")
            except (ValueError, IndexError, UnicodeDecodeError):
                pass
        for field, key in (("create_time", "create_time"), ("update_time", "update_time")):
            fm = re.search(field.encode() + rb'N(.{8})', window, re.DOTALL)
            if fm:
                try:
                    rec[key] = int(struct.unpack("<d", fm.group(1))[0])
                except struct.error:
                    pass
        out.append(rec)
    return out