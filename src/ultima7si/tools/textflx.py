# TEXT.FLX を「番号<TAB>原文」の一覧に書き出す
#   使い方: python textflx.py TEXT.FLX 出力.tsv
import struct, sys
src, dst = sys.argv[1], sys.argv[2]
d = open(src, 'rb').read()
cnt = struct.unpack_from('<I', d, 0x54)[0]
with open(dst, 'w', encoding='utf-8', newline='\n') as w:
    w.write('# 番号\t原文\t訳\n')
    for i in range(cnt):
        off, size = struct.unpack_from('<II', d, 0x80 + i * 8)
        if not size:
            continue
        t = d[off:off + size].rstrip(bytes(1)).decode('latin-1')
        w.write(f'{i}\t{t}\t\n')
print('ok', cnt)
