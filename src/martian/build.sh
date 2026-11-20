#!/bin/sh
# 組み立て: 会話の訳をまとめ、常駐部 build/MDJP.COM・表 build/conv/MDJP.DAT・日本語の LZC（build/conv）、
# 配布用のパッチ build/MDJP.PAT と組み立て役 build/MDJPMK.COM を作る
cd "$(dirname "$0")"
python -X utf8 tools/collect_ja.py | tail -2
rm -rf build/conv && mkdir -p build/conv
MDJP_GAMETSV="translation/other_ja/game.tsv;translation/other_ja/game_extra.tsv" MDJP_LOOKTSV=translation/other_ja/look.tsv \
MDJP_CONVTEST="translation/conv_ja_all.tsv;translation/other_ja/names.tsv" MDJP_BOOKTSV=translation/other_ja/mdtext.tsv \
MDJP_MIDTSV=translation/other_ja/midgame.tsv MDJP_SCENETSV=translation/other_ja/scenetxt.tsv MDJP_CONVOUT=build/conv \
python -X utf8 tools/build_mdjp.py ../MARTIAN translation/empty.txt build/MDJP.COM > build/build_log.txt 2>&1 || { tail -20 build/build_log.txt; exit 1; }
grep -v "隠す" build/build_log.txt | grep -E "注意|表|置き換え|MDTEXT|MIDGAME|SCENETXT|MDJP"
python -X utf8 tools/make_patch.py ../MARTIAN build/conv build/MDJP.PAT | tail -1 || exit 1
python -X utf8 tools/build_mk.py build/MDJPMK.COM || exit 1
