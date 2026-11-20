# EXODUS.BIN / BOOTUP.BIN の文字列と参照元を集める（調査用）
# 使い方: python survey.py <ゲームのフォルダ> <出力 csv>
#   文字列: 0 終わりで、表示できる字（0x20〜0x7E と改行 0x0A、色の切り替えらしい 0x10/0x11）だけでできた並び
#   参照元: lea r16,[imm] / mov r16,imm の即値、2つ以上続く番地の表
import csv
import os
import re
import struct
import sys

import capstone

sys.stdout.reconfigure(encoding="utf-8")
game, out = sys.argv[1], sys.argv[2]
BASE = 0x100
OK = set(range(0x20, 0x7F)) | {0x0A, 0x0D, 0x10, 0x11}


def strings(d):
    """{番地: バイト列}  0 の直前で終わる並び（長さ 2 以上）"""
    res = {}
    i = 0
    n = len(d)
    while i < n:
        if d[i] in OK:
            j = i
            while j < n and d[j] in OK:
                j += 1
            if j < n and d[j] == 0 and j - i >= 2:
                s = d[i:j]
                # 英字を1つ以上含むものだけ
                if re.search(rb"[A-Za-z]{2}", s) or re.search(rb"[A-Za-z]", s) and len(s) <= 3:
                    res[i + BASE] = s
            i = j + 1
        else:
            i += 1
    return res


def code_refs(d):
    """即値 → [命令の番地]"""
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_16)
    md.detail = True
    md.skipdata = True
    refs = {}
    for ins in md.disasm(d, BASE):
        if ins.mnemonic == ".byte":
            continue
        if ins.mnemonic in ("lea", "mov", "push", "cmp", "add"):
            for op in ins.operands:
                v = None
                if ins.mnemonic == "lea" and op.type == capstone.x86.X86_OP_MEM and op.mem.base == 0 and op.mem.index == 0:
                    v = op.mem.disp & 0xFFFF
                elif ins.mnemonic in ("mov", "push") and op.type == capstone.x86.X86_OP_IMM:
                    v = op.imm & 0xFFFF
                if v is not None:
                    refs.setdefault(v, []).append(ins.address)
    return refs


def table_refs(d, strs):
    """2つ以上続く「文字列の先頭を指す番地」の表 → {番地: [表の位置]}"""
    heads = set(strs)
    refs = {}
    i = 0
    while i + 1 < len(d):
        run = []
        j = i
        while j + 1 < len(d) and struct.unpack_from("<H", d, j)[0] in heads:
            run.append(j)
            j += 2
        if len(run) >= 2:
            for p in run:
                refs.setdefault(struct.unpack_from("<H", d, p)[0], []).append(p + BASE)
            i = j
        else:
            i += 1
    return refs


rows = []
for name in ("BOOTUP.BIN", "EXODUS.BIN"):
    d = open(os.path.join(game, name), "rb").read()
    strs = strings(d)
    cr = code_refs(d)
    tr = table_refs(d, strs)
    for a in sorted(strs):
        s = strs[a]
        c = cr.get(a, [])
        t = tr.get(a, [])
        # 文字列の途中を指す参照
        mid = [hex(x) for k in range(a + 1, a + len(s)) for x in cr.get(k, [])]
        rows.append((name, f"{a:04x}", len(s), len(c), len(t), " ".join(f"{x:04x}" for x in c),
                     " ".join(f"{x:04x}" for x in t), " ".join(mid),
                     s.decode("latin-1").replace("\n", "\\n").replace("\r", "\\r")
                     .replace("\x10", "{10}").replace("\x11", "{11}")))
with open(out, "w", encoding="utf-8", newline="") as f:
    w = csv.writer(f)
    w.writerow(["file", "addr", "len", "ncode", "ntab", "code", "tab", "mid", "text"])
    w.writerows(rows)
for name in ("BOOTUP.BIN", "EXODUS.BIN"):
    rs = [r for r in rows if r[0] == name]
    noref = [r for r in rs if r[3] == 0 and r[4] == 0]
    print(f"{name}: {len(rs)} 件 {sum(r[2] for r in rs)} バイト、参照なし {len(noref)} 件")
