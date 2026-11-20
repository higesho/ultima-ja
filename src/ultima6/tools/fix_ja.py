"""集めた会話の訳をそろえる（translation/conv_ja/*.tsv を書き換える）
  1. 序数の表（英語 st/nd/rd/th）の訳を「番目」にそろえる
  2. 英語の部分がまったく同じキーワードの行どうしで、足したかなの語をそろえる（別の場面で同じ一覧を使うとき）
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from conv_text import unesc, esc
HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
ORD = {'st', 'nd', 'rd', 'th'}

def rows(path):
    out = []
    for line in open(path, encoding='utf-8'):
        if line.startswith('#') or '\t' not in line:
            out.append((None, line)); continue
        k, v = line.rstrip('\n').split('\t', 1)
        out.append((k, v))
    return out

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    n_ord = n_kw = 0
    for fn in sorted(os.listdir(os.path.join(HERE, 'translation', 'conv_ja'))):
        en = {k: v for k, v in rows(os.path.join(HERE, 'translation', 'conv_en', fn)) if k}
        jp = os.path.join(HERE, 'translation', 'conv_ja', fn)
        rs = rows(jp)
        # キーワードの行: 英語の部分 → かなの和集合（現れた順）
        union = {}
        for k, v in rs:
            if k and ':k' in k and k in en:
                eng = en[k]
                kana = [x.strip() for x in v.split(',')][len(eng.split(',')):]
                lst = union.setdefault(eng, [])
                for x in kana:
                    if x and x not in lst: lst.append(x)
        new = []
        for k, v in rs:
            if k and ':s' in k and en.get(k, '').strip() in ORD and v != '番目':
                v = '番目'; n_ord += 1
            if k and ':k' in k and k in en:
                eng = en[k]
                w = ','.join(eng.split(',') + union.get(eng, []))
                if w != v: n_kw += 1
                v = w
            new.append(f"{k}\t{v}\n" if k else v)
        open(jp, 'w', encoding='utf-8', newline='\n').writelines(new)
    print(f"序数の表を直した行 {n_ord}、キーワードの行をそろえた行 {n_kw}")

if __name__ == '__main__':
    main()
