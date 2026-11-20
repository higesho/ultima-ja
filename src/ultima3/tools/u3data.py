# ウルティマIII の文字列と参照元を集める（build_u3jp.py などから使う）
#   文字列: 0 終わりで、表示できる字（0x20〜0x7E、改行 0x0A、ラベルの両端の飾り 0x10/0x11）だけでできた並び
#   参照元:
#     lea si,[番地]（8D 36）: 番地が文字列の中を指すもの
#     番地の表: 文字列の中を指す番地が2つ以上続くもの（誤検出があるので tables.txt で採否を決める）
#   「単位」= 参照される番地。そこから次の 0 までを1つの文字列として訳す
import os
import struct

import capstone

BASE = 0x100
OK = set(range(0x20, 0x7F)) | {0x0A, 0x10, 0x11}
HERE = os.path.dirname(os.path.abspath(__file__))
FILES = {"B": "BOOTUP.BIN", "E": "EXODUS.BIN"}


def string_spans(d):
    """[(開始番地, 終わり番地=0 の位置)]"""
    res = []
    i = 0
    n = len(d)
    while i < n:
        if d[i] in OK:
            j = i
            while j < n and d[j] in OK:
                j += 1
            if j < n and d[j] == 0 and j - i >= 2 and any(0x41 <= c <= 0x5A or 0x61 <= c <= 0x7A for c in d[i:j]):
                res.append((i + BASE, j + BASE))
            i = j + 1
        else:
            i += 1
    return res


def inside_map(spans):
    m = {}
    for s, e in spans:
        for a in range(s, e):
            m[a] = (s, e)
    return m


def lea_si_refs(d, inside):
    """{番地: [命令の番地]}  lea si,[imm]"""
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_16)
    md.skipdata = True
    refs = {}
    for ins in md.disasm(d, BASE):
        if ins.address in inside:
            continue
        b = ins.bytes
        if len(b) == 4 and b[0] == 0x8D and b[1] == 0x36:
            v = struct.unpack_from("<H", b, 2)[0]
            if v in inside:
                refs.setdefault(v, []).append(ins.address)
    return refs


def table_runs(d, inside):
    """[(表の開始番地, [指す番地...])]  文字列の中を指す番地が2つ以上続く並び（2バイト境界は問わない）"""
    runs = []
    n = len(d)
    for parity in (0, 1):
        i = parity
        while i + 1 < n:
            j = i
            vals = []
            while j + 1 < n and (j + BASE) not in inside and struct.unpack_from("<H", d, j)[0] in inside:
                vals.append(struct.unpack_from("<H", d, j)[0])
                j += 2
            if len(vals) >= 2:
                runs.append((i + BASE, vals))
                i = j
            else:
                i += 2
    runs.sort()
    return runs


def read_tables():
    """tables.txt: 「E 18c9 33」= 表の開始番地と件数 → {tag: [(開始, 件数)]}"""
    res = {}
    p = os.path.join(HERE, "..", "translation", "tables.txt")
    for line in open(p, encoding="utf-8"):
        t = line.split("#")[0].split()
        if len(t) >= 3:
            res.setdefault(t[0], []).append((int(t[1], 16), int(t[2])))
    return res


def collect(game, tag):
    """→ dict(data, units={番地: 英文バイト列}, code={番地: [命令]}, tab={番地: [表の中の位置]}, runs, spans)"""
    d = open(os.path.join(game, FILES[tag]), "rb").read()
    spans = string_spans(d)
    inside = inside_map(spans)
    code = lea_si_refs(d, inside)
    runs = table_runs(d, inside)
    tab = {}
    tabs = read_tables().get(tag, [])
    in_table = {start + k for start, cnt in tabs for k in range(2 * cnt)}
    code = {a: v for a, v in code.items() if a not in in_table}   # 表を渡す lea si は文字列の参照ではない
    for start, cnt in tabs:
        for k in range(cnt):
            p = start + 2 * k
            v = struct.unpack_from("<H", d, p - BASE)[0]
            if v in inside:
                tab.setdefault(v, []).append(p)
    units = {}
    for a in sorted(set(code) | set(tab)):
        s, e = inside[a]
        units[a] = d[a - BASE:e - BASE]
    return dict(data=d, units=units, code=code, tab=tab, runs=runs, spans=spans, inside=inside)


def show(b):
    return (b.decode("latin-1").replace("\n", "\\n").replace("\x10", "{10}").replace("\x11", "{11}"))
