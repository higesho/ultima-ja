# -*- coding: utf-8 -*-
"""英語版から訳す文を書き出す（訳の TSV を作る・更新する）。

- usecode: クラスごとに translation/usecode/<番号>_<名前>.tsv。クラスの中で同じ英文は1行にまとめる。
  行の順は、コードの中で最初に出てくる順（会話の流れにほぼ沿う）
- 字幕: translation/intro.tsv（EINTRO.SKF）
- すでにある TSV の訳とメモは、キーと英文が同じなら残す

使い方: python -I tools/extract.py
"""
import sys, os, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from u8uc import Usecode
from u8shape import read_flex
from strdb import read_tsv, write_tsv, en_from_bytes

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
GAME = os.path.normpath(os.path.join(ROOT, '..', 'ENGLISH'))
TR = os.path.join(ROOT, 'translation')
UCDIR = os.path.join(TR, 'usecode')

# 字幕の項目（EINTRO.SKF）
SKF_SUBS = [336, 340, 344, 348, 350]


def class_name(uc, cid):
    names = uc.entries[1]
    return names[4 + 13 * cid:4 + 13 * cid + 13].split(b'\0')[0].decode('latin1')


def merge(path, rows):
    """既存の訳を引き継いで書く。英文が変わった行は訳を消してメモに残す。"""
    old = {}
    if os.path.exists(path):
        for r in read_tsv(path):
            old[r['key']] = r
    n_keep = 0
    for r in rows:
        o = old.get(r['key'])
        if o:
            if o['en'] == r['en']:
                r['ja'], r['note'] = o['ja'], o['note']
                n_keep += o['ja'] != ''
            elif o['ja']:
                r['note'] = ('英文が変わった。前の訳: ' + o['ja'] + ' / ' + o['note']).strip(' /')
    write_tsv(path, rows)
    return n_keep


def main():
    os.makedirs(UCDIR, exist_ok=True)
    uc = Usecode(os.path.join(GAME, 'USECODE', 'EUSECODE.FLX'))
    files = rows_total = kept = 0
    for c in uc.classes():
        seen = []
        for s in c.strings():
            t = en_from_bytes(s.text)
            if not t.strip():
                continue
            if t not in seen:
                seen.append(t)
        if not seen:
            continue
        name = class_name(uc, c.classid)
        path = os.path.join(UCDIR, '%04X_%s.tsv' % (c.classid, name))
        rows = [{'key': '%04X:%03d' % (c.classid, i), 'en': t, 'ja': '', 'note': ''}
                for i, t in enumerate(seen)]
        kept += merge(path, rows)
        files += 1
        rows_total += len(rows)
    # 字幕
    ents = read_flex(open(os.path.join(GAME, 'STATIC', 'EINTRO.SKF'), 'rb').read())
    rows = [{'key': 'SKF:%d' % k, 'en': en_from_bytes(ents[k][6:-1]), 'ja': '', 'note': ''} for k in SKF_SUBS]
    kept += merge(os.path.join(TR, 'intro.tsv'), rows)
    print('usecode: %d ファイル、%d 行。字幕 %d 行。引き継いだ訳 %d' % (files, rows_total, len(rows), kept))


main()
