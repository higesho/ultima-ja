"""EXEPACK を外した通常の MZ を作る。使い方: python rebuild_exe.py 元.EXE 出力.EXE [パッチ 16進リニア=16進バイト ...]"""
import sys,struct
sys.path.insert(0,__import__('os').path.dirname(__file__))
from unexepack import unpack
def build(src,patches=()):
    d=open(src,'rb').read()
    h=struct.unpack('<14H',d[:28])
    img,regs,rel=unpack(src); img=bytearray(img)
    for lin,b in patches: img[lin:lin+len(b)]=b
    hdrlen=(0x1c+4*len(rel)+15)//16*16
    pars=len(img)//16+(1 if len(img)%16 else 0)
    old_img_pars=((h[2]-1)*512+h[1]-h[4]*16+15)//16 if h[1] else (h[2]*512-h[4]*16+15)//16
    total=old_img_pars+h[5]
    minalloc=max(total-pars, regs['ss']+(regs['sp']+15)//16-pars)+1
    size=hdrlen+len(img)
    hdr=struct.pack('<2s13H',b'MZ',size%512,(size+511)//512,len(rel),hdrlen//16,minalloc,0xffff,regs['ss'],regs['sp'],0,regs['ip'],regs['cs'],0x1c,0)
    hdr+=b''.join(struct.pack('<HH',o,s) for s,o in rel)
    return hdr.ljust(hdrlen,b'\0')+bytes(img)
if __name__=='__main__':
    pats=[(int(a,16),bytes.fromhex(b)) for a,b in (p.split('=') for p in sys.argv[3:])]
    out=build(sys.argv[1],pats); open(sys.argv[2],'wb').write(out); print(sys.argv[2],len(out))
