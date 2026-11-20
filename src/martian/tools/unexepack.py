import struct,sys
def unpack(path):
    d=open(path,'rb').read()
    h=struct.unpack('<14H',d[:28]); last,pages=h[1],h[2]; hdr=h[4]; ip,cs=h[10],h[11]
    size=(pages-1)*512+last if last else pages*512
    img=bytearray(d[hdr*16:size])
    eh=cs*16
    rIP,rCS,_,exsz,rSP,rSS,dlen,skip,sig=struct.unpack('<8H2s',img[eh:eh+18])
    assert sig==b'RB',sig
    src=img[:eh]; dst=bytearray(dlen*16); dst[:len(src)]=src
    s=len(src)-1
    while dst[s]==0xff: s-=1
    dpos=len(dst)
    # work in place style: read backwards from src copy
    buf=bytes(src); s=len(buf)-1
    while buf[s]==0xff: s-=1
    out=bytearray(dlen*16); o=len(out)
    while True:
        cmd=buf[s]; s-=1
        ln=buf[s]<<8|buf[s-1]; s-=2
        c=cmd&0xfe
        if c==0xb0:
            b=buf[s]; s-=1
            out[o-ln:o]=bytes([b])*ln; o-=ln
        elif c==0xb2:
            out[o-ln:o]=buf[s-ln+1:s+1]; s-=ln; o-=ln
        else: raise Exception('bad cmd %x'%cmd)
        if cmd&1: break
    # remaining head (uncopied) stays as in src
    out[:s+1]=buf[:s+1]
    # relocations
    code=bytes(img[eh:eh+exsz])
    p=code.find(b'Packed file is corrupt')+len(b'Packed file is corrupt')
    relocs=[]
    for seg in range(16):
        n=struct.unpack('<H',code[p:p+2])[0]; p+=2
        for i in range(n):
            relocs.append((seg*0x1000,struct.unpack('<H',code[p:p+2])[0])); p+=2
    return out,dict(ip=rIP,cs=rCS,sp=rSP,ss=rSS),relocs
if __name__=='__main__':
    out,regs,rel=unpack(sys.argv[1])
    open(sys.argv[2],'wb').write(out)
    print(len(out),{k:hex(v) for k,v in regs.items()},'relocs',len(rel))
