"""GAME.EXE の文字列を探す: python strs.py EXE 正規表現 [DGROUP(16進)]"""
import re, sys, struct
d = open(sys.argv[1], 'rb').read()
hs = struct.unpack('<H', d[8:10])[0] * 16
DG = int(sys.argv[3], 16) * 16 if len(sys.argv) > 3 else 0x2fab0
for m in re.finditer(sys.argv[2].encode(), d, re.I):
    a = m.start()
    print(hex(a), 'img', hex(a - hs), 'ds', hex(a - hs - DG), d[a:a + 24])
