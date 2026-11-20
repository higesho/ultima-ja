"""人物ごとの訳（translation/conv_ja/*.tsv）を確かめて1つにまとめる。
使い方: python tools/collect_ja.py
  - 全員を check_ja で確かめ、問題・注意の数を人物ごとに出す（詳しくは build/check/<番号>.txt）
  - 問題のない人物の訳を translation/conv_ja_all.tsv にまとめる（問題のある人物は入れない）
"""
import io
import os
import sys
import contextlib

sys.path.insert(0, os.path.dirname(__file__))
import check_ja  # noqa: E402

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    en_dir = os.path.join(HERE, 'translation', 'conv_en')
    ja_dir = os.path.join(HERE, 'translation', 'conv_ja')
    out_dir = os.path.join(HERE, 'build', 'check')
    os.makedirs(out_dir, exist_ok=True)
    ok, bad, missing = [], [], []
    lines = []
    for fn in sorted(os.listdir(en_dir)):
        pid = fn[:-4]
        jp = os.path.join(ja_dir, fn)
        if not os.path.exists(jp):
            missing.append(pid)
            continue
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            try:
                rc = check_ja.main(os.path.join(en_dir, fn), jp)
            except SystemExit as e:
                print("問題:", e)
                rc = 1
        text = buf.getvalue()
        open(os.path.join(out_dir, pid + '.txt'), 'w', encoding='utf-8').write(text)
        ne = text.count('問題:')
        nw = text.count('注意:')
        if rc:
            bad.append((pid, ne, nw))
        else:
            ok.append((pid, nw))
            for line in open(jp, encoding='utf-8'):
                if line.strip() and not line.startswith('#'):
                    lines.append(line.rstrip('\n') + '\n')
    open(os.path.join(HERE, 'translation', 'conv_ja_all.tsv'), 'w', encoding='utf-8', newline='\n').writelines(lines)
    print(f"問題なし {len(ok)} 人（注意あり {sum(1 for _, w in ok if w)} 人）、問題あり {len(bad)} 人、訳なし {len(missing)} 人")
    for pid, ne, nw in bad:
        print(f"  問題あり {pid}: 問題 {ne}、注意 {nw}（build/check/{pid}.txt）")
    if missing:
        print("  訳なし:", ' '.join(missing))
    print(f"translation/conv_ja_all.tsv: {len(lines)} 行")


if __name__ == '__main__':
    main()
