# -*- coding: utf-8 -*-
"""用語集の下書き（translation/glossary.tsv）を作る。出現数は訳の TSV の英文から数える。
すでに用語集があれば、訳語・状態・メモはそちらを残す（下書きの行は足すだけ）。
使い方: python -I tools/make_glossary.py
"""
import sys, os, re, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from strdb import read_tsv

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
TR = os.path.join(ROOT, 'translation')

# 分類, 英語, 訳語, 状態, メモ
DRAFT = '''
シリーズ|Avatar|アバタール|確定|UW2 と同じ
シリーズ|Guardian|ガーディアン|確定|
シリーズ|Britannia|ブリタニア|確定|
シリーズ|Earth|地球|確定|アバタールの故郷の意味のとき。元素の Earth は「土」
シリーズ|Pagan|ペイガン|確定|世界の名前。Pagans は「ペイガンの民」
シリーズ|blackrock|ブラックロック|確定|UW2 と同じ
シリーズ|Ethereal Void|エーテルの虚空|確定|UW2 と同じ
シリーズ|daemon|デーモン|確定|UW2 と同じ
タイタン|Titan|タイタン|仮|Titans は「タイタンたち」
タイタン|Lithos|リソス|仮|土のタイタン
タイタン|Pyros|パイロス|仮|火のタイタン
タイタン|Hydros|ハイドロス|仮|水のタイタン
タイタン|Stratos|ストラトス|仮|風のタイタン
タイタン|Mountain King|山の王|仮|リソスの呼び名
タイタン|Mystic Voice|神秘の声|仮|ストラトスの呼び名
魔法|Necromancy|死霊術|仮|
魔法|Necromancer|ネクロマンサー|仮|方針を決める（カタカナか漢字か）
魔法|Sorcery|妖術|仮|
魔法|Sorcerer|ソーサラー|仮|方針を決める
魔法|Theurgy|祈祷術|仮|
魔法|Theurgist|祈祷師|仮|方針を決める
魔法|Tempestry|テンペストリー|仮|
魔法|Tempest|テンペスト|仮|モルデアの称号
魔法|Thaumaturgy|奇跡術|仮|
魔法|Focus|フォーカス|仮|複数形 Foci も「フォーカス」
魔法|Truename|真の名|仮|
魔法|reagent|触媒|仮|
魔法|words of power|力の言葉|仮|呪文の言葉（Kal Corp Xen など）は英字のまま
階級|Disciple|ディサイプル|仮|妖術師の階級。方針を決める
階級|Acolyte|アコライト|仮|
階級|Adept|アデプト|仮|
階級|Initiate|イニシエイト|仮|
呪文|Death Speak|デススピーク|仮|呪文名はカタカナ。中黒は動詞で始まる名前と of を含む名前だけ（UW2・SFC VI と同じ）
呪文|Mask of Death|マスク・オブ・デス|仮|
呪文|Rock Flesh|ロックフレッシュ|仮|
呪文|Summon Dead|サモン・デッド|仮|
呪文|Open Ground|オープン・グラウンド|仮|
呪文|Create Golem|クリエイト・ゴーレム|仮|
呪文|Withstand Death|ウィズスタンド・デス|仮|
呪文|Grant Peace|グラント・ピース|仮|
呪文|Call Quake|コール・クエイク|仮|
呪文|Meteor Shower|メテオシャワー|仮|
呪文|Air Walk|エアウォーク|仮|
呪文|Divination|ディヴィネーション|仮|
呪文|Healing Touch|ヒーリングタッチ|仮|
呪文|Aerial Servant|エアリアルサーヴァント|仮|
呪文|Restoration|レストレーション|仮|
呪文|Fade From Sight|フェイド・フロム・サイト|仮|
呪文|Hear Truth|ヒア・トゥルース|仮|
呪文|Intervention|インターベンション|仮|
呪文|Reveal|リヴィール|仮|
呪文|Ignite|イグナイト|仮|
呪文|Extinguish|エクスティングイッシュ|仮|
呪文|Flash|フラッシュ|仮|
呪文|Flame Bolt|フレイムボルト|仮|
呪文|Endure Heat|エンデュア・ヒート|仮|
呪文|Fire Shield|ファイアシールド|仮|
呪文|Armor of Flames|アーマー・オブ・フレイムズ|仮|
呪文|Create Fire|クリエイト・ファイア|仮|
呪文|Explosion|エクスプロージョン|仮|
呪文|Summon Daemon|サモン・デーモン|仮|UW2 と同じ
呪文|Banish Daemon|バニッシュ・デーモン|仮|
呪文|Conflagration|コンフラグレーション|仮|
触媒|blood|血|仮|
触媒|bone shards|骨のかけら|仮|
触媒|wood|木片|仮|
触媒|dirt|土くれ|仮|
触媒|executioner's hood|処刑人の頭巾|仮|キノコの名前
触媒|blackmoor|ブラックムーア|仮|
触媒|deadman's elbow|死人の肘|仮|
触媒|volcanic ash|火山灰|仮|
触媒|pumice|軽石|仮|
触媒|obsidian|黒曜石|仮|
触媒|iron|鉄|仮|
触媒|brimstone|硫黄|仮|
触媒|daemon bone|デーモンの骨|仮|
触媒|eye of newt|イモリの目|仮|
触媒|bat wing|コウモリの翼|仮|
触媒|snake skin|ヘビの皮|仮|
触媒|dragon blood|竜の血|仮|
地名|Tenebrae|テネブレ|仮|町。Tenebraen は「テネブレの」
地名|Argentrock Isle|アージェントロック島|仮|Argentrock・Argent Rock も「アージェントロック」
地名|Obsidian Fortress|黒曜石の砦|仮|
地名|Hall of the Mountain King|山の王の広間|仮|
地名|Catacombs|地下墓所|仮|Upper / Lower は「上層 / 下層」
地名|Pit of Death|死の穴|仮|Pit of the Dead は「死者の穴」
地名|City of the Dead|死者の都|仮|
地名|Plateau|高原|仮|
地名|Daemon's Crag|デーモンの岩山|仮|
地名|Brimstone Cliffs|硫黄の崖|仮|
地名|Lava River|溶岩の川|仮|
地名|Carthax Lake|カーサックス湖|仮|
地名|Treasure Cove|宝の入り江|仮|
地名|Stone Cove|石の入り江|仮|
地名|Fishermans Reef|漁師の岩礁|仮|
地名|Windy Point|風の岬|仮|
地名|Sea of Rains|雨の海|仮|
地名|Plain of Fire|火の界|仮|Water / Air / Earth も「水の界 / 風の界 / 土の界」
地名|Shrine of the Ancient Ones|古き者たちの社|仮|
地名|Perivolcanae|ペリヴォルカネ|仮|
地名|Mesostelae|メソステラエ|仮|
地名|Morgaelin|モーゲイリン|仮|
人々|Zealan|ジーラン|仮|古代の民。Zealans は「ジーランの民」
人々|Ancient Ones|古き者たち|仮|
人々|Order of Enlightenment|啓示の結社|仮|
人々|Cabal|秘密結社|仮|
人々|Enclave|エンクレイヴ|仮|
人名|Mordea|モルデア|仮|
人名|Devon|デボン|仮|
人名|Salkind|サルキンド|仮|
人名|Beren|ベレン|仮|
人名|Bentic|ベンティック|仮|
人名|Moriens|モリエンス|仮|
人名|Cyrrus|サイラス|仮|
人名|Torwin|トーウィン|仮|
人名|Lothian|ロジアン|仮|
人名|Orlok|オーロック|仮|
人名|Gwillim|グウィリム|仮|
人名|Stellos|ステロス|仮|
人名|Jenna|ジェナ|仮|
人名|Vardion|ヴァーディオン|仮|
人名|Mythran|ミスラン|仮|
人名|Bane|ベイン|仮|
人名|Aphelion|アフェリオン|仮|
人名|Kalen|ケイレン|仮|
人名|John Blowhard|ジョン・ブロウハード|仮|
人名|Toran|トラン|仮|
人名|Kilandra|キランドラ|仮|
人名|Corinth|コリンス|仮|
人名|Malchir|マルキア|仮|
人名|Daemion|デーミオン|仮|
人名|Aramina|アラミナ|仮|
人名|Keldan|ケルダン|仮|
人名|Darion|ダリオン|仮|
人名|Xavier|ザビエル|仮|Brother Xavier は「ザビエル修道士」
人名|Yevaud|イェヴォード|仮|
人名|Shaana|シャーナ|仮|
人名|Korick|コリック|仮|
人名|Varkus|ヴァーカス|仮|
人名|Knarl|ナール|仮|
人名|Torax|トーラックス|仮|
人名|Celidia|セリディア|仮|
人名|Galious|ガリアス|仮|
人名|Odion|オディオン|仮|
人名|Tarna|ターナ|仮|
人名|Rhian|リアン|仮|
人名|Gorgrond|ゴーグロンド|仮|
人名|Vividos|ヴィヴィドス|仮|
人名|Khumash|クマシュ|仮|Khumash-Gor
人名|Lurker|ラーカー|仮|水の怪物（The Lurker）
人名|Bone Crusher|ボーンクラッシャー|仮|
宝物|Heart of Earth|大地の心臓|仮|タイタンの宝物。Tongue of Flame / Breath of Wind / Tear of the Seas と組
宝物|Tongue of Flame|炎の舌|仮|
宝物|Breath of Wind|風の息吹|仮|
宝物|Tear of the Seas|海の涙|仮|
宝物|Skull of Quakes|地震の頭骨|仮|「髑髏」は第2水準で使えない
宝物|Slayer|スレイヤー|仮|魔法の剣
宝物|Key of the Caretaker|管理人の鍵|仮|
用語|Test of Centeredness|平静の試練|仮|
用語|Test of Wisdom|知恵の試練|仮|
用語|Ceremony of Eternity|永遠の儀式|仮|
用語|Elder Tongue|古語|仮|
暦（時刻）|Bloodwatch|ブラッドウォッチ|仮|時刻・曜日・月はカタカナにするか、意味で訳すかを決める
暦（時刻）|Firstebb|ファーストエブ|仮|
暦（時刻）|Daytide|デイタイド|仮|
暦（時刻）|Threemoons|スリームーンズ|仮|
暦（時刻）|Lastebb|ラストエブ|仮|
暦（時刻）|Eventide|イーブンタイド|仮|
暦（曜日）|Guarday|守りの日|仮|
暦（曜日）|Earthday|土の日|仮|
暦（曜日）|Waterday|水の日|仮|
暦（曜日）|Airday|風の日|仮|
暦（曜日）|Fireday|火の日|仮|
暦（曜日）|Blackday|黒の日|仮|
暦（月）|Stonemark|ストーンマーク|仮|
暦（月）|Skyrock|スカイロック|仮|
暦（月）|Windbreak|ウインドブレイク|仮|
暦（月）|Stormpeak|ストームピーク|仮|
暦（月）|Firefall|ファイアフォール|仮|
暦（月）|DarkFlame|ダークフレイム|仮|
'''


def count(term, texts):
    pat = re.compile(r'\b' + re.escape(term) + r'\b', re.I)
    return sum(len(pat.findall(t)) for t in texts)


def main():
    texts = [r['en'] for p in glob.glob(os.path.join(TR, 'usecode', '*.tsv')) for r in read_tsv(p)]
    texts += [r['en'] for r in read_tsv(os.path.join(TR, 'intro.tsv'))]
    path = os.path.join(TR, 'glossary.tsv')
    old = {}
    if os.path.exists(path):
        for ln in open(path, encoding='utf-8').read().split('\n')[1:]:
            p = ln.rstrip('\r').split('\t')
            if len(p) >= 6:
                old[p[1]] = p
    rows = []
    for ln in DRAFT.strip().split('\n'):
        cat, en, ja, st, note = (ln.split('|') + [''] * 5)[:5]
        if en in old:      # 決めた訳語・状態・メモは残す
            cat, ja, st, note = old[en][0], old[en][2], old[en][3], old[en][5]
        rows.append([cat, en, ja, st, str(count(en, texts)), note])
    # 下書きに無く、用語集に手で足した語も残す
    drafted = {r[1] for r in rows}
    for en, p in old.items():
        if en not in drafted:
            rows.append([p[0], en, p[2], p[3], str(count(en, texts)), p[5]])
    out = ['分類\t英語\t訳語\t状態\t出現数\tメモ']
    out += ['\t'.join(r) for r in rows]
    with open(path, 'w', encoding='utf-8', newline='') as f:
        f.write('\n'.join(out) + '\n')
    print('用語', len(rows), '件 →', path)
    zero = [r[1] for r in rows if r[4] == '0']
    if zero:
        print('出現 0:', ', '.join(zero))


main()
