"""会話以外の英文を書き出す（翻訳用）。
  translation/other_en/book.tsv   本・看板など（BOOK.DAT、128件）  番号 book:000
  translation/other_en/look.tsv   物の名前（LOOK.LZD）             番号 look:0001（タイルの番号、16進）
  translation/other_en/game.tsv   本編 GAME.EXE のデータの文字列   番号 game:0a8c（データの中の位置）
  translation/other_en/u.tsv      タイトル・導入・キャラクター作成 U.EXE  番号 u:1234（イメージの中の位置）
  translation/other_en/end.tsv    エンディング END.EXE             番号 end:1234
使い方: python extract_other.py <ゲームのフォルダ> <出力のフォルダ>
"""
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(__file__))
from u6fmt import lib, lzw  # noqa: E402
from unexepack import unpack  # noqa: E402
from conv_text import esc  # noqa: E402

DGROUP = 0x2D85
SKIP = re.compile(rb'(?i)(\.(cga|ega|hrc|tga|vga|shp|drv|m|bmp|lzd|ptr|exe|dat|u6|ch|set|pal|lbm|int|bin)$'
                  rb'|^savegame|^lzobjblk|^lzdngblk|^objblk|^objlist|^tileflag|^basetile|^chunks$|^map$|^schedule$'
                  rb'|^portrait|^converse|^config|^u6pal|^tileindx|^maptiles|^objtiles|^masktype|^animdata|^dither'
                  rb'|^Turbo-C|^Null pointer|^Divide error|^Abnormal program|^\(null\)|^print scanf|^Floating point'
                  rb'|^MS Run-Time)')


def strings_in(img, lo, hi, min_letters=2):
    """lo〜hi の中の、0 で終わる表示用らしい文字列: [(位置, bytes)]"""
    out = []
    for m in re.finditer(rb'[\x20-\x7e\n]{2,}(?=\0)', img[lo:hi]):
        s = m.group()
        p = lo + m.start()
        if p > 0 and img[p - 1] not in (0,) and not (0x80 <= img[p - 1]):
            # 前が 0 でない（別の文字列の後半）ものは、前が表示できない値のときだけ取る
            if 0x20 <= img[p - 1] <= 0x7e or img[p - 1] == 0x0a:
                continue
        if len(re.findall(rb'[A-Za-z]', s)) < min_letters or SKIP.search(s.strip()):
            continue
        if not re.search(rb'[a-z]{3}|[A-Z][a-z]{2}|[A-Z]{4}', s):   # コードの一部が文字に見えたもの（DD-A など）を外す
            continue
        out.append((p, s))
    return out


def write(path, head, rows):
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(head)
        for key, b in rows:
            f.write(f"{key}\t{esc(b)}\n")
    print(f"{path}: {len(rows)} 件")


def main(gamedir, outdir):
    os.makedirs(outdir, exist_ok=True)
    # 本
    items = lib(open(os.path.join(gamedir, 'BOOK.DAT'), 'rb').read(), 2)
    write(os.path.join(outdir, 'book.tsv'),
          "# 本・看板・墓碑など（BOOK.DAT）。<…> の中はルーン文字で表示されるので訳さずそのまま残す\n",
          [(f"book:{i:03d}", it.rstrip(b'\0')) for i, it in enumerate(items) if it and it.rstrip(b'\0')])
    # 物の名前
    raw, _ = lzw(open(os.path.join(gamedir, 'LOOK.LZD'), 'rb').read())
    rows = []
    p = 0
    while p + 2 < len(raw):
        tile = struct.unpack_from('<H', raw, p)[0]
        p += 2
        e = raw.find(b'\0', p)
        if e < 0:
            break
        if re.search(rb'[A-Za-z]{2}', raw[p:e]):
            rows.append((f"look:{tile:04x}", raw[p:e]))
        p = e + 1
    write(os.path.join(outdir, 'look.tsv'),
          "# 物の名前（LOOK.LZD）。\\s や \\es は英語の複数形の語尾（日本語では消す）。冠詞（a/an/the）はゲームが付ける\n", rows)
    # 本編
    img, _, _ = unpack(os.path.join(gamedir, 'GAME.EXE'))
    ds = DGROUP * 16
    rows = [(f"game:{p - ds:04x}", s) for p, s in strings_in(img, ds, len(img))]
    # DGROUP の手前のデータの区画（セグメント 0x2D32。戦闘や状態の表示などの文字列）
    seg2 = 0x2D32 * 16
    rows2 = [(f"gam2:{p - seg2:04x}", s) for p, s in strings_in(img, seg2, ds)]
    write(os.path.join(outdir, 'gam2.tsv'),
          "# 本編 GAME.EXE の文字列（その2: 戦闘・状態など）。訳は元の英語の字数以内（全角も半角も1字）。"
          "%s %d などはそのまま残す\n# 行頭の ` は「次の字を大文字に」の印（消してよい）\n", rows2)
    write(os.path.join(outdir, 'game.tsv'),
          "# 本編 GAME.EXE の文字列。訳は元の英語の字数以内（全角も半角も1字）。%s %d などはそのまま残す\n", rows)
    # タイトル・導入・エンディング（圧縮なし）
    for name, tag in (('U.EXE', 'u'), ('END.EXE', 'end')):
        d = open(os.path.join(gamedir, name), 'rb').read()
        hdr = struct.unpack_from('<H', d, 8)[0] * 16
        im = d[hdr:]
        rows = [(f"{tag}:{p:05x}", s) for p, s in strings_in(im, 0, len(im), min_letters=3)]
        write(os.path.join(outdir, f'{tag}.tsv'),
              f"# {name} の文字列。訳は元の英語の字数以内（全角も半角も1字）。%c %P %F などはそのまま残す\n", rows)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main(sys.argv[1], sys.argv[2])
