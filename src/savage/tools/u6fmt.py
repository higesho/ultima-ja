import struct
def lzw(data):
    size=struct.unpack('<I',data[:4])[0]
    bits=9; pos=32  # bit position
    dic=[bytes([i]) for i in range(256)]+[b'',b'']
    out=bytearray(); prev=None
    nbits=len(data)*8
    def get():
        nonlocal pos
        bi=pos>>3; v=data[bi]|(data[bi+1]<<8 if bi+1<len(data) else 0)|(data[bi+2]<<16 if bi+2<len(data) else 0)
        c=(v>>(pos&7))&((1<<bits)-1); pos+=bits; return c
    while pos+bits<=nbits:
        c=get()
        if c==0x100:
            bits=9; dic=dic[:258]; prev=None; continue
        if c==0x101: break
        if prev is None:
            e=dic[c]; out+=e; prev=e; continue
        if c<len(dic): e=dic[c]; dic.append(prev+e[:1])
        elif c==len(dic): e=prev+prev[:1]; dic.append(e)
        else: raise ValueError('bad code')
        out+=e; prev=e
        if len(dic)>=(1<<bits) and bits<12: bits+=1
    return bytes(out),size
def lib(data,w=4):
    fmt='<I' if w==4 else '<H'
    first=None; offs=[]
    i=0
    while True:
        o=struct.unpack(fmt,data[i:i+w])[0]
        if o and (first is None or o<first): first=o
        offs.append(o); i+=w
        if first is not None and i>=first: break
    items=[]
    nz=sorted(set(o for o in offs if o)) + [len(data)]
    for o in offs:
        if not o: items.append(None); continue
        nxt=min(x for x in nz if x>o)
        items.append(data[o:nxt])
    return items
