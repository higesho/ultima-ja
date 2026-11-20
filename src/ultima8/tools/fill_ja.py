# -*- coding: utf-8 -*-
"""下書きの訳を TSV の ja 列に流し込む。

下書きの形（UTF-8 のテキスト）: 1 行に「キー<TAB>訳」。# で始まる行と空行は読み飛ばす。
訳の中の改行・タブは \\n \\t と書く（TSV と同じ）。
キーのクラス番号から TSV を探して書き込む（複数のクラスが混ざっていてもよい）。

使い方: python -I tools/fill_ja.py <下書き.txt>...
"""
import sys, os, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from strdb import read_tsv, write_tsv, unesc

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
UCDIR = os.path.join(ROOT, 'translation', 'usecode')


def main():
    todo = {}
    for p in sys.argv[1:]:
        for ln in open(p, encoding='utf-8').read().split('\n'):
            ln = ln.rstrip('\r')
            if not ln.strip() or ln.startswith('#'):
                continue
            if '\t' not in ln:
                sys.exit('タブが無い行: %s' % ln)
            key, ja = ln.split('\t', 1)
            todo.setdefault(key.split(':')[0], {})[key] = unesc(ja.strip(' '))
    total = 0
    for cls, items in todo.items():
        if cls == 'SKF':
            path = os.path.join(ROOT, 'translation', 'intro.tsv')
        else:
            m = glob.glob(os.path.join(UCDIR, cls + '_*.tsv'))
            if not m:
                sys.exit('クラス %s の TSV が無い' % cls)
            path = m[0]
        rows = read_tsv(path)
        keys = {r['key'] for r in rows}
        bad = [k for k in items if k not in keys]
        if bad:
            sys.exit('%s に無いキー: %s' % (os.path.basename(path), ' '.join(bad[:10])))
        for r in rows:
            if r['key'] in items:
                r['ja'] = items[r['key']]
        write_tsv(path, rows)
        total += len(items)
        print('%s: %d 行' % (os.path.basename(path), len(items)))
    print('合計 %d 行を書き込みました' % total)


main()
