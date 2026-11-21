from pathlib import Path
import numpy as np
from .paired_anf import anf,coefficient_polys,matrix,rank_decomposition,poly_product,Product,Plan,bits
from .rm_code import code,syndrome,reconstruct
HIGH_OUTPUTS=[7*j+b for j in range(5) for b in range(1,7)]

def code_diagnostics(words,degree):
    """Check the actual punctured evaluation code, never padding the tail."""
    if degree not in (1,2):raise ValueError('degree must be1or2')
    words=np.asarray(words,np.int64);bad=[];blocks=0;reconstructed=0
    for start in range(0,len(words),16):
        n=min(16,len(words)-start);c=code(n,degree);parity=(words[start:start+n].T&1).astype(bool)
        syn=syndrome(parity,c);ids=np.flatnonzero(syn)
        bad.extend((start,int(i),int(syn[i])) for i in ids);blocks+=1
        if not len(ids):
            for row in parity:reconstruct(sum(int(x)<<i for i,x in enumerate(row)),c);reconstructed+=1
    return dict(valid=not bad,degree=degree,blocks=blocks,tail=len(words)%16,
        bad_count=len(bad),bad_examples=bad[:8],polynomial_reconstructions=reconstructed)

def lsb_plan(delta,degree):
    """Five exact unmixed LSB rank decompositions, with paired pure corrections."""
    delta=np.asarray(delta,np.int64);A,J=delta.shape
    if J!=5:raise ValueError('need five words')
    polys=coefficient_polys(anf(delta,8),40);pure={};products=[];ranks=[];H=(A-1)>>4
    def add(poly,fan,shift):
        for mask in bits(poly):
            m=mask<<shift
            if m<A:pure[m]=pure.get(m,0)^fan
    for j in range(5):
        columns,lo,hi=matrix(polys[8*j],4,A);factors=rank_decomposition(columns);ranks.append(len(factors));fan=1<<(8*j)
        for t in range(0,len(factors),2):
            l1,r1=factors[t];l2,r2=factors[t+1] if t+1<len(factors) else (0,0)
            products.append(Product(l1,r1,l2,r2,fan));lo^=poly_product(l1,l2,15);hi^=poly_product(r1,r2,H)
        add(lo,fan,0);add(hi,fan,4)
    assert max(ranks,default=0)<=(4 if degree==1 else 10)
    cache=sorted([m for m in range(1,16) if m.bit_count()>=2]+[h<<4 for h in range(1,H+1) if h.bit_count()>=2])
    return Plan(A,5,8,4,products,{m:v for m,v in pure.items() if v},ranks,cache,parity_scratch=0)

def combine(high,low):
    assert (high.addresses,high.batch,high.brot,high.low_bits)==(low.addresses,low.batch,low.brot,low.low_bits)
    assert high.cache_masks==low.cache_masks and high.parity_scratch==low.parity_scratch==0
    lsb_mask=sum(1<<(8*j) for j in range(5))
    assert all(not(p.fanout&lsb_mask) for p in high.products)
    assert all(not(v&lsb_mask) for v in high.pure.values())
    assert all(not(p.fanout&~lsb_mask) for p in low.products)
    assert all(not(v&~lsb_mask) for v in low.pure.values())
    pure=high.pure.copy()
    for m,v in low.pure.items():pure[m]=pure.get(m,0)^v
    return Plan(high.addresses,5,8,4,low.products+high.products,{m:v for m,v in pure.items() if v},low.ranks,
        high.cache_masks.copy(),parity_scratch=0)

