"""far call / push cs+near call の呼び出し元を探す。使い方: python xref.py イメージ SEG OFF"""
import re,sys
def load(p): return open(p,'rb').read()[:0x2d850]
def callers(d,seg,off):
    pat=b'\x9a'+off.to_bytes(2,'little')+seg.to_bytes(2,'little')
    hs=[m.start() for m in re.finditer(re.escape(pat),d)]
    base=seg*16
    for i in range(max(0,base),min(len(d)-4,base+0x10000)):
        if d[i]==0x0e and d[i+1]==0xe8 and (i+4-base+int.from_bytes(d[i+2:i+4],'little',signed=True))&0xffff==off: hs.append(i+1)
    return sorted(hs)
def func(d,p):
    while p>0 and d[p:p+3]!=b'\x55\x8b\xec': p-=1
    return p
if __name__=='__main__':
    d=load(sys.argv[1]); seg=int(sys.argv[2],16); off=int(sys.argv[3],16)
    for h in callers(d,seg,off): print(hex(h),'in func',hex(func(d,h)))
