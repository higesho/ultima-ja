# -*- coding: utf-8 -*-
"""どのクラスでも同じ訳にする文（アバタールの選択肢、物の呼び名、助けを呼ぶ声など）を、
すべての TSV の未訳の行に入れる。表は translation/common.tsv（列: en  ja  note）。
すでに訳がある行は変えない（違っていたら知らせる）。

使い方: python -I tools/fill_common.py
"""
import sys, os, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from strdb import read_tsv, write_tsv, unesc

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
TR = os.path.join(ROOT, 'translation')


def main():
    table = {}
    for ln in open(os.path.join(TR, 'common.tsv'), encoding='utf-8').read().split('\n')[1:]:
        p = ln.rstrip('\r').split('\t')
        if len(p) >= 2 and p[0]:
            table[unesc(p[0])] = unesc(p[1])
    filled = 0
    for path in glob.glob(os.path.join(TR, 'usecode', '*.tsv')):
        rows = read_tsv(path)
        changed = False
        for r in rows:
            key = r['en'].strip(' ')
            if key in table:
                if not r['ja']:
                    r['ja'] = table[key]
                    filled += 1
                    changed = True
                elif r['ja'] != table[key]:
                    print('共通の訳と違う: %s %s %r → %s（表は %s）' % (os.path.basename(path), r['key'], r['en'], r['ja'], table[key]))
        if changed:
            write_tsv(path, rows)
    print('共通の訳を %d 行に入れました（表 %d 件）' % (filled, len(table)))


main()
