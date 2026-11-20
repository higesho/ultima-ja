"""常駐部の ensure_scene（場面の表の読み込み）を x86 の模擬実行で確かめる。
本・途中の場面（文の後ろの 0 FE <番号>）と会話（先頭 FF <人物>）の切り替え、2 回目の近道を試す。
使い方: python test_scene.py   （build/MDJP.COM と build/conv の MDTEXT.LZC・MIDGAME1.LZC・MDJP.DAT を使う）
"""
import os
import struct
import sys

from unicorn import Uc, UC_ARCH_X86, UC_MODE_16, UC_HOOK_CODE
from unicorn.x86_const import (UC_X86_REG_AX, UC_X86_REG_BX, UC_X86_REG_CX, UC_X86_REG_DX, UC_X86_REG_SI,
                               UC_X86_REG_DI, UC_X86_REG_DS, UC_X86_REG_ES, UC_X86_REG_SS, UC_X86_REG_SP,
                               UC_X86_REG_CS, UC_X86_REG_IP, UC_X86_REG_FLAGS)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mdfmt  # noqa: E402

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
CSEG, GSEG, BSEG, SSEG, STUB = 0x1000, 0x3000, 0x5000, 0x7000, 0x8000
V = dict(CURNPC=0x122, DESC_S=0x136, BKPOS=0x154, BKID=0x158)

com = open(os.path.join(HERE, "build", "MDJP.COM"), "rb").read()
dat = open(os.path.join(HERE, "build", "conv", "MDJP.DAT"), "rb").read()
pat = bytes.fromhex("5053515256571e06c41ec26e")
es_addr = 0x100 + com.index(pat)
old21 = 0x103
mu = Uc(UC_ARCH_X86, UC_MODE_16)
mu.mem_map(0, 0x100000)
mu.mem_write(CSEG * 16 + 0x100, com)
mu.mem_write(CSEG * 16 + old21, struct.pack("<HH", 0, STUB))      # 元の INT 21h は STUB:0 の iret
mu.mem_write(STUB * 16, b"\xcf")
mu.mem_write(STUB * 16 + 0x10, b"\xf4")                            # 戻り先の hlt
files = {}
pos = {}


def dos(uc, addr, size, ud):
    if addr != STUB * 16:
        return
    ax = uc.reg_read(UC_X86_REG_AX)
    ah = ax >> 8
    sp = uc.reg_read(UC_X86_REG_SP)
    fl_addr = SSEG * 16 + sp + 4
    ok = True
    ds = uc.reg_read(UC_X86_REG_DS)
    dx = uc.reg_read(UC_X86_REG_DX)
    if ah == 0x3D:
        name = bytes(uc.mem_read(ds * 16 + dx, 13)).split(b"\0")[0]
        assert name == b"MDJP.DAT", name
        files[5] = dat
        pos[5] = 0
        uc.reg_write(UC_X86_REG_AX, 5)
    elif ah == 0x42:
        bx = uc.reg_read(UC_X86_REG_BX)
        cx = uc.reg_read(UC_X86_REG_CX)
        pos[bx] = (cx << 16) | dx
        uc.reg_write(UC_X86_REG_AX, dx)
    elif ah == 0x3F:
        bx = uc.reg_read(UC_X86_REG_BX)
        cx = uc.reg_read(UC_X86_REG_CX)
        d = files[bx][pos[bx]:pos[bx] + cx]
        uc.mem_write(ds * 16 + dx, d)
        pos[bx] += len(d)
        uc.reg_write(UC_X86_REG_AX, len(d))
    elif ah == 0x3E:
        pass
    else:
        ok = False
    fl = struct.unpack("<H", bytes(uc.mem_read(fl_addr, 2)))[0]
    fl = (fl & ~1) | (0 if ok else 1)
    uc.mem_write(fl_addr, struct.pack("<H", fl))


mu.hook_add(UC_HOOK_CODE, dos)


def run(buf):
    """会話スクリプトの置き場所に buf を置いて ensure_scene を呼ぶ。戻り: (CURNPC, 組の数)"""
    mu.mem_write(BSEG * 16, bytes(0x3800))
    mu.mem_write(BSEG * 16, buf)
    mu.mem_write(GSEG * 16 + 0x6EC2, struct.pack("<HH", 0, BSEG))
    for r, v in ((UC_X86_REG_DS, GSEG), (UC_X86_REG_SS, SSEG), (UC_X86_REG_SP, 0xFFF0), (UC_X86_REG_ES, 0)):
        mu.reg_write(r, v)
    sp = 0xFFF0 - 4
    mu.mem_write(SSEG * 16 + sp, struct.pack("<HH", 0x10, STUB))     # 近い ret の代わりに far の戻り先を積む
    # ensure_scene は near ret なので、CS を合わせ、戻り先はこのセグメントの中に hlt を置く
    mu.mem_write(CSEG * 16 + 0xFFF0, b"\xf4")
    mu.mem_write(SSEG * 16 + sp + 2, struct.pack("<H", 0xFFF0))
    mu.reg_write(UC_X86_REG_SP, sp + 2)
    mu.reg_write(UC_X86_REG_CS, CSEG)
    mu.emu_start(es_addr, 0xFFF0, timeout=2_000_000)
    cur = struct.unpack("<H", bytes(mu.mem_read(CSEG * 16 + V["CURNPC"], 2)))[0]
    npairs = struct.unpack("<H", bytes(mu.mem_read(CSEG * 16 + V["DESC_S"] + 2, 2)))[0]
    return cur, npairs


def rec_pairs(k):
    off, n = struct.unpack_from("<IH", dat, k * 6)
    return struct.unpack_from("<H", dat, off)[0] if n else None


books = [mdfmt.item(*e) for e in mdfmt.entries(open(os.path.join(HERE, "build", "conv", "MDTEXT.LZC"), "rb").read())[1]]
mids = [mdfmt.item(*e) for e in mdfmt.entries(open(os.path.join(HERE, "build", "conv", "MIDGAME1.LZC"), "rb").read())[1]]
talk = b"\xff\x02Spector\xf1"
ok = True
for label, buf, want in (("本 5", books[5], 0x85), ("本 5（2回目）", books[5], 0x85), ("本 26", books[26], 0x9A),
                         ("会話 スペクター", talk, 0x02), ("途中の場面 1", mids[1], 0xA0), ("本 0", books[0], 0x80)):
    cur, npairs = run(buf)
    good = cur == want and npairs == rec_pairs(want)
    ok &= good
    print(f"{label}: 表 {cur:#04x}（期待 {want:#04x}）、組 {npairs}（表の中 {rec_pairs(want)}） {'OK' if good else 'NG'}")
print("全部 OK" if ok else "NG あり")
