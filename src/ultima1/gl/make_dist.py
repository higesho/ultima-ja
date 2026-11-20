# I・II の配布物を作り直す（窓の表示と東雲フォントの DLL を足す）
#   それぞれの dist/ウルティマN日本語化パッチ/ にある COM と起動設定（公開済みのもの）を元にして、
#   起動設定に [sdl] と [render] を足し、DOSBOX/opengl32.dll と DOSBOX/ultima_ja.ini を加え、
#   説明書は release/readme.txt から作る。zip は2つの名前で作る（中身は同じ）。
# 使い方: python make_dist.py
import os
import shutil
import sys
import zipfile

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
DLL = os.path.join(HERE, "out", "opengl32.dll")
INI = os.path.join(HERE, "ultima_ja.ini")
README = "はじめにお読みください.txt"

VIEW = ("[sdl]\r\nfullscreen=false\r\nwindowresolution=960x720\r\noutput=opengl\r\n\r\n"
        "[render]\r\naspect=false\r\nscaler=none\r\n\r\n")


def make(n, com, zname, extra=()):
    jp = os.path.join(ROOT, f"Ultima {n}", "jp_work")
    dist = os.path.join(jp, "dist")
    src = os.path.join(dist, f"ウルティマ{n}日本語化パッチ")
    confname = f"dosboxULTIMA{n}_single.conf"

    # 起動設定: [autoexec] の前に、窓で起動して opengl で描く設定を足す（もう足してあれば何もしない）
    conf = open(os.path.join(src, confname), "rb").read().decode("latin-1")
    if "[sdl]" not in conf:
        assert conf.count("[autoexec]") == 1
        conf = conf.replace("[autoexec]", VIEW + "[autoexec]", 1)
        open(os.path.join(src, confname), "wb").write(conf.encode("latin-1"))

    os.makedirs(os.path.join(src, "DOSBOX"), exist_ok=True)
    shutil.copyfile(DLL, os.path.join(src, "DOSBOX", "opengl32.dll"))
    shutil.copyfile(INI, os.path.join(src, "DOSBOX", "ultima_ja.ini"))

    # 説明書: BOM 付き UTF-8、改行は CRLF
    text = open(os.path.join(jp, "release", "readme.txt"), encoding="utf-8").read()
    text = text.replace("\r\n", "\n").rstrip("\n")
    open(os.path.join(src, README), "wb").write(b"\xef\xbb\xbf" + text.replace("\n", "\r\n").encode("utf-8"))

    for x in extra:
        shutil.copyfile(os.path.join(jp, "build", x), os.path.join(src, x))
    names = [com, *extra, confname, "DOSBOX/opengl32.dll", "DOSBOX/ultima_ja.ini", README]
    for z in (zname, f"ウルティマ{n}日本語化パッチ.zip"):
        zpath = os.path.join(dist, z)
        tmp = zpath + ".tmp"
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
            for name in names:
                zf.write(os.path.join(src, *name.split("/")), name)
        os.replace(tmp, zpath)
        print("作成:", zpath, os.path.getsize(zpath), "バイト")


if __name__ == "__main__":
    # 引数 1 / 2 で片方だけ作る（なしで両方）
    which = sys.argv[1:] or ["1", "2"]
    if "1" in which: make(1, "U1JP.COM", "Ultima1_JP.zip", ("NIJ.BIN",))
    if "2" in which: make(2, "U2JP.COM", "Ultima2_JP.zip")
