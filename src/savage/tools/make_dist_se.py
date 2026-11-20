# 配布物を作る
#   dist/サベージ・エンパイア日本語化パッチ/ に SAVAGE/SEJP.COM・SEJP.DAT・SEJP.PAT・SEJPMK.COM、
#   dosboxSAVAGE_single.conf、はじめにお読みください.txt を置き、
#   dist/SavageEmpire_JP.zip と dist/サベージ・エンパイア日本語化パッチ.zip（どちらも中身はゲームのフォルダと同じ並び）を作る
# 使い方: python make_dist_se.py <ゲームのフォルダ（dosboxSAVAGE_single.conf がある所）> <build フォルダ> <説明書の元（UTF-8）> <dist フォルダ>
#   起動設定は GOG 版の dosboxSAVAGE_single.conf の SAVAGE.EXE の前に SEJPMK と SEJP を足したもの
#   *.LZJ は配らない（原作の台本や絵を含むため）。遊ぶ人の所で SEJPMK.COM が作る
import os
import shutil
import sys
import zipfile

sys.stdout.reconfigure(encoding="utf-8")
game, build, readme_src, dist = sys.argv[1:5]
src = os.path.join(dist, "サベージ・エンパイア日本語化パッチ")
if os.path.isdir(src):
    shutil.rmtree(src)
os.makedirs(os.path.join(src, "SAVAGE"))

conf = open(os.path.join(game, "dosboxSAVAGE_single.conf"), "rb").read().decode("latin-1")
assert conf.count("\r\nSAVAGE.EXE\r\n") == 1 and "SEJP" not in conf
conf = conf.replace("\r\nSAVAGE.EXE\r\n", "\r\nSEJPMK\r\nSEJP\r\nSAVAGE.EXE\r\n", 1)
open(os.path.join(src, "dosboxSAVAGE_single.conf"), "wb").write(conf.encode("latin-1"))

files = {"SAVAGE/SEJP.COM": os.path.join(build, "SEJP.COM"),
         "SAVAGE/SEJP.DAT": os.path.join(build, "conv", "SEJP.DAT"),
         "SAVAGE/SEJP.PAT": os.path.join(build, "SEJP.PAT"),
         "SAVAGE/SEJPMK.COM": os.path.join(build, "SEJPMK.COM")}
for name, path in files.items():
    shutil.copyfile(path, os.path.join(src, name))

# 説明書: BOM 付き UTF-8、改行は CRLF
text = open(readme_src, encoding="utf-8").read().replace("\r\n", "\n").rstrip("\n")
open(os.path.join(src, "はじめにお読みください.txt"), "wb").write(
    b"\xef\xbb\xbf" + text.replace("\n", "\r\n").encode("utf-8"))

names = list(files) + ["dosboxSAVAGE_single.conf", "はじめにお読みください.txt"]
for zname in ["SavageEmpire_JP.zip", "サベージ・エンパイア日本語化パッチ.zip"]:
    zpath = os.path.join(dist, zname)
    tmp = zpath + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        for n in names:
            zf.write(os.path.join(src, n), n)
    os.replace(tmp, zpath)
    print("作成:", zpath, os.path.getsize(zpath), "バイト、", len(names), "ファイル")
