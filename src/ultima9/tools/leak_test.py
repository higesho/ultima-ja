# -*- coding: utf-8 -*-
"""操作を繰り返して、前後のメモリと確保の集計を比べる。
使い方: python leak_test.py <名前> <回数> <操作>...
  操作の書き方: キー名を + でつなぐと同時押し、@秒 で待つ。例: j @1.5 esc @1
  キー名: 1文字のキー、up/down/left/right/esc/enter/space/tab/shift/ctrl/alt
結果: ../test/<名前>_0.txt / _1.txt（確保の集計）と、画面に増減の要約
"""
import sys, os, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from u9_ctl import *

name, count, ops = sys.argv[1], int(sys.argv[2]), sys.argv[3:]
st = json.load(open(STATE)); pid = st['pid']
out = os.path.join(TEST, name)


def run_ops():
    for op in ops:
        if op.startswith('@'):
            time.sleep(float(op[1:]))
        else:
            probe_hold(pid, op.split('+'), 0.12)
            time.sleep(0.15)


probe_dump(pid, out + '_0.txt'); m0 = measure(pid); s0 = probe_stat(pid)
t0 = time.time()
for i in range(count):
    run_ops()
    if (i + 1) % max(1, count // 5) == 0:
        print('  %d回目' % (i + 1), measure(pid))
time.sleep(3)
probe_dump(pid, out + '_1.txt'); m1 = measure(pid); s1 = probe_stat(pid)
grab(find_window(pid), out + '.png')
print('所要 %.0f 秒' % (time.time() - t0))
print('記録上の確保: %+d 件, %+.1f MB' % (s1['live_count'] - s0['live_count'], s1['live_mb'] - s0['live_mb']))
print('プロセス: 私用 %+.1f MB, 確保済み %+.1f MB, 番地空間 %+.1f MB' % (
    m1['private'] - m0['private'], m1['commit'] - m0['commit'], m1['used_va'] - m0['used_va']))
