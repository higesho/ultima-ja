# -*- coding: utf-8 -*-
"""usecode を読んで、そのまま組み直し、元と同じになるか確かめる。
使い方: python -I test_roundtrip.py <USECODE.FLX>
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from u8uc import Usecode

path = sys.argv[1]
uc = Usecode(path)
cls = uc.classes()
strs = sum(len(c.strings()) for c in cls)
print('クラス', len(cls), '命令', sum(len(c.ins) for c in cls), '文字列', strs)
out = uc.build()
orig = open(path, 'rb').read()
if out == orig:
    print('組み直し: 元と同じ')
else:
    diff = [i for i in range(min(len(out), len(orig))) if out[i] != orig[i]]
    print('組み直し: 違う', len(out), len(orig), '最初の違い', hex(diff[0]) if diff else None)
