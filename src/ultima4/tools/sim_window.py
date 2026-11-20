# 本編の会話欄（桁 24〜39 の 16 マス）での表示を、文字で再現する（画面で行けない場面の確認用）
# 使い方: python sim_window.py <開始の位置(16進)> <終わりの位置(16進)>
#   その範囲の AVATAR の訳を、組み立てと同じ自動改行を入れてから、本体の 0x0B38（空白で単語を区切って折り返す）
#   と 0x0C9F（40 桁を越えたら改行）の規則で並べる。1 つの文字列ごとに、行の頭から書き始めたものとして見せる
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import build_u4jp as B  # noqa: E402

TR = os.path.join(HERE, "..", "translation")
master = B.read_master(os.path.join(TR, "master_avatar.tsv"))
ja = B.read_id_translation(os.path.join(TR, "ja_avatar.tsv"), "A", master)
enc = B.Encoder(list(ja.values()))


def render(text):
    """会話欄に書いたときの行（1 マス 1 文字。組は 2 マス）"""
    body = text.rstrip("\x12\x08")
    text = B.wrap(enc, body)
    lines, cur = [], ""
    col = 24
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\n":
            lines.append(cur)
            cur, col = "", 24
            i += 1
            continue
        if ch != " " and (i == 0 or text[i - 1] in " \n"):
            j = i
            while j < len(text) and text[j] not in " \n":
                j += 1
            if col + B.cells(enc, text[i:j]) > 40 and col != 24:
                lines.append(cur)
                cur, col = "", 24
        if col > 39:
            lines.append(cur)
            cur, col = "", 24
        cur += ch
        col += 1
        i += 1
    lines.append(cur)
    return lines


a, b = int(sys.argv[1], 16), int(sys.argv[2], 16)
for off in sorted(o for o in ja if a <= o < b):
    n, k, en = master[off]
    print(f"---- A:{off:04X}  {en[:60]!r}")
    for ln in render(ja[off]):
        print("  |" + ln.ljust(16, "　" if False else " ") + "|")
