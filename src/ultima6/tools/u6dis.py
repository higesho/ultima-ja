"""展開済み GAME.EXE イメージの逆アセンブル補助。
使い方: python dis.py イメージ 開始(16進,リニア) [バイト数] [セグメント基底(16進,段落)]"""
import sys,capstone
md=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_16)
def dis(img,lin,n=0x80,segbase=None):
    if segbase is None: segbase=lin>>4
    base=segbase<<4
    out=[]
    for i in md.disasm(img[lin:lin+n],lin-base):
        b=img[base+i.address:base+i.address+i.size]
        if not b: break
        extra=''
        if b[0]==0x9a:
            off=int.from_bytes(b[1:3],'little'); seg=int.from_bytes(b[3:5],'little'); extra='  ; far -> %05x'%(seg*16+off)
        out.append('%05x %04x:%04x  %-20s %s %s%s'%(base+i.address,segbase,i.address,b.hex(),i.mnemonic,i.op_str,extra))
    return '\n'.join(out)
if __name__=='__main__':
    img=open(sys.argv[1],'rb').read()
    lin=int(sys.argv[2],16); n=int(sys.argv[3],16) if len(sys.argv)>3 else 0x80
    sb=int(sys.argv[4],16) if len(sys.argv)>4 else None
    print(dis(img,lin,n,sb))
