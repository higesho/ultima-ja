# サーペントアイルの配布物（SerpentIsle_JP.zip）を作る
#   使い方: python mkdist.py [出力フォルダ] [版]   （既定: jp_work\dist、1.0）
# 中身は、改造した Exult（BG 側でビルドしたもの。本体・DLL・Exult のデータ）、訳とフォント（patch）、
# フォルダの中だけで動くための設定と起動用の bat、説明書、使っているものの使用許諾。
# 原作のプログラムやデータは入れない。ソースも入れない（GitHub の higesho/exult の ja ブランチ）。
# BG 側のファイルは読むだけで、書きかえない。
import sys, os, shutil, subprocess, zipfile
sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
W = os.path.normpath(os.path.join(HERE, '..'))
BG = os.path.normpath(os.path.join(W, '..', '..', 'Ultima 7', 'jp_work'))
EX = os.path.join(BG, 'exult')
VCPKG_SHARE = os.path.join(EX, 'msvcstuff', 'vs2019', 'vcpkg_installed', 'x64-windows', 'x64-windows', 'share')
CRT = r'C:\Program Files\Microsoft Visual Studio\18\Community\VC\Redist\MSVC\14.52.36520\x64\Microsoft.VC145.CRT'
NAME = 'SerpentIsle_JP'
SOURCE_URL = 'https://github.com/higesho/exult'

DLLS = ['SDL3.dll', 'z.dll', 'libpng16.dll', 'ogg.dll', 'vorbis.dll', 'vorbisfile.dll',
        'libfluidsynth-3.dll', 'mt32emu-2.dll']
CRT_DLLS = ['vcruntime140.dll', 'vcruntime140_1.dll', 'msvcp140.dll']
DATA = ['exult.flx', 'exult_bg.flx', 'exult_si.flx', 'midisfx.flx']
PATCH = ['usecode_ja.tsv', 'textmsg.txt', 'npc_names.txt', 'exultmsg.txt', 'mainshp.flx', 'gumps.vga',
         'jfont8.bin', 'jfont12.bin']
LICENSES = [('sdl3', 'SDL3.txt'), ('zlib', 'zlib.txt'), ('libpng', 'libpng.txt'),
            ('libogg', 'libogg.txt'), ('libvorbis', 'libvorbis.txt'),
            ('fluidsynth', 'FluidSynth.txt'), ('libmt32emu', 'Munt_mt32emu.txt')]

CFG = '''<config>
  <disk>
    <data_path>data</data_path>
    <game>
      <serpentisle>
        <path>..</path>
        <patch>patch</patch>
        <savegame_path>save\\serpentisle</savegame_path>
        <gamedat_path>save\\serpentisle\\gamedat</gamedat_path>
      </serpentisle>
      <silverseed>
        <path>..</path>
        <patch>patch</patch>
        <savegame_path>save\\silverseed</savegame_path>
        <gamedat_path>save\\silverseed\\gamedat</gamedat_path>
      </silverseed>
    </game>
  </disk>
  <audio>
    <speech>
      <with_subs>yes</with_subs>
    </speech>
  </audio>
  <video>
    <fullscreen>no</fullscreen>
    <game>
      <width>320</width>
      <height>200</height>
    </game>
    <display>
      <width>1024</width>
      <height>768</height>
    </display>
    <scale>2</scale>
    <scale_method>Point</scale_method>
    <fill_mode>Fit</fill_mode>
  </video>
</config>
'''

# 起動用（日本語の Windows の cmd で読めるよう Shift_JIS・CRLF で書く）
BAT = '''@echo off
cd /d "%~dp0"
if not exist "..\\STATIC\\INITGAME.DAT" goto wrong
if not exist "..\\STATIC\\PAPERDOL.VGA" goto wrong
if not exist "save\\silverseed\\gamedat" mkdir "save\\silverseed\\gamedat"
if not exist "save\\serpentisle\\gamedat" mkdir "save\\serpentisle\\gamedat"
start "" "%~dp0Exult.exe" -p --ss
exit /b 0
:wrong
echo SerpentIsle_JP フォルダが、サーペントアイルのゲームのフォルダ（SERPENT.COM と STATIC フォルダがあるフォルダ）に入っていません。
echo SerpentIsle_JP フォルダごと、ゲームのフォルダに入れてから、もう一度開いてください。
pause
exit /b 1
'''

README = '''ウルティマVII 第2部 サーペントアイル 日本語化パッチ（Ultima VII Part Two: Serpent Isle ＋ The Silver Seed）
版: {version}

非公式のファン翻訳です。開発元・販売元とは関係ありません。
GOG.com で販売されている「Ultima 7 Complete」のサーペントアイル（The Silver Seed 入り）を、
Exult（ウルティマVII を今のパソコンで遊ぶためのエンジン）で日本語で遊べるようにします。

■ 入れ方
1. ダウンロードした SerpentIsle_JP.zip を展開します。
2. 出てきた SerpentIsle_JP フォルダを、フォルダごと、サーペントアイルのゲームのフォルダ
   （SERPENT.COM と STATIC フォルダがあるフォルダ。GOG 版では「Ultima 7 - Serpent Isle」など）に入れます。
3. SerpentIsle_JP フォルダの中の SerpentIsle_JP.bat をダブルクリックすると始まります。
   よく遊ぶなら、SerpentIsle_JP.bat のショートカットをデスクトップに作っておくと便利です。

ゲームのファイルは書き換えません。設定とセーブデータは SerpentIsle_JP フォルダの中に作られます。
The Silver Seed（追加シナリオ）入りとして起動します。

■ 外し方
SerpentIsle_JP フォルダを消します。
セーブデータ（SerpentIsle_JP\\save）も一緒に消えるので、残したいときは先に別の場所へ写してください。

■ 遊ぶときの注意
- GOG Galaxy やいつものショートカットから起動する DOS 版は英語のままです。
  日本語で遊ぶときは SerpentIsle_JP.bat から起動してください。
- セーブデータは DOS 版とは別です。
- 会話は、画面に出る言葉をマウスで選んで進めます。ESC キーで会話を終えます。
- 声のある場面には日本語の字幕が出ます（設定の「声と字幕」）。
- 呪文の唱え言葉は、原作の言葉をローマ字で表示します。
- 町の看板（ルーン文字・蛇の文字）は、原作どおりの文字のままです。
- タイトルのロゴなど、絵の中に描かれている英字の一部は英語のままです。
- 効果音を鳴らすには、Exult のサイト（https://exult.info/）のダウンロードのページにある
  効果音のパック（Sound pack）を、SerpentIsle_JP フォルダの中の data フォルダに展開してください。
  音楽と声は、入れなくても鳴ります。
- Alt＋Enter で全画面と窓を切り替えられます。そのほかの設定は、ESC キーで出るメニューから変えられます。
- 設定を初めの状態に戻したいときは、SerpentIsle_JP フォルダの中の exult.cfg を、zip の中のものに入れ替えてください。

■ ご意見・誤訳の報告
https://github.com/higesho/ultima-ja/issues

■ 中身と権利
- Exult.exe と data フォルダは、Exult に日本語の表示などを加えたものです。
  Exult は GNU General Public License（第2版またはそれ以降）で配布されています（COPYING.txt）。
  このパッチの Exult のソースは次の場所で公開しています。
    {source_url} の ja ブランチ（{commit}）
  もとの Exult: Copyright (C) The Exult Team  https://exult.info/
- 日本語の表示に、東雲フォント（The Electronic Font Open Laboratory、Public Domain）と、
  美咲フォント（Copyright (C) 2002-2021 Num Kadoma。自由に利用・複製・再配布できるフリーソフトウエア）を使っています。
- 次のものを使っています。使用許諾は licenses フォルダにあります。
  SDL、zlib、libpng、Ogg Vorbis、FluidSynth、Munt（mt32emu）、Microsoft Visual C++ のランタイム
- Ultima は Electronic Arts Inc. の商標です。ゲームの画像・文章の権利は原作の権利者にあります。
- このパッチの使用は自己責任でお願いします。
'''

def write(path, text, enc='utf-8', crlf=True):
    with open(path, 'w', encoding=enc, newline='\r\n' if crlf else '\n') as f:
        f.write(text)

def main(out, version):
    commit = subprocess.run(['git', '-C', EX, 'rev-parse', '--short=9', 'HEAD'],
                            capture_output=True, text=True, check=True).stdout.strip()
    dirty = subprocess.run(['git', '-C', EX, 'status', '--porcelain', '--untracked-files=no'],
                           capture_output=True, text=True, check=True).stdout.strip()
    if dirty:
        sys.exit('BG 側の exult にコミットしていない変更があります。ソースと配布物を合わせるため、コミットされるのを待ってください。')
    top = os.path.join(out, NAME)
    if os.path.exists(top):
        shutil.rmtree(top)
    for d in ('data', 'patch', 'licenses'):
        os.makedirs(os.path.join(top, d))

    # 訳を作り直してから写す
    subprocess.run([sys.executable, '-I', os.path.join(HERE, 'mkpatch.py'), os.path.join(W, 'test', 'patch')], check=True)
    shutil.copy2(os.path.join(EX, 'Exult.exe'), top)
    for d in DLLS:
        shutil.copy2(os.path.join(EX, d), top)
    for d in CRT_DLLS:
        shutil.copy2(os.path.join(CRT, d), top)
    for d in DATA:
        shutil.copy2(os.path.join(EX, 'data', d), os.path.join(top, 'data'))
    for p in PATCH:
        shutil.copy2(os.path.join(W, 'test', 'patch', p), os.path.join(top, 'patch'))

    write(os.path.join(top, 'exult.cfg'), CFG, crlf=False)
    write(os.path.join(top, NAME + '.bat'), BAT, enc='cp932')
    write(os.path.join(top, 'README.txt'), README.format(version=version, source_url=SOURCE_URL, commit=commit))
    shutil.copy2(os.path.join(EX, 'COPYING'), os.path.join(top, 'COPYING.txt'))
    shutil.copy2(os.path.join(EX, 'AUTHORS'), os.path.join(top, 'licenses', 'Exult_AUTHORS.txt'))
    for pkg, name in LICENSES:
        shutil.copy2(os.path.join(VCPKG_SHARE, pkg, 'copyright'), os.path.join(top, 'licenses', name))
    sh = os.path.join(BG, 'font', 'dl_shinonome', 'shinonome-0.9.11', 'LICENSE')
    write(os.path.join(top, 'licenses', 'Shinonome.txt'), open(sh, encoding='euc_jp').read())
    write(os.path.join(top, 'licenses', 'Misaki.txt'),
          '美咲フォント\nCopyright (C) 2002-2021 Num Kadoma\n'
          '自由に利用・複製・再配布できるフリーソフトウエアです。\nhttps://littlelimit.net/misaki.htm\n')

    zpath = os.path.join(out, NAME + '.zip')
    if os.path.exists(zpath):
        os.remove(zpath)
    n = 0
    with zipfile.ZipFile(zpath, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for root, _, files in os.walk(top):
            for f in sorted(files):
                full = os.path.join(root, f)
                z.write(full, os.path.relpath(full, out))
                n += 1
    print(f'{zpath}: {n} ファイル、{os.path.getsize(zpath) / 1048576:.1f} MB（Exult {commit}）')

if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(W, 'dist')
    version = sys.argv[2] if len(sys.argv) > 2 else '1.0'
    main(out, version)
