# -*- coding: utf-8 -*-
"""長さの違う文に差し替えても位置が正しく直るかを、別の言語版で確かめる。
英語版の文を他の言語版の文に置き換えて組み直し、本物の他言語版とクラスごとに比べる。
（文字列以外の命令が同じクラスだけを置き換える）
使い方: python -I test_relocate.py <英語版.FLX> <他言語版.FLX>
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from u8uc import Usecode, CODE_BASE


def shape(c):
    """文字列と位置の値を除いた命令の並び。"""
    return [i.op if i.op == 0x0D or i.rel_target() is not None or i.op in (0x11, 0x57, 0x58)
            else i.raw for i in c.ins]


en = Usecode(sys.argv[1])
fr = Usecode(sys.argv[2])
same = changed = skipped = 0
for c in en.classes():
    f = fr.by_classid(c.classid)
    if f is None or shape(c) != shape(f):
        skipped += 1
        continue
    for a, b in zip(c.strings(), f.strings()):
        a.text = b.text
    same += 1
out = en.build()

# 組み直した結果をクラスごとに比べる
tmp = os.path.join(os.environ.get('TEMP', '.'), 'u8_reloc_test.flx')
open(tmp, 'wb').write(out)
re_ = Usecode(tmp)
ok = ng = 0
bad = []
for c in re_.classes():
    f = fr.by_classid(c.classid)
    e = en.by_classid(c.classid)
    if f is None or shape(e) != shape(f):
        continue
    import struct
    o1, s1 = struct.unpack_from('<II', re_.raw, 0x80 + c.index * 8)
    o2, s2 = struct.unpack_from('<II', fr.raw, 0x80 + c.index * 8)
    if re_.raw[o1:o1 + s1] == fr.raw[o2:o2 + s2]:
        ok += 1
    else:
        ng += 1
        bad.append(c.classid)
print('置き換えたクラス', same, '置き換えなかったクラス', skipped)
print('本物と同じ', ok, '違う', ng, ['%04X' % x for x in bad[:20]])
