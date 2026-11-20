# ゲーム画面（30マス）の文字列で、1行が30マスを超えるものを探す（符号化したあとのバイト数で数える）
# 使い方: python check_width.py <ja.txt> <U2JP_enc.json>
import importlib.util, json, os, sys
sys.stdout.reconfigure(encoding="utf-8")
here = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("b", os.path.join(here, "build_u2jp.py")); b = importlib.util.module_from_spec(spec); spec.loader.exec_module(b)
tr = b.read_translation(sys.argv[1])
enc = {t: bytes.fromhex(h) for t, h in json.load(open(sys.argv[2], encoding="utf-8"))["encoded"].items()}
WIDE = {0x003d8, 0x00406, 0x00452, 0x00485, 0x004cf, 0x004fe, 0x0053f, 0x00572, 0x005bc, 0x005ec, 0x0063a, 0x0066c, 0x072a9, 0x07352}
n = 0
for k, t in tr.items():
    if isinstance(k, int) and (k in b.TEXT_KEYS or k in WIDE or b.TABLES[0][0] <= k < b.TABLES[0][1]):
        continue
    for line in enc[t].split(b"\r"):
        if len(line) > 30:
            n += 1
            print(k if isinstance(k, str) else f"{k:05x}", len(line), t.replace("\r", "|"))
print("30マスを超える行:", n)
