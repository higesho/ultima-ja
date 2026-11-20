# 文の断片のあいだに何がはさまるかを調べる
#   使い方: python splice.py XXXX [XXXX ...]
# 命令を追って、文字列の断片（ADDSI / PUSHS）と、その間に足される変数を並べる。
# 変数に入っている値が、どの関数から返ってきたかも示す（0x908 = プレイヤーの名前、0x909 = milord/milady など）。
# 結果は「位置: 断片」のあとに [変数←0x909] のように出る。
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding='utf-8')
from u7uc import read_usecode, decode, OPS, DATA_TYPES
import struct

SRC = os.path.join(HERE, '..', '..', 'STATIC', 'USECODE')
KNOWN = {0x908: '名前', 0x909: '呼びかけ(milord/milady)'}

def run(fid, funcs):
    f = funcs[fid]; strs = dict(f.strings()); ins, _ = decode(f)
    ext = struct.unpack_from(f'<{(f.code_off - 6) // 2}H', f.rest, 6)
    origin = {}    # 変数番号 → 値を返した関数
    last_call = None
    for i, (p, op, args, end) in enumerate(ins):
        name = OPS[op][0]
        if name.startswith('UC_CALL') and not name.startswith('UC_CALLI') and args and args[0][0] == 'extoffset':
            last_call = ext[args[0][1]]
            continue
        if name == 'UC_POP' and last_call is not None:
            origin[args[0][1]] = last_call
        if name.startswith('UC_ADDSV') or (name == 'UC_PUSH' and i + 1 < len(ins) and OPS[ins[i + 1][1]][0] == 'UC_ADD'):
            v = args[0][1]
            src = origin.get(v)
            tag = KNOWN.get(src, f'{src:#x}' if src is not None else '?')
            # 直前と直後の断片
            prev = next((strs.get(a[1]) for q in reversed(ins[:i]) for a in q[2] if a[0] in DATA_TYPES), None)
            nxt = next((strs.get(a[1]) for q in ins[i + 1:] for a in q[2] if a[0] in DATA_TYPES), None)
            if src in KNOWN:
                pv = (prev or b'').decode('latin-1')[-40:]
                nv = (nxt or b'').decode('latin-1')[:40]
                print(f'{fid:#06x} {p:#06x}: …{pv!r} ＋[{tag}]＋ {nv!r}…')
        if not name.startswith('UC_CALL'):
            last_call = None

if __name__ == '__main__':
    funcs = {f.fid: f for f in read_usecode(SRC)}
    for a in sys.argv[1:]:
        run(int(a, 16), funcs)
