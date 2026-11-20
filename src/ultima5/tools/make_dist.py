# 配布物を作る
#   dist/ウルティマ5日本語化パッチ/ に U5JP.COM、U5JP.DAT、U5JPMK.COM、dosboxULTIMA5_single.conf、
#   はじめにお読みください.txt を置き、dist/Ultima5_JP.zip と dist/ウルティマ5日本語化パッチ.zip（どちらもフォルダなし）を作る
# 使い方: python make_dist.py <ゲームのフォルダ> <build フォルダ> <説明書の元（UTF-8）> <dist フォルダ>
#   起動設定は GOG 版の dosboxULTIMA5_single.conf の ULTIMA.EXE の前に U5JPMK と U5JP を足したもの
#   （Steam 版も同じ DOSBox.exe が同じ 2 つの conf を読む。single の conf は GOG 版と Steam 版で同じ）
#   TLJ/DAJ は配らない（原作の台本の命令や英語の言葉を含むため）。遊ぶ人の所で U5JPMK.COM が作る
import os
import shutil
import sys
import zipfile

sys.stdout.reconfigure(encoding="utf-8")
game, build, readme_src, dist = sys.argv[1:5]
src = os.path.join(dist, "ウルティマ5日本語化パッチ")
if os.path.isdir(src):
    shutil.rmtree(src)
os.makedirs(src)

conf = open(os.path.join(game, "dosboxULTIMA5_single.conf"), "rb").read().decode("latin-1")
assert conf.count("\r\nULTIMA.EXE\r\n") == 1 and "U5JP" not in conf
conf = conf.replace("\r\nULTIMA.EXE\r\n", "\r\nU5JPMK\r\nU5JP\r\nULTIMA.EXE\r\n", 1)
open(os.path.join(src, "dosboxULTIMA5_single.conf"), "wb").write(conf.encode("latin-1"))

names = ["U5JP.COM", "U5JP.DAT", "U5JPMK.COM"]
for n in names:
    shutil.copyfile(os.path.join(build, n), os.path.join(src, n))

# 説明書: BOM 付き UTF-8、改行は CRLF
text = open(readme_src, encoding="utf-8").read().replace("\r\n", "\n").rstrip("\n")
open(os.path.join(src, "はじめにお読みください.txt"), "wb").write(
    b"\xef\xbb\xbf" + text.replace("\n", "\r\n").encode("utf-8"))

files = names + ["dosboxULTIMA5_single.conf", "はじめにお読みください.txt"]
for zname in ["Ultima5_JP.zip", "ウルティマ5日本語化パッチ.zip"]:
    zpath = os.path.join(dist, zname)
    tmp = zpath + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        for n in files:
            zf.write(os.path.join(src, n), n)
    os.replace(tmp, zpath)
    print("作成:", zpath, os.path.getsize(zpath), "バイト、", len(files), "ファイル")
