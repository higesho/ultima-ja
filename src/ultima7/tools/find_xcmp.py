# 関数をまたいで比べる語（選択肢など）を探す
#   使い方: python find_xcmp.py > translation/xcmp.txt
# 次のどちらかに当たる文字列を「関数をまたぐ語」とする。
#   1. ある関数で比べる（CMPS / CMPEQ / CMPNE）のに、その関数では比べる以外に出していない
#      （ほかの関数が選択肢に足したものや、ほかの関数から返ってきたものと比べている）
#   2. ある関数で選択肢に足す（組み込み命令 0x05 add_answer）のに、その関数では比べず、
#      ほかの関数で比べている
# こういう語は、出てくるすべての関数で同じ訳にしないと、選択肢が反応しなくなる。
import sys, os, collections
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from u7uc import read_usecode, decode, OPS, DATA_TYPES

SRC = os.path.join(HERE, '..', '..', 'STATIC', 'USECODE')
ADD_ANSWER = 0x05

def analyse(src=SRC):
    """{関数: (比べる語, 比べる以外に出す語, 選択肢に足す語)}"""
    out = {}
    for f in read_usecode(src):
        strs = dict(f.strings()); ins, _ = decode(f)
        names = [OPS[op][0] for _, op, _, _ in ins]
        compared, provided, added = set(), set(), set()
        run = []    # 続けて積んだ文字列
        for i, (p, op, args, end) in enumerate(ins):
            name = names[i]
            if name in ('UC_PUSHS', 'UC_PUSHS32'):
                s = next((strs[v] for t, v in args if t in DATA_TYPES and v in strs), None)
                nxt = names[i + 1] if i + 1 < len(ins) else ''
                if s is None:
                    continue
                if nxt in ('UC_CMPEQ', 'UC_CMPNE') or nxt.startswith('UC_CMPS'):
                    compared.add(s); run = []
                else:
                    provided.add(s); run.append(s)
                continue
            if name.startswith('UC_ARRC'):
                continue    # 配列にまとめただけ。続けて見る
            if name.startswith('UC_CALLI') and args and args[0][1] == ADD_ANSWER:
                added.update(run)
            run = []
        out[f.fid] = (compared, provided, added)
    return out

def cross_words(src=SRC):
    """{語: 関わる関数の集まり}"""
    info = analyse(src)
    cmp_in = collections.defaultdict(set)
    for fid, (c, p, a) in info.items():
        for s in c:
            cmp_in[s].add(fid)
    cross = collections.defaultdict(set)
    for fid, (c, p, a) in info.items():
        for s in c - p:                      # 1. 比べるだけ
            cross[s].add(fid)
        for s in a - c:                      # 2. 足すだけで、ほかで比べる
            others = cmp_in.get(s, set()) - {fid}
            if others:
                cross[s].add(fid); cross[s].update(others)
    return cross

if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    for s, fids in sorted(cross_words().items(), key=lambda x: x[0].lower()):
        print(f'{s.decode("latin-1")!r:32} {len(fids):3} 関数: {" ".join(f"{x:#x}" for x in sorted(fids))}')
