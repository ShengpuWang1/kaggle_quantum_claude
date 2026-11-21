from pathlib import Path
import sys,numpy as np
from staged_b154.paired_anf import anf,coefficient_polys,output_basis,matrix,rank_decomposition,bits,poly_product,Product,Plan,assert_classical
from staged_b154.emitter import high_masks
from staged_b154.scheduler import candidate_orders,product_requirement
from staged_b154.retention import optimize
from staged_b154.beam import orders as beam_orders

def row_plan(delta,brot=8):
    """Same shared-odd identity, residuals expanded in individual low monomials."""
    delta=np.asarray(delta,np.int64);A,J=delta.shape;assert J==5
    funcs,fans=output_basis(coefficient_polys(anf(delta,brot),5*brot));products=[];pure={};H=(A-1)//16
    eligible=[i for i,p in enumerate(funcs)if len(rank_decomposition(matrix(p,4,A)[0]))==15]
    for i,j in zip(eligible[::2],eligible[1::2]):
        ca=matrix(funcs[i],4,A)[0];cb=matrix(funcs[j],4,A)[0]
        r1=sum(1<<(h+1)for h,col in enumerate(ca)if(col>>1)&1)
        r2=sum(1<<(h+1)for h,col in enumerate(cb)if(col>>2)&1)
        products.append(Product(1<<1,r1,1<<2,r2,fans[i]^fans[j]))
        full=1<<3
        for h in bits(r1):full^=1<<(1|(h<<4))
        for h in bits(r2):full^=1<<(2|(h<<4))
        for h in bits(poly_product(r1,r2,H)):full^=1<<(h<<4)
        funcs[i]^=full;funcs[j]^=full
    ranks=[]
    def add(poly,fan,shift):
        for m in bits(poly):
            m<<=shift
            if m<A:pure[m]=pure.get(m,0)^fan
    for poly,fan in zip(funcs,fans):
        columns,lo,hi=matrix(poly,4,A)
        factors=[]
        for l in range(1,16):
            row=sum(1<<(h+1)for h,col in enumerate(columns)if(col>>l)&1)
            if row:factors.append((1<<l,row))
        ranks.append(len(factors))
        for t in range(0,len(factors),2):
            l1,r1=factors[t];l2,r2=factors[t+1]if t+1<len(factors)else(0,0)
            products.append(Product(l1,r1,l2,r2,fan));lo^=poly_product(l1,l2,15);hi^=poly_product(r1,r2,H)
        add(lo,fan,0);add(hi,fan,4)
    cache=sorted([m for m in range(1,16)if m.bit_count()>=2]+high_masks(A))
    p=Plan(A,5,brot,4,products,{m:f for m,f in pure.items()if f},ranks,cache,parity_scratch=0)
    assert_classical(p,delta);assert max(product_requirement(x).bit_count()for x in p.products)<=6
    return p

def schedule(plan,capacity):
    choices=[]
    for label,order in candidate_orders(plan,capacity).items():
        s,a=optimize(plan,order,capacity,'eager_'+label);choices.append(s)
    orders,metadata=beam_orders(plan,capacity,width=64,max_depth=9)
    for i,b in enumerate(orders):
        s,a=optimize(plan,b['order'],capacity,'beam64_'+str(i));choices.append(s)
    return min(choices,key=lambda s:(s['low_computations'],s['peak_live'],s['label']))
