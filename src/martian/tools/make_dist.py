# 配布物を作る
#   dist/マーシャン・ドリームズ日本語化パッチ/ に MARTIAN/MDJP.COM・MDJP.DAT・MDJP.PAT・MDJPMK.COM、
#   dosboxMARTIAN_single.conf、はじめにお読みください.txt を置き、
#   dist/MartianDreams_JP.zip（中身はゲームのフォルダと同じ並び）を作る
# 使い方: python make_dist.py <ゲームのフォルダ（dosboxMARTIAN_single.conf がある所）> <build フォルダ> <説明書の元（UTF-8）> <dist フォルダ>
#   起動設定は GOG 版の dosboxMARTIAN_single.conf の MARTIAN.EXE の前に MDJPMK と MDJP を足したもの
#   *.LZJ は配らない（原作の台本や絵を含むため）。遊ぶ人の所で MDJPMK.COM が作る
import os
import shutil
import sys
import zipfile

sys.stdout.reconfigure(encoding="utf-8")
game, build, readme_src, dist = sys.argv[1:5]
src = os.path.join(dist, "マーシャン・ドリームズ日本語化パッチ")
if os.path.isdir(src):
    shutil.rmtree(src)
os.makedirs(os.path.join(src, "MARTIAN"))

conf = open(os.path.join(game, "dosboxMARTIAN_single.conf"), "rb").read().decode("latin-1")
assert conf.count("\r\nMARTIAN.EXE\r\n") == 1 and "MDJP" not in conf
conf = conf.replace("\r\nMARTIAN.EXE\r\n", "\r\nMDJPMK\r\nMDJP\r\nMARTIAN.EXE\r\n", 1)
open(os.path.join(src, "dosboxMARTIAN_single.conf"), "wb").write(conf.encode("latin-1"))

files = {"MARTIAN/MDJP.COM": os.path.join(build, "MDJP.COM"),
         "MARTIAN/MDJP.DAT": os.path.join(build, "conv", "MDJP.DAT"),
         "MARTIAN/MDJP.PAT": os.path.join(build, "MDJP.PAT"),
         "MARTIAN/MDJPMK.COM": os.path.join(build, "MDJPMK.COM")}
for name, path in files.items():
    shutil.copyfile(path, os.path.join(src, name))

# 説明書: BOM 付き UTF-8、改行は CRLF
text = open(readme_src, encoding="utf-8").read().replace("\r\n", "\n").rstrip("\n")
open(os.path.join(src, "はじめにお読みください.txt"), "wb").write(
    b"\xef\xbb\xbf" + text.replace("\n", "\r\n").encode("utf-8"))

names = list(files) + ["dosboxMARTIAN_single.conf", "はじめにお読みください.txt"]
zpath = os.path.join(dist, "MartianDreams_JP.zip")
tmp = zpath + ".tmp"
with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
    for n in names:
        zf.write(os.path.join(src, n), n)
os.replace(tmp, zpath)
print("作成:", zpath, os.path.getsize(zpath), "バイト、", len(names), "ファイル")
