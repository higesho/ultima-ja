import sys, struct
for fn in sys.argv[1:]:
    d = open(fn,'rb').read()
    sig, lastp, pages, nrel, hdrpar, minalloc, maxalloc, ss, sp, csum, ip, cs, reloff, ovl = struct.unpack_from('<2s13H', d, 0)
    hdr = hdrpar*16
    size = (pages-1)*512 + (lastp or 512)
    print(f"{fn}: filesize={len(d)} imgsize={size} hdr={hdr} nrel={nrel} reloff={reloff:#x} CS:IP={cs:04x}:{ip:04x} SS:SP={ss:04x}:{sp:04x} min={minalloc} max={maxalloc}")
    if len(d) > size: print("   overlay/extra bytes:", len(d)-size)
