# 配布物を作る
#   dist/ウルティマ6日本語化パッチ/ に U6JP.COM、U6JP.DAT、U6JPMK.COM、U6JPMK.DAT、LOOK.JZD、dosboxULTIMA6_single.conf、
#   はじめにお読みください.txt を置き、dist/Ultima6_JP.zip と dist/ウルティマ6日本語化パッチ.zip（どちらもフォルダなし）を作る
# 使い方: python make_dist.py <ゲームのフォルダ> <build フォルダ> <説明書の元（UTF-8）> <dist フォルダ>
#   build フォルダには U6JP.COM、U6JPMK.COM、U6JPMK.DAT と、conv/U6JP.DAT、conv/LOOK.JZD があること
#   起動設定は GOG 版の dosboxULTIMA6_single.conf の ULTIMA6.EXE の前に U6JPMK と U6JP を足したもの
#   （Steam 版も同じ DOSBox.exe が同じ 2 つの conf を読む。single の conf は GOG 版と Steam 版で同じ）
#   CONVERSE.JA/JB と BOOK.JDT は配らない（原作の会話のスクリプトや、ルーン文字の部分の英語を含むため）。遊ぶ人の所で U6JPMK.COM が作る
import os
import shutil
import sys
import zipfile

sys.stdout.reconfigure(encoding="utf-8")
game, build, readme_src, dist = sys.argv[1:5]
src = os.path.join(dist, "ウルティマ6日本語化パッチ")
if os.path.isdir(src):
    shutil.rmtree(src)
os.makedirs(src)

conf = open(os.path.join(game, "dosboxULTIMA6_single.conf"), "rb").read().decode("latin-1")
assert conf.count("\r\nULTIMA6.EXE\r\n") == 1 and "U6JP" not in conf
conf = conf.replace("\r\nULTIMA6.EXE\r\n", "\r\nU6JPMK\r\nU6JP\r\nULTIMA6.EXE\r\n", 1)
open(os.path.join(src, "dosboxULTIMA6_single.conf"), "wb").write(conf.encode("latin-1"))

names = {"U6JP.COM": "U6JP.COM", "U6JP.DAT": "conv/U6JP.DAT", "U6JPMK.COM": "U6JPMK.COM",
         "U6JPMK.DAT": "U6JPMK.DAT", "LOOK.JZD": "conv/LOOK.JZD"}
for n, f in names.items():
    shutil.copyfile(os.path.join(build, f), os.path.join(src, n))

# 説明書: BOM 付き UTF-8、改行は CRLF
text = open(readme_src, encoding="utf-8").read().replace("\r\n", "\n").rstrip("\n")
open(os.path.join(src, "はじめにお読みください.txt"), "wb").write(
    b"\xef\xbb\xbf" + text.replace("\n", "\r\n").encode("utf-8"))

files = list(names) + ["dosboxULTIMA6_single.conf", "はじめにお読みください.txt"]
for zname in ["Ultima6_JP.zip", "ウルティマ6日本語化パッチ.zip"]:
    zpath = os.path.join(dist, zname)
    tmp = zpath + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        for n in files:
            zf.write(os.path.join(src, n), n)
    os.replace(tmp, zpath)
    print("作成:", zpath, os.path.getsize(zpath), "バイト、", len(files), "ファイル")
