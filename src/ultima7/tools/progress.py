# 組ごとの進み具合（translation/batches.tsv の組）
#   使い方: python progress.py [組の番号 ...]
# 組ごとに、訳し終えたバイト数／全体、訳し漏れの行数、check_tr.py の問題の数を出す。
import sys, os, subprocess
sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
TR = os.path.join(HERE, '..', 'translation')

def stat(fid):
    total = done = left = 0
    for line in open(os.path.join(TR, 'usecode', f'{fid}.tsv'), encoding='utf-8'):
        if line.startswith('#'):
            continue
        c = line.rstrip('\n').split('\t')
        b = len(c[1].encode('latin-1', 'replace'))
        if not c[1].strip():
            continue
        total += b
        if len(c) > 2 and c[2]:
            done += b
        else:
            left += 1
    return total, done, left

def main(sel):
    rows = []
    for line in open(os.path.join(TR, 'batches.tsv'), encoding='utf-8'):
        if line.startswith('#'):
            continue
        no, fids, _ = line.rstrip('\n').split('\t')
        if sel and no not in sel:
            continue
        rows.append((no, fids.split()))
    gt = gd = 0
    for no, fids in rows:
        t = d = l = 0
        for f in fids:
            a, b, c = stat(f); t += a; d += b; l += c
        gt += t; gd += d
        probs = ''
        if d:
            r = subprocess.run([sys.executable, '-I', os.path.join(HERE, 'check_tr.py'), *fids], capture_output=True, text=True, encoding='utf-8')
            n = sum(1 for x in r.stdout.splitlines() if x.startswith('    '))
            probs = f'  確認の問題 {n}'
        print(f'組{no}: {d:6}/{t:6} B（{100 * d // max(t, 1):3}%）  未訳の行 {l:4}{probs}')
    print(f'合計: {gd}/{gt} B（{100 * gd // max(gt, 1)}%）')

if __name__ == '__main__':
    main(sys.argv[1:])
