# In-place string patcher (prototype): writes Shift-JIS text over the original strings.
# The new text must fit in the original byte length; the rest is filled with NUL.
# usage: python patch_strings.py <game_dir> <out_dir> <patch.tsv>
#   patch.tsv (UTF-8): FILE<TAB>ds_off(hex)<TAB>english<TAB>japanese   ('#' lines ignored, \n allowed)
import sys, os, shutil, struct, glob

DS = {'ULTIMA.EXE': 0x3ed, 'OUT.EXE': 0xd48, 'SPACE.EXE': 0x72d, 'MONDAIN.EXE': 0x597, 'GEN.EXE': 0x426}
src, dst, tsv = sys.argv[1:4]
os.makedirs(dst, exist_ok=True)
for pat in ('*.EXE', '*.BIN', 'CASTLE.*'):
    for f in glob.glob(os.path.join(src, pat)):
        if os.path.basename(f).lower() == 'unins000.exe': continue
        shutil.copy2(f, dst)

files = {}
ok = ng = 0
for ln, line in enumerate(open(tsv, encoding='utf-8-sig'), 1):
    line = line.rstrip('\r\n')
    if not line or line.startswith('#'): continue
    fn, off, en, ja = line.split('\t')
    en = en.replace('\\n', '\n'); ja = ja.replace('\\n', '\n')
    if fn not in files: files[fn] = bytearray(open(os.path.join(dst, fn), 'rb').read())
    d = files[fn]
    hdr = struct.unpack_from('<H', d, 8)[0] * 16
    p = hdr + DS[fn] * 16 + int(off, 16)
    orig = en.encode('latin1')
    if d[p:p + len(orig) + 1] != orig + b'\0':
        print(f'line {ln}: original text mismatch at {fn}:{off}: {bytes(d[p:p+len(orig)])!r}'); ng += 1; continue
    new = ja.encode('cp932')
    if len(new) > len(orig):
        print(f'line {ln}: too long ({len(new)} > {len(orig)}): {ja}'); ng += 1; continue
    d[p:p + len(orig)] = new + b'\0' * (len(orig) - len(new))
    ok += 1
for fn, d in files.items():
    open(os.path.join(dst, fn), 'wb').write(d)
print(f'patched {ok} strings, {ng} errors')
