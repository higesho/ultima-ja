# usecode の命令表（exult/tools/ucxt/data/u7opcodes.data）から、
# 日本語化の差し替え処理（exult/usecode/ucinternal.cc）が使う C++ の表を作る
#   使い方: python mkopheader.py   → exult/usecode/ja_opcodes.h
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from u7uc import OPS

KIND = {'byte': 1, 'short': 2, 'flag': 2, 'varoffset': 2, 'extoffset': 2, 'long': 3,
        'dataoffset': 4, 'dataoffset32': 5, 'offset': 6, 'offset32': 7}

def main():
    out = os.path.join(HERE, '..', 'exult', 'usecode', 'ja_opcodes.h')
    lines = ['// 日本語化: usecode の命令ごとの引数の種類（tools/mkopheader.py が u7opcodes.data から作る）',
             '// 0 = 無し / 1 = 1 バイト / 2 = 2 バイト / 3 = 4 バイト /',
             '// 4 = 文字列の位置（2 バイト）/ 5 = 文字列の位置（4 バイト）/ 6 = 飛び幅（2 バイト、符号つき）/ 7 = 飛び幅（4 バイト、符号つき）',
             '// ja_op_known[op] が 0 の命令は知らない命令。',
             '#ifndef JA_OPCODES_H', '#define JA_OPCODES_H', '',
             'static const unsigned char ja_op_known[256] = {']
    known = [1 if op in OPS else 0 for op in range(256)]
    for i in range(0, 256, 32):
        lines.append('\t' + ', '.join(str(x) for x in known[i:i + 32]) + ',')
    lines += ['};', '', 'static const unsigned char ja_op_args[256][6] = {']
    for op in range(256):
        kinds = [KIND[t] for t in OPS[op][1]] if op in OPS else []
        if len(kinds) > 6:
            sys.exit(f'{op:#x}: 引数が多すぎます')
        kinds += [0] * (6 - len(kinds))
        name = OPS[op][0] if op in OPS else '-'
        lines.append(f'\t{{{", ".join(map(str, kinds))}}},    // {op:#04x} {name}')
    lines += ['};', '', '#endif', '']
    open(out, 'w', encoding='utf-8', newline='\n').write('\n'.join(lines))
    print(f'{out} を作りました')

if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
