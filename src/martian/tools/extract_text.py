"""本（MDTEXT.LZC）・途中の場面（MIDGAME*.LZC）・導入とエンディング（SCENETXT.LZC）の英文を書き出す。
使い方: python extract_text.py <ゲームのフォルダ> <出力フォルダ translation/other_en>
  mdtext.tsv   番号 mdtext:NN（本1冊）。文の \\r\\n は \\n と書く
  midgame.tsv  番号 midgameX:NN（場面のファイル X の項目 NN）。中身が *END* や bogus! の項目は書かない
  scenetxt.tsv 番号 scene:N:LL（項目 N の LL 行目。行は \\r\\n で分かれる。行の数は変えられない）
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mdfmt  # noqa: E402

MIDGAMES = "123456789ABCD"


def esc(s):
    return s.replace("\\", "\\\\").replace("\r\n", "\\n").replace("\n", "\\n").replace("\t", "\\t")


def items(path):
    total, es = mdfmt.entries(open(path, "rb").read())
    return [mdfmt.item(*e) if e[1] != 0xFF else None for e in es], es


def scene_lines(x):
    """SCENETXT の項目を行に分ける: [(行の文字列)]。先頭が \\r\\n のときは最初の行が空"""
    return x.decode("latin1").split("\r\n")


def main(game, outdir):
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "mdtext.tsv"), "w", encoding="utf-8", newline="\n") as f:
        f.write("# 本・手紙（MDTEXT.LZC）。1行 = 1冊。\\n は改行、* だけの行はページの区切り（キー待ち）\n")
        its, _ = items(os.path.join(game, "MDTEXT.LZC"))
        for k, x in enumerate(its):
            if x:
                f.write(f"mdtext:{k:02d}\t{esc(x.rstrip(bytes([0])).decode('latin1'))}\n")
    with open(os.path.join(outdir, "midgame.tsv"), "w", encoding="utf-8", newline="\n") as f:
        f.write("# 本編の途中の場面の文（MIDGAME*.LZC）。1行 = 絵の下に出る文1つ\n")
        for c in MIDGAMES:
            its, es = items(os.path.join(game, f"MIDGAME{c}.LZC"))
            for k, x in enumerate(its):
                if x is None or es[k][1] != 0xE0:
                    continue
                s = x.rstrip(bytes([0])).decode("latin1")
                if s in ("*END*", "bogus!"):
                    continue
                f.write(f"midgame{c}:{k:02d}\t{esc(s)}\n")
    with open(os.path.join(outdir, "scenetxt.tsv"), "w", encoding="utf-8", newline="\n") as f:
        f.write("# 導入・キャラクター作成・エンディング・スタッフの字幕（SCENETXT.LZC）。1行 = 画面に出る字幕1つ。^ は字幕の中の改行\n")
        its, _ = items(os.path.join(game, "SCENETXT.LZC"))
        for k, x in enumerate(its):
            for j, line in enumerate(scene_lines(x)):
                if any(ch.isalpha() for ch in line):
                    f.write(f"scene:{k}:{j:02d}\t{esc(line)}\n")
    print("書き出しました:", outdir)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
