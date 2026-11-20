#!/bin/sh
# 試験用のフォルダ game_test に組み立てた物を入れる（元のファイルはそのまま、日本語は *.LZJ）
cd "$(dirname "$0")"
for f in TALK LOOK MDTEXT SCENETXT MIDGAME1 MIDGAME2 MIDGAME3 MIDGAME4 MIDGAME5 MIDGAME6 MIDGAME7 MIDGAME8 MIDGAME9 MIDGAMEA MIDGAMEB MIDGAMEC MIDGAMED; do
  cp ../MARTIAN/$f.LZC game_test/$f.LZC
  cp build/conv/$f.LZC game_test/$f.LZJ
done
cp build/conv/MDJP.DAT build/MDJP.COM game_test/
