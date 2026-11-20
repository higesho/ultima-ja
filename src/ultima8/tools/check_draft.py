# -*- coding: utf-8 -*-
"""下書き（キー<TAB>訳）を、TSV に流し込む前に検査する。TSV は書き換えない。

- check.py と同じ検査（使えない字、特殊な記号の数、前後の空白、半角カナ）
- キーが TSV に無い、同じキーが二度ある、を知らせる
- 担当の TSV のうち、下書きに無い未訳の行を数える（--files に担当の TSV を並べたとき）

使い方: python -I tools/check_draft.py <下書き.txt> [--files <TSV>...]
"""
import sys, os, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from strdb import read_tsv, unesc
from check import check_row

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
UCDIR = os.path.join(ROOT, 'translation', 'usecode')


def main():
    args = sys.argv[1:]
    files = []
    if '--files' in args:
        i = args.index('--files')
        files = args[i + 1:]
        args = args[:i]
    draft = {}
    dup = []
    for p in args:
        for ln in open(p, encoding='utf-8').read().split('\n'):
            ln = ln.rstrip('\r')
            if not ln.strip() or ln.startswith('#'):
                continue
            if '\t' not in ln:
                print('タブが無い行:', ln[:60])
                continue
            k, ja = ln.split('\t', 1)
            if k in draft:
                dup.append(k)
            draft[k] = unesc(ja.strip(' '))
    en = {}
    for p in glob.glob(os.path.join(UCDIR, '*.tsv')):
        for r in read_tsv(p):
            en[r['key']] = r
    n_err = n_warn = 0
    for k, ja in draft.items():
        if k not in en:
            print('誤り %s: TSV に無いキー' % k)
            n_err += 1
            continue
        errs, warns = check_row({'en': en[k]['en'], 'ja': ja})
        for e in errs:
            print('誤り %s: %s' % (k, e))
        for w in warns:
            print('警告 %s: %s' % (k, w))
        n_err += len(errs)
        n_warn += len(warns)
    for k in dup:
        print('警告 %s: 同じキーが二度ある（後のほうを使う）' % k)
    left = 0
    for p in files:
        for r in read_tsv(p):
            if not r['ja'] and r['key'] not in draft:
                left += 1
    print('下書き %d 行、誤り %d、警告 %d%s' % (len(draft), n_err, n_warn,
          ('、担当の未訳の残り %d 行' % left) if files else ''))


main()
