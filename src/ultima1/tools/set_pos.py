# セーブデータのプレイヤー位置（と乗り物）を書き換える
# 使い方: python set_pos.py <セーブ> <x> <y> [乗り物番号]
import sys, struct
p, x, y = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
d = bytearray(open(p, 'rb').read())
struct.pack_into('<HH', d, 0x34, x, y)
if len(sys.argv) > 4: struct.pack_into('<H', d, 0x30, int(sys.argv[4]))
open(p, 'wb').write(d)
print('位置', x, y)
