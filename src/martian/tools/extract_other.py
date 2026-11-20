"""Martian Dreams の会話以外の英文を書き出す（翻訳用）。
  translation/other_en/game.tsv   本編 GAME.EXE のデータの文字列   番号 game:2bc14（ロードイメージの中の位置、16進）
  translation/other_en/look.tsv   物の名前（LOOK.LZC）             番号 look:0001（タイルの番号、16進）
使い方: python extract_other.py <ゲームのフォルダ> <出力のフォルダ>
本編の文字列は far データ（0x2BB4〜）と DGROUP（0x2FAB）にある。どちらも置き換えの対象（build_mdjp.py の DATA_SEGS）
"""
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mdfmt import entries  # noqa: E402
from conv_text import esc  # noqa: E402

EXE_HDR, FBOV = 0x3400, 0x422B0
FARDATA, DGROUP, DG_SIZE = 0x2BB4, 0x2FAB, 0xF378
SKIP = re.compile(rb'(?i)(\.(cga|ega|vga|drv|lzc|ptr|pal|tim|exe|dat|bak|tmp)$'
                  rb'|^savegame|^lzobjblk|^lzdngblk|^objblk|^objlist|^tileflag|^basetile|^chunks$|^map$|^schedule$'
                  rb'|^mdpal|^config|^tileindx|^maptiles|^objtiles|^masktype|^animdata|^MThd|^MTrk|^EMM'
                  rb'|^Turbo|^Borland|^Null pointer|^Divide error|^Abnormal program|^\(null\)|^print scanf|^Floating point'
                  rb'|^Stack overflow)')


def strings_in(img, lo, hi, min_letters=2):
    """lo〜hi の中の、0 で終わる表示用らしい文字列: [(位置, bytes)]"""
    out = []
    for m in re.finditer(rb'[\x20-\x7e\n]{2,}(?=\0)', img[lo:hi]):
        s = m.group()
        p = lo + m.start()
        if p > 0 and img[p - 1] != 0 and (0x20 <= img[p - 1] <= 0x7e or img[p - 1] == 0x0a):
            continue
        if len(re.findall(rb'[A-Za-z]', s)) < min_letters or SKIP.search(s.strip()):
            continue
        if not re.search(rb'[a-z]{3}|[A-Z][a-z]{2}|[A-Z]{4}', s):   # コードや表の一部が文字に見えたものを外す
            continue
        out.append((p, s))
    return out


def write(path, head, rows):
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(head)
        for key, b in rows:
            f.write(f"{key}\t{esc(b)}\n")
    print(f"{path}: {len(rows)} 件")


def look_entries(gamedir):
    """LOOK.LZC: [(タイル, 名前 bytes)]、末尾の残り"""
    t, es = entries(open(os.path.join(gamedir, 'LOOK.LZC'), 'rb').read())
    raw = es[0][2]
    out = []
    p = 0
    while p + 2 < len(raw):
        e = raw.find(b'\0', p + 2)
        if e < 0:
            break
        out.append((struct.unpack_from('<H', raw, p)[0], raw[p + 2:e]))
        p = e + 1
    return out, raw[p:]


def main(gamedir, outdir):
    os.makedirs(outdir, exist_ok=True)
    ents, _ = look_entries(gamedir)
    rows = [(f"look:{tile:04x}", n) for tile, n in ents if re.search(rb'[A-Za-z]{2}', n)]
    write(os.path.join(outdir, 'look.tsv'),
          "# 物の名前（LOOK.LZC）。\\s や \\es は英語の複数形の語尾（日本語では消す）。冠詞（a/an/the）はゲームが付ける\n", rows)
    exe = open(os.path.join(gamedir, 'GAME.EXE'), 'rb').read()
    img = exe[EXE_HDR:FBOV]
    rows = [(f"game:{p:05x}", s) for p, s in strings_in(img, FARDATA * 16, DGROUP * 16 + DG_SIZE)]
    write(os.path.join(outdir, 'game.tsv'),
          "# 本編 GAME.EXE の文字列。訳は元の英語のバイト数以内（日本語は1字1〜2バイト）。%s %d などはそのまま残す\n"
          "# 行頭の ` は「次の字を大文字に」の印（日本語では消してよい）\n", rows)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main(sys.argv[1], sys.argv[2])
