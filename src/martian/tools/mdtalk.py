"""Martian Dreams の会話 TALK.LZC を読む・書く。
束の形は mdfmt.py: 先頭4バイト=ファイル全体の大きさ、4バイトの項目表（下位24ビット=位置、上位8ビット=印）。
TALK.LZC の項目はどれも圧縮なし（印 0xE0）。印 0xFF の項目は次の項目と同じ位置を指す（空きの番号）。
0 番はスクリプトではない（作った人の残したバッチファイル）。
本編は項目の大きさが 0x36B0（14,000 バイト）以上だとエラーにする（0E1A:1718）。"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mdfmt import entries  # noqa: E402

TALK_MAX = 0x36B0


def load_items(path):
    """[(番号, スクリプト or None)]。スクリプトでない項目（0 番、印 0xFF）は None"""
    t, es = entries(open(path, 'rb').read())
    out = []
    for k, (o, f, r) in enumerate(es):
        if r is not None and f == 0xE0 and r[:1] == b'\xff':
            out.append((k, r))
        else:
            out.append((k, None))
    return out


def save_talk(src, dst, new):
    """src の TALK.LZC の項目を new（{番号: 新しいスクリプト}）で置き換えて dst に書く。
    印 0xFF の項目は、元と同じく「元で同じ位置を指していた項目」の新しい位置を指す"""
    d = open(src, 'rb').read()
    t, es = entries(d)
    n = len(es)
    head = 4 + 4 * n
    body = bytearray()
    newpos = {}          # 元の位置 → 新しい位置（印 0xE0 の項目だけ）
    for k, (o, f, r) in enumerate(es):
        if f != 0xE0 or r is None:
            continue
        data = new.get(k, r)
        if k in new and len(data) >= TALK_MAX:
            raise ValueError(f"#{k}: スクリプトが {TALK_MAX} バイト以上: {len(data)}")
        newpos[o] = head + len(body)
        body += data
    table = bytearray()
    for k, (o, f, r) in enumerate(es):
        if o == 0:
            table += struct.pack('<I', f << 24)
            continue
        if o not in newpos:
            raise ValueError(f"#{k}: 位置 {o:#x} を指す本体の項目がない")
        table += struct.pack('<I', newpos[o] | (f << 24))
    out = struct.pack('<I', head + len(body)) + bytes(table) + bytes(body)
    open(dst, 'wb').write(out)
    return len(out)


if __name__ == '__main__':
    # 何も変えずに書き戻して元と一致するか
    src = sys.argv[1]
    tmp = sys.argv[2]
    save_talk(src, tmp, {})
    print('一致' if open(src, 'rb').read() == open(tmp, 'rb').read() else '不一致')
