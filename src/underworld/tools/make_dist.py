"""配布物を作る: python make_dist.py [--game=uw2]
  UW1: dist/ウルティマアンダーワールド日本語化パッチ/ と dist/UltimaUnderworld_JP.zip
  UW2: dist/ウルティマアンダーワールド2日本語化パッチ/ と dist/UltimaUnderworld2_JP.zip
  - UWJP（UW2JP）.COM・.DAT は試験用の部分を入れずに組み立て直す
  - dosboxULTIMAn_single.conf は GOG の元の設定に、表示の設定（[sdl] output=opengl、[render] glshader=sharp）と
    autoexec の LH ????.COM を足したもの
  - DOSBOX\\opengl32.dll は gl64/out の 64 ビット版（dosbox-staging 用）"""
import os, re, sys, shutil, subprocess, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.normpath(os.path.join(HERE, '..'))
GAMES = {
    'uw1': dict(dir=os.path.normpath(os.path.join(WORK, '..')), conf='dosboxULTIMA1_single.conf', name='UWJP',
                folder='ウルティマアンダーワールド日本語化パッチ', zip='UltimaUnderworld_JP.zip',
                tsv='uw1_ur_ja.tsv', readme='はじめにお読みください.txt'),
    'uw2': dict(dir=os.path.normpath(os.path.join(WORK, '..', '..', 'Ultima Underworld 2')), conf='dosboxULTIMA2_single.conf',
                name='UW2JP', folder='ウルティマアンダーワールド2日本語化パッチ', zip='UltimaUnderworld2_JP.zip',
                tsv='uw2_ur_ja.tsv', readme='uw2_はじめにお読みください.txt'),
}


def patched_conf(g):
    t = open(os.path.join(g['dir'], g['conf']), 'rb').read().decode('latin1')
    nl = '\r\n' if '\r\n' in t else '\n'
    head = nl.join(['# Japanese patch: OpenGL output (for DOSBOX\\opengl32.dll) and sharp scaling',
                    '[sdl]', 'output=opengl', '', '[render]', 'glshader=sharp', '', ''])
    t2, n = re.subn(r'(?m)^c:(\r?\n)+GOG\.BAT', 'c:' + nl + 'LH ' + g['name'] + '.COM' + nl + 'GOG.BAT', t)
    assert n == 1, 'GOG の起動設定の形が違う'
    return (head + t2).encode('latin1')


def main(game):
    g = GAMES[game]
    out = os.path.join(WORK, 'dist', g['folder']); zpath = os.path.join(WORK, 'dist', g['zip'])
    env = dict(os.environ); env.pop('UWJP_TEST', None)
    build = os.path.join(WORK, 'build', 'release_' + game)
    r = subprocess.run([sys.executable, '-I', os.path.join(HERE, 'build_uwjp.py'),
                        os.path.join(WORK, 'translation', g['tsv']), build, '--game=' + game], env=env,
                       capture_output=True, text=True, encoding='utf-8')
    print(r.stdout[-400:], r.stderr[-400:])
    if r.returncode: sys.exit('組み立てに失敗')
    if os.path.exists(out): shutil.rmtree(out)
    os.makedirs(os.path.join(out, 'DOSBOX'))
    for f in (g['name'] + '.COM', g['name'] + '.DAT'): shutil.copy(os.path.join(build, f), os.path.join(out, f))
    open(os.path.join(out, g['conf']), 'wb').write(patched_conf(g))
    shutil.copy(os.path.join(WORK, 'gl64', 'out', 'opengl32.dll'), os.path.join(out, 'DOSBOX', 'opengl32.dll'))
    ini = ['; 日本語化パッチの表示の設定（DOSBOX フォルダの opengl32.dll が読みます）', '[view]',
           '; 日本語の字の形: shinonome（東雲フォント 12 ドット）または misaki（美咲フォント 8 ドット）', 'font=shinonome',
           '; うまく表示されないとき 1 にすると、ultima_ja.log に記録します', 'log=0', '']
    open(os.path.join(out, 'DOSBOX', 'ultima_ja.ini'), 'wb').write('\r\n'.join(ini).encode('cp932'))
    readme = open(os.path.join(WORK, 'dist_src', g['readme']), encoding='utf-8').read()
    open(os.path.join(out, 'はじめにお読みください.txt'), 'wb').write(
        b'\xef\xbb\xbf' + readme.replace('\r\n', '\n').replace('\n', '\r\n').encode('utf-8'))
    if os.path.exists(zpath): os.remove(zpath)
    with zipfile.ZipFile(zpath, 'w', zipfile.ZIP_DEFLATED) as z:
        for dp, _, fns in os.walk(out):
            for fn in fns:
                p = os.path.join(dp, fn)
                z.write(p, os.path.relpath(p, os.path.dirname(out)))
    for dp, _, fns in os.walk(out):
        for fn in fns:
            p = os.path.join(dp, fn); print('%-60s %8d' % (os.path.relpath(p, out), os.path.getsize(p)))
    print(zpath, os.path.getsize(zpath))


if __name__ == '__main__':
    main(next((a.split('=', 1)[1] for a in sys.argv[1:] if a.startswith('--game=')), 'uw1'))
