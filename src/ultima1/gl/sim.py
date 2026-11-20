# 試験用の「GOG のまね」のフォルダを作って起動する
#   python sim.py make <作品のフォルダ名> [zip]   ゲームのフォルダを <作品>/jp_work/test/glsim に写し、
#                                                 日本語化の zip（省くと dist の *_JP.zip）を展開して、窓の表示の設定と DLL を足す
#   python sim.py run <作品のフォルダ名>           GOG と同じ引数で起動する（キーを送れるよう SDL は windib）
import os, sys, json, shutil, zipfile, subprocess, glob, time

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
TOP = os.path.normpath(os.path.join(HERE, '..', '..', '..'))
STATE = os.path.join(HERE, '..', 'test', 'dosbox_ctl.json')
VIEW = ("[sdl]\r\nfullscreen=false\r\nwindowresolution=960x720\r\noutput=opengl\r\n\r\n"
        "[render]\r\naspect=false\r\nscaler=none\r\n\r\n")


def add_view(conf_bytes):
    t = conf_bytes.decode('latin-1')
    if '[sdl]' in t: return conf_bytes
    assert t.count('[autoexec]') == 1
    return t.replace('[autoexec]', VIEW + '[autoexec]', 1).encode('latin-1')


def make(game, zpath=None):
    src = os.path.join(TOP, game)
    sim = os.path.join(src, 'jp_work', 'test', 'glsim')
    if os.path.exists(sim): shutil.rmtree(sim)
    shutil.copytree(src, sim, ignore=lambda d, names: [n for n in names if d == src and n in ('jp_work',)])
    zpath = zpath or sorted(glob.glob(os.path.join(src, 'jp_work', 'dist', '*_JP.zip')))[0]
    with zipfile.ZipFile(zpath) as z:
        for i in z.infolist():
            data = z.read(i)
            if i.filename.endswith('.conf'): data = add_view(data)
            out = os.path.join(sim, *i.filename.split('/'))
            os.makedirs(os.path.dirname(out), exist_ok=True)
            open(out, 'wb').write(data)
    dll = os.path.join(sim, 'DOSBOX', 'opengl32.dll')
    if not os.path.exists(dll): shutil.copyfile(os.path.join(HERE, 'out', 'opengl32.dll'), dll)
    ini = os.path.join(sim, 'DOSBOX', 'ultima_ja.ini')
    if not os.path.exists(ini): shutil.copyfile(os.path.join(HERE, 'ultima_ja.ini'), ini)
    s = open(ini, 'rb').read().replace(b'log=0', b'log=1').replace(b'remember=1', b'remember=0')
    open(ini, 'wb').write(s)
    print('作った:', sim, '（zip:', os.path.basename(zpath) + '）')


def run(game):
    sim = os.path.join(TOP, game, 'jp_work', 'test', 'glsim')
    info = json.load(open(glob.glob(os.path.join(sim, 'goggame-*.info'))[0], encoding='utf-8'))
    task = next(t for t in info['playTasks'] if t.get('isPrimary')) if any(
        t.get('isPrimary') for t in info['playTasks']) else info['playTasks'][0]
    cwd = os.path.join(sim, task.get('workingDir', ''))
    exe = os.path.join(sim, task['path'])
    args = subprocess.list2cmdline([exe]) + ' ' + task.get('arguments', '')
    p = subprocess.Popen(args, cwd=cwd, creationflags=0x8 | 0x200, env=dict(os.environ, SDL_VIDEODRIVER='windib'))
    json.dump({'pid': p.pid}, open(STATE, 'w'))
    time.sleep(1.5)
    print('起動した:', task['name'], p.pid)


if __name__ == '__main__':
    {'make': lambda: make(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None),
     'run': lambda: run(sys.argv[2])}[sys.argv[1]]()
