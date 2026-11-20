"""全員の文章と文字列の表を、長さを変えた別の中身に置き換えて書き戻し、読み直して構造が同じか確かめる"""
import sys, os, random
sys.path.insert(0, os.path.dirname(__file__))
from u6conv import Script, load_items, build, node_bytes
def shape(s):
    """部品の並びと、参照が何番目の部品を指すか（位置の値は除く）"""
    idx = {nd[1]: i for i, nd in enumerate(s.nodes)}
    refs = []
    for at, tgt, kind in s.refs:
        holder = max(i for i, nd in enumerate(s.nodes) if nd[1] <= at)
        refs.append((holder, at - s.nodes[holder][1], idx[tgt], kind))
    code = []
    for nd in s.nodes:
        if nd[0] == 'code':
            b = bytearray(nd[2])
            for h, off, _, _ in refs:
                if s.nodes[h] is nd:
                    b[off:off + 4] = b'\0\0\0\0'
            code.append(bytes(b))
    return [nd[0] for nd in s.nodes], code, sorted(refs)
def mutate(s, rnd):
    new = {}
    for i, nd in enumerate(s.nodes):
        if nd[0] == 'text' and any(0x41 <= c <= 0x7a for c in nd[2]):
            n = max(1, int(len(nd[2]) * rnd.uniform(0.3, 1.6)))
            body = bytes(rnd.choice(b'abcdefgh ') for _ in range(n))
            body = bytes(rnd.choice(range(0x80, 0x9c)) if rnd.random() < .3 else c for c in body)
            # 元の先頭と末尾の改行は残す（飛び先の切れ目を変えない）
            lead = len(nd[2]) - len(nd[2].lstrip(b'\n')); tail = len(nd[2]) - len(nd[2].rstrip(b'\n'))
            new[i] = nd[2][:lead] + body.strip(b'\n') + (nd[2][len(nd[2]) - tail:] if tail else b'')
        elif nd[0] == 'table':
            new[i] = [bytes(rnd.choice(b'xyz') for _ in range(rnd.randint(1, 12))) for _ in nd[2]]
    return new
if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    rnd = random.Random(1); ok = bad = 0; grew = []
    for f in ('CONVERSE.A', 'CONVERSE.B'):
        for k, raw in load_items(os.path.join(sys.argv[1], f)):
            if raw is None: continue
            s = Script(raw)
            out = build(s, mutate(s, rnd))
            t = Script(out)
            if shape(s) == shape(t): ok += 1
            else: bad += 1; print('構造が違う', f, k)
            grew.append(len(out) - len(raw))
    print('構造が同じ', ok, '違う', bad, '長さの変化', min(grew), '〜', max(grew))
