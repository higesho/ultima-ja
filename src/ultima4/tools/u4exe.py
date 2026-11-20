# AVATAR.EXE（EXEPACK で圧縮）を展開する
#   EXEPACK のヘッダはイメージ内 0x17720（"RB" の 16 バイト前）。展開後のイメージを返す
#   本体のデータ（DGROUP）はイメージ内 0xF0D0 から（起動時に DS=0x0F0D）
import struct

DGROUP = 0xF0D0


def unpack_avatar(path):
    d = open(path, "rb").read()
    hdr = struct.unpack_from("<H", d, 8)[0] * 16
    img = d[hdr:]
    hp = img.find(b"RB") - 16
    rip, rcs, _, esz, rsp, rss, dlen, skip = struct.unpack_from("<8H", img, hp)
    src = img[:hp - (skip - 1) * 16]
    dst = bytearray(dlen * 16)
    dst[:len(src)] = src
    si = len(src) - 1
    while src[si] == 0xFF:
        si -= 1
    di = len(dst) - 1
    while True:
        cmd = src[si]
        cnt = src[si - 1] << 8 | src[si - 2]
        si -= 3
        if cmd & 0xFE == 0xB0:
            b = src[si]
            si -= 1
            dst[di - cnt + 1:di + 1] = bytes([b]) * cnt
            di -= cnt
        elif cmd & 0xFE == 0xB2:
            dst[di - cnt + 1:di + 1] = src[si - cnt + 1:si + 1]
            di -= cnt
            si -= cnt
        else:
            raise ValueError(f"EXEPACK の命令が不正です: {cmd:02x}")
        if cmd & 1:
            break
    return bytes(dst)


if __name__ == "__main__":
    import sys
    open(sys.argv[2], "wb").write(unpack_avatar(sys.argv[1]))
