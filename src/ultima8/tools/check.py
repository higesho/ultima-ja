# -*- coding: utf-8 -*-
"""訳の TSV を検査する。

誤り（直さないと組み立てられない）:
  - 16番フォントに無い字（JIS 第1水準の外、2区の記号など）
警告（たいてい直すべき）:
  - 特殊な記号の数が英文と違う: ~（改行） *（改ページ） %（タブ） ^（空白）
  - 訳の前後に空白がある（英文の前後の空白は自動で付くので二重になる）
  - 半角カナ
参考（report に書くだけ）:
  - 同じ英文なのに、クラスによって訳が違う（会話の選択肢などは同じ訳にそろえる）

使い方: python -I tools/check.py [TSV...]    （省略すると全部）
結果の詳細は test/check_report.txt に書く。
"""
import sys, os, glob, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from strdb import read_tsv
from jpenc import bad_chars

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
TR = os.path.join(ROOT, 'translation')
SPECIAL = ['~', '*', '%', '^']


def check_row(r):
    errs, warns = [], []
    ja = r['ja']
    if not ja or ja == '{空}':
        return errs, warns
    bad = bad_chars(ja.replace('\t', ''))
    if bad:
        errs.append('使えない字: ' + ''.join(sorted(set(bad))))
    for ch in SPECIAL:
        if r['en'].count(ch) != ja.count(ch):
            warns.append('記号 %s の数が違う（英 %d、訳 %d）' % (ch, r['en'].count(ch), ja.count(ch)))
    if ja != ja.strip(' '):
        warns.append('訳の前後に空白がある')
    if any(0xFF61 <= ord(c) <= 0xFF9F for c in ja):
        warns.append('半角カナがある')
    return errs, warns


def main():
    files = sys.argv[1:] or sorted(glob.glob(os.path.join(TR, 'usecode', '*.tsv'))) + [os.path.join(TR, 'intro.tsv')]
    n_err = n_warn = total = done = 0
    by_en = collections.defaultdict(set)
    lines = []
    for p in files:
        for r in read_tsv(p):
            total += 1
            if r['ja']:
                done += 1
                by_en[r['en'].strip()].add(r['ja'])
            errs, warns = check_row(r)
            for e in errs:
                lines.append('誤り %s %s: %s' % (os.path.basename(p), r['key'], e))
            for w in warns:
                lines.append('警告 %s %s: %s' % (os.path.basename(p), r['key'], w))
            n_err += len(errs)
            n_warn += len(warns)
    diff = {en: ja for en, ja in by_en.items() if len(ja) > 1}
    for en, ja in sorted(diff.items()):
        lines.append('参考 訳が分かれている: %r → %s' % (en, ' / '.join(sorted(ja))))
    os.makedirs(os.path.join(ROOT, 'test'), exist_ok=True)
    with open(os.path.join(ROOT, 'test', 'check_report.txt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    for ln in lines:
        if not ln.startswith('参考'):
            print(ln)
    print('訳した行 %d / %d（%.1f%%）、誤り %d、警告 %d、訳が分かれている英文 %d'
          % (done, total, 100.0 * done / max(total, 1), n_err, n_warn, len(diff)))
    return 1 if n_err else 0


if __name__ == '__main__':
    sys.exit(main())
