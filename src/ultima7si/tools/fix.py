# 訳ファイル（translation\usecode\XXXX.tsv）をまとめて直す
#   python fix.py
# 直すこと（下の表を書きかえて使う）:
#   KEEP_EN: 原文のまま残す関数（看板の暗号文字など）
#   UNIFY:   (関数, 原文, 訳) 同じ関数の中の同じ原文を、この訳にそろえる（選択肢）
#   REPLACE: 訳の中の文字の置きかえ（フォントにない字など）
#   原文が空白だけの行は、訳も原文と同じ空白にする
import sys, os, re
here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
from si_uc import unesc, esc
sys.stdout.reconfigure(encoding='utf-8')
U = os.path.join(here, '..', 'translation', 'usecode')

KEEP_EN = {'017b', '0334', '02c5'}
UNIFY = [
    ('0494', 'Spoke of me?', 'わたしのことを話していた？'),
    ('041b', 'cheated', '騙された'),
    ('04d1', 'arrival', '到着'),
    ('061b', 'help', '手助け'),
]
REPLACE = [('冒瀆', '冒とく'), ('瀆', 'とく')]

changed = 0
for name in sorted(os.listdir(U)):
    m = re.fullmatch(r'([0-9a-f]{4})\.tsv', name)
    if not m:
        continue
    fid = m.group(1)
    path = os.path.join(U, name)
    lines = open(path, encoding='utf-8').read().split('\n')
    out = []; n = 0
    for line in lines:
        if not line or line.startswith('#'):
            out.append(line); continue
        c = line.split('\t')
        while len(c) < 3:
            c.append('')
        en = unesc(c[1]); ja = unesc(c[2])
        new = ja
        if fid in KEEP_EN:
            new = en
        else:
            for f, e, j in UNIFY:
                if f == fid and en == e:
                    new = j
            for a, b in REPLACE:
                new = new.replace(a, b)
            if en.strip() == '' and en != '' and new != en:
                new = en
        if new != ja:
            c[2] = esc(new.encode('latin-1', 'replace')) if False else new.replace('\\', '\\\\').replace('\t', '\\t').replace('\n', '\\n').replace('\r', '\\r')
            n += 1
        out.append('\t'.join(c[:3]))
    if n:
        open(path, 'w', encoding='utf-8', newline='\n').write('\n'.join(out))
        print(f'{fid}: {n} 行を直した')
        changed += n
print(f'合計 {changed} 行')
