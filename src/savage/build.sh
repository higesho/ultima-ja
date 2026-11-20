#!/bin/sh
# 日本語化の組み立て（常駐部 SEJP.COM、人物ごとの表 SEJP.DAT、日本語版の LZC、配布用のパッチ SEJP.PAT と組み立て役 SEJPMK.COM）
cd "$(dirname "$0")"
SEJP_SAVTSV=translation/other_ja/savage.tsv \
SEJP_GAMETSV="translation/other_ja/game.tsv;translation/other_ja/game_extra.tsv" \
SEJP_GAME2TSV=translation/other_ja/game2.tsv \
SEJP_MIDTSV=translation/other_ja/midgame.tsv \
SEJP_LOOKTSV=translation/other_ja/look.tsv \
SEJP_CONVTEST=translation/conv_ja_all.tsv \
SEJP_CONVOUT=build/conv \
python -X utf8 tools/build_sejp.py ../SAVAGE translation/empty.txt build/SEJP.COM > build/build_log.txt 2>&1 || { tail -20 build/build_log.txt; exit 1; }
grep -E "注意|常に持つ表|置き換え|MIDGAME|SAVAGE.EXE|SEJP.COM" build/build_log.txt
python -X utf8 tools/make_patch_se.py ../SAVAGE build/conv build/SEJP.PAT || exit 1
python -X utf8 tools/build_mk_se.py build/SEJPMK.COM || exit 1
