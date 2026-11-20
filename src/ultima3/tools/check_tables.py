# 番地の表の候補ごとに、添字付きで読む命令（[bx+表] など）があるか調べる
import sys
import capstone
import u3data

sys.stdout.reconfigure(encoding="utf-8")
for tag in ("B", "E"):
    r = u3data.collect(sys.argv[1], tag)
    d, inside = r["data"], r["inside"]
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_16)
    md.detail = True
    md.skipdata = True
    disp = {}
    for ins in md.disasm(d, 0x100):
        if ins.mnemonic == ".byte" or ins.address in inside:
            continue
        for op in ins.operands:
            if op.type == capstone.x86.X86_OP_MEM and (op.mem.base or op.mem.index):
                disp.setdefault(op.mem.disp & 0xFFFF, []).append(f"{ins.address:04x} {ins.mnemonic} {ins.op_str}")
    for start, vals in r["runs"]:
        heads = sum(1 for v in vals if inside[v][0] == v)
        hit = []
        for k in range(-4, 2 * len(vals)):
            for x in disp.get((start + k) & 0xFFFF, []):
                hit.append(f"[{k:+d}] {x}")
        if hit:
            print(f"{tag} {start:04x} n={len(vals)} heads={heads}: " + " | ".join(hit[:4]))
