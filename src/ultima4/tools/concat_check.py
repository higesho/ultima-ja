# 本体（AVATAR）のコードから、文字列を画面に出す順番を取り出し、改行をはさまずに続けて出される部品の並び（つなぎの文）を
# 訳を当てはめた形で一覧にする（つなぎ方の確認用）
# 使い方: python concat_check.py > 出力
#   0x0B38 文字列、0x0C9F 1 文字、0x0C03 数字、0x2230 改行、0xA22D 会話の項目（文字列＋改行）を拾う
#   引数: mov ax,即値 / push ax → 文字列 A:xxxx、push word ptr [番地] → 変数、push word ptr [bx+表] → 表から引く名前
#   コードを頭から順に読むだけなので、分かれ道（if）の両方が 1 本に並ぶことがある
import os
import re
import struct
import sys

import capstone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import build_u4jp as B  # noqa: E402
from u4exe import unpack_avatar, DGROUP  # noqa: E402

TR = os.path.join(HERE, "..", "translation")
master = B.read_master(os.path.join(TR, "master_avatar.tsv"))
ja = B.read_id_translation(os.path.join(TR, "ja_avatar.tsv"), "A", master)
img = unpack_avatar(os.path.join(HERE, "..", "..", "AVATAR.EXE"))
D = img[DGROUP:]
PUTS, PUTC, NUM, NL, TALK = 0x0B38, 0x0C9F, 0x0C03, 0x2230, 0xA22D


def table_name(base):
    """表の最初の名前（表の中身を示す手がかり）"""
    for k in range(0, 8, 2):
        v = struct.unpack_from("<H", D, base + k)[0]
        if v in master:
            return master[v][2].strip()[:12]
    return f"表{base:04X}"


def desc_arg(prev):
    """call の直前の命令から、渡したものを読む"""
    if len(prev) >= 2 and prev[-1].mnemonic == "push" and prev[-1].op_str == "ax":
        m = re.match(r"ax, (0x[0-9a-f]+|\d+)$", prev[-2].op_str) if prev[-2].mnemonic == "mov" else None
        if m:
            return ("imm", int(m.group(1), 0))
    if prev and prev[-1].mnemonic == "push":
        op = prev[-1].op_str
        m = re.search(r"\[bx \+ (0x[0-9a-f]+)\]", op)
        if m:
            return ("tab", int(m.group(1), 16))
        m = re.search(r"\[(0x[0-9a-f]+)\]", op)
        if m:
            return ("var", int(m.group(1), 16))
        return ("dyn", op)
    return ("dyn", "?")


md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_16)
events = []          # (位置, 種類, 値)
prev = []
for ins in md.disasm(img[:DGROUP], 0):
    if ins.mnemonic == "call":
        try:
            t = int(ins.op_str, 16) & 0xFFFF
        except ValueError:
            t = None
        if t == PUTS or t == TALK:
            events.append((ins.address, "s", desc_arg(prev)))
            if t == TALK:
                events.append((ins.address, "nl", None))
        elif t == PUTC:
            if ins.address - 4 not in B.A_CODE_NOP:      # 組み込みで消している 1 文字は出さない
                events.append((ins.address, "c", desc_arg(prev)))
        elif t == NUM:
            events.append((ins.address, "n", None))
        elif t == NL:
            events.append((ins.address, "nl", None))
    if ins.mnemonic in ("ret", "retf") or (ins.mnemonic == "push" and ins.op_str == "bp"):
        events.append((ins.address, "end", None))
    prev = (prev + [ins])[-4:]


def show(ev, lang):
    k, v = ev[1], ev[2]
    if k == "s":
        if v[0] == "imm" and v[1] in master:
            off = v[1]
            if master[off][1] != "text":
                return "«" + master[off][2] + "»"
            return (ja.get(off, master[off][2]) if lang == "ja" else master[off][2])
        if v[0] == "tab":
            return f"〔{table_name(v[1])}…〕"
        if v[0] == "var":
            return f"〔変数{v[1]:04X}〕"
        return "〔?〕"
    if k == "c":
        return chr(v[1]) if v[0] == "imm" and 32 <= v[1] < 127 else "〔字〕"
    if k == "n":
        return "〔数〕"
    return ""


# 改行（0x2230、文字列の頭・末尾の \n）で区切った並びのうち、2 つ以上の部品からなり、訳した文字列を含むもの
run = []


def flush():
    global run
    texts = [e for e in run if e[1] in ("s", "c", "n")]
    has_tr = any(e[1] == "s" and e[2][0] == "imm" and e[2][1] in ja for e in texts)
    if len(texts) >= 2 and has_tr:
        en = "".join(show(e, "en") for e in texts).replace("\n", "⏎")
        jp = "".join(show(e, "ja") for e in texts).replace("\n", "⏎")
        ids = " ".join(f"A:{e[2][1]:04X}" for e in texts if e[1] == "s" and e[2][0] == "imm")
        print(f"{texts[0][0]:05X}  {ids}\n  英: {en}\n  訳: {jp}")
    run = []


for ev in events:
    if ev[1] in ("nl", "end"):
        flush()
        continue
    if ev[1] == "s" and ev[2][0] == "imm" and ev[2][1] in master:
        en = master[ev[2][1]][2]
        if en.startswith("\n") and run:
            flush()
        run.append(ev)
        if en.endswith("\n"):
            flush()
        continue
    run.append(ev)
flush()
