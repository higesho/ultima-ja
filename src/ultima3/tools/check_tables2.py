# 番地の表の候補ごとに、表の番地（即値でも添字付きでも）を使う命令を一覧にする
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
    use = {}
    for ins in md.disasm(d, 0x100):
        if ins.mnemonic == ".byte" or ins.address in inside:
            continue
        for op in ins.operands:
            v = None
            if op.type == capstone.x86.X86_OP_MEM:
                v = op.mem.disp & 0xFFFF
            elif op.type == capstone.x86.X86_OP_IMM and ins.mnemonic in ("mov", "lea", "push", "add", "cmp"):
                v = op.imm & 0xFFFF
            if v is not None:
                use.setdefault(v, []).append(f"{ins.address:04x} {ins.mnemonic} {ins.op_str}")
    for start, vals in r["runs"]:
        heads = sum(1 for v in vals if inside[v][0] == v)
        if heads < 2:
            continue
        hit = []
        for k in range(-4, 2 * len(vals) + 1):
            for x in use.get((start + k) & 0xFFFF, []):
                hit.append(f"[{k:+d}] {x}")
        txt = " / ".join(u3data.show(d[v - 0x100:inside[v][1] - 0x100])[:10] for v in vals[:3])
        print(f"{tag} {start:04x} n={len(vals)} heads={heads} ({txt}): " + " | ".join(hit[:5]))
