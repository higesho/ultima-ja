# TEXT.FLX に訳を当てて、Exult のパッチフォルダ用の text.flx を作る
#   使い方: python mktext.py 元のTEXT.FLX 訳.tsv 出力text.flx
# 訳.tsv は「番号<TAB>原文<TAB>訳」（translation/text_flx.tsv）。
# 古い形「番号<TAB>訳」も読める。# で始まる行と空行、訳が空の行は読み飛ばす。
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from u7flex import read_flex, write_flex
from u7uc import unesc

def main(src, tsv, dst):
    head, ents = read_flex(src)
    n = 0
    for line in open(tsv, encoding='utf-8-sig'):
        line = line.rstrip('\r\n')
        if not line or line.startswith('#'):
            continue
        cols = line.split('\t')
        num, ja = cols[0], (cols[2] if len(cols) >= 3 else cols[1])
        if not ja:
            continue
        i = int(num, 0)
        if i >= len(ents) or not ents[i]:
            sys.exit(f'{num}: 元の文がありません')
        if len(cols) >= 3 and ents[i].rstrip(b'\0').decode('latin-1') != unesc(cols[1]):
            sys.exit(f'{num}: 原文が合いません')
        ents[i] = unesc(ja).encode('utf-8') + b'\0'
        n += 1
    write_flex(dst, head, ents)
    print(f'{dst}: {n} 件を訳しました')

if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main(*sys.argv[1:4])
