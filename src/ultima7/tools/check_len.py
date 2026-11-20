# 訳が短すぎる行（要約や訳し落としの疑い）を探す
#   使い方: python check_len.py --batch 02 04 …   または   python check_len.py XXXX …
# 原文が 120 バイト以上で、訳（UTF-8）のバイト数が原文の 0.8 倍より少ない行を挙げる。
# 日本語は英語のおよそ 1.2〜1.5 倍のバイト数になるのがふつう。
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
TR = os.path.join(HERE, '..', 'translation')

def fids_of(args):
    if args and args[0] == '--batch':
        out = []
        for line in open(os.path.join(TR, 'batches.tsv'), encoding='utf-8'):
            c = line.rstrip('\n').split('\t')
            if not line.startswith('#') and c[0] in args[1:]:
                out += c[1].split()
        return out
    return args

def main(args):
    n = 0; tot_en = tot_ja = 0
    for fid in fids_of(args):
        for line in open(os.path.join(TR, 'usecode', f'{fid}.tsv'), encoding='utf-8'):
            c = line.rstrip('\n').split('\t')
            if line.startswith('#') or len(c) < 3 or not c[2]:
                continue
            en = len(c[1].encode('latin-1', 'replace')); ja = len(c[2].encode('utf-8'))
            tot_en += en; tot_ja += ja
            if en >= 120 and ja < en * 0.8:
                print(f'{fid} {c[0]}: 原文 {en}B → 訳 {ja}B（{ja / en:.2f}）: {c[2][:50]}')
                n += 1
    print(f'短すぎる疑い: {n} 行。全体の比 {tot_ja / max(tot_en, 1):.2f}')

if __name__ == '__main__':
    main(sys.argv[1:])
