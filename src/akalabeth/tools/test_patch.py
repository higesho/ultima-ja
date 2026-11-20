"""試験用: 組み立てた AK.EXE の「町に入る」を「城に入る」に差し替える（配布物には使わない）。"""
import sys, os, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wdx, coff
src, dst = sys.argv[1:3]
exe = open(src, 'rb').read()
c = coff.Coff(wdx.unpack_exe(exe))
at = 0x1b05
o = c.va2off(at)
assert c.d[o] == 0xe8 and at + 5 + struct.unpack_from('<i', c.d, o + 1)[0] == 0x56b8
struct.pack_into('<i', c.d, o + 1, 0x64cc - (at + 5))
open(dst, 'wb').write(wdx.pack_exe(exe, bytes(c.d)))
print('ok')
