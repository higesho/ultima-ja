# 本体（AVATAR / TITLE）の文字列が、コードのどこでどの関数に渡されているかを調べる（調査用）
# 使い方: python strrefs.py avatar|title  → 標準出力に「位置  参照の種類  関数  英文」
import sys, re, struct
import capstone
sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
from u4exe import unpack_avatar, DGROUP

sys.stdout.reconfigure(encoding="utf-8")
which = sys.argv[1]
if which == "avatar":
    img = unpack_avatar("../AVATAR.EXE"); DS = DGROUP
else:
    t = open("../TITLE.EXE", "rb").read(); img = t[struct.unpack_from("<H", t, 8)[0] * 16:]; DS = 0x3FD0
D = img[DS:]
strs = {}
for m in re.finditer(rb"[\x20-\x7e\n]{2,}\x00", D):
    strs[m.start()] = m.group()[:-1].decode()
# 文字列の途中を指す参照も拾えるように、全部の文字の位置 → 先頭
owner = {}
for off, s in strs.items():
    for i in range(len(s) + 1):
        owner[off + i] = off
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_16)
refs = {}            # 文字列の先頭 → [(コードの位置, 参照先, 次の call 先)]
insns = list(md.disasm(img[:DS], 0))
for k, ins in enumerate(insns):
    for m in re.finditer(r"0x([0-9a-f]{2,4})\b", ins.op_str):
        v = int(m.group(1), 16)
        if v in owner and ins.mnemonic in ("mov", "push", "lea", "cmp", "add"):
            callee = None
            for j in range(k + 1, min(k + 12, len(insns))):
                if insns[j].mnemonic == "call":
                    callee = insns[j].op_str
                    try:
                        callee = hex(int(callee, 16) & 0xFFFF)
                    except ValueError:
                        pass
                    break
            refs.setdefault(owner[v], []).append((ins.address, v, callee, ins.mnemonic))
# データの中の表（2バイトの番地）
tabrefs = {}
for i in range(0, len(D) - 1, 1):
    v = struct.unpack_from("<H", D, i)[0]
    if v in strs and i not in owner:
        tabrefs.setdefault(v, []).append(i)
for off, s in strs.items():
    r = refs.get(off, [])
    kinds = sorted({c for _, _, c, _ in r if c})
    mid = sorted({hex(v - off) for _, v, _, _ in r if v != off})
    tb = tabrefs.get(off, [])
    print(f"{off:04x}\t{','.join(kinds) or '-'}\t{'表' + ','.join(hex(x) for x in tb[:3]) if tb else ''}\t{'途中' + ','.join(mid) if mid else ''}\t{s!r}")
