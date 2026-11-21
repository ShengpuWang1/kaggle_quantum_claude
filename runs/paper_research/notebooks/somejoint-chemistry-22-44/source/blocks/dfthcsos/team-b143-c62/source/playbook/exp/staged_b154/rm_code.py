"""Weighted nearest punctured RM(d,4) projection using dual-syndrome DP."""
from __future__ import annotations
import numpy as np

def gf2_basis(vectors):
    piv={}
    for j,v in enumerate(vectors):
        x=int(v);comb=1<<j
        while x:
            p=x.bit_length()-1
            if p in piv:old,c=piv[p];x^=old;comb^=c
            else:piv[p]=(x,comb);break
    return piv

def code(n,degree):
    masks=[m for m in range(16) if m.bit_count()<=degree]
    generators=[sum(1<<x for x in range(n) if x&m==m) for m in masks]
    piv=gf2_basis(generators);checks=[]
    for f in range(n):
        if f in piv:continue
        h=1<<f
        for p in sorted(piv):
            row=piv[p][0]
            if ((row^(1<<p))&h).bit_count()&1:h^=1<<p
        assert all((g&h).bit_count()%2==0 for g in generators)
        checks.append(h)
    assert len(gf2_basis(checks))==n-len(piv)
    columns=np.array([sum(1<<j for j,h in enumerate(checks) if h>>i&1) for i in range(n)],np.int64)
    return dict(n=n,degree=degree,masks=masks,generators=generators,piv=piv,checks=checks,columns=columns,dimension=len(piv))

def syndrome(parities,c):
    out=np.zeros(len(parities),np.int64)
    for i,col in enumerate(c['columns']):out^=parities[:,i].astype(np.int64)*col
    return out

def dp(parities,weights,c,batch=128):
    n=c['n'];states=1<<len(c['checks']);indices=np.arange(states);flips=np.zeros_like(parities,bool);costs=np.zeros(len(parities))
    for start in range(0,len(parities),batch):
        end=min(start+batch,len(parities));p=parities[start:end];w=weights[start:end]
        dist=np.full((len(p),states),np.inf);dist[:,0]=0.;history=[]
        for i,col in enumerate(c['columns']):
            alt=dist[:,indices^col]+w[:,i,None];take=alt<dist
            history.append(take);dist=np.minimum(dist,alt)
        syn=syndrome(p,c);rows=np.arange(len(p));costs[start:end]=dist[rows,syn]
        for i in range(n-1,-1,-1):
            take=history[i][rows,syn];flips[start:end,i]=take;syn^=take.astype(np.int64)*c['columns'][i]
        assert not np.any(syn)
        assert not np.any(syndrome(p^flips[start:end],c))
    return flips,costs

def reconstruct(pattern,c):
    x=int(pattern);coeff=0
    while x:
        p=x.bit_length()-1
        if p not in c['piv']:raise AssertionError('outside evaluation code')
        row,comb=c['piv'][p];x^=row;coeff^=comb
    result=0
    for j,g in enumerate(c['generators']):
        if coeff>>j&1:result^=g
    assert result==int(pattern)
    return coeff

def brute(parity,weights,c):
    # Enumerate every codeword (all 2048 possibilities for full RM(2,4)).
    basis=[r for r,_ in c['piv'].values()];values=[0]
    for v in basis:values += [x^v for x in values]
    initial=sum(int(x)<<i for i,x in enumerate(parity));best=np.inf
    for value in values:
        delta=value^initial;cost=sum(weights[i] for i in range(c['n']) if delta>>i&1)
        best=min(best,float(cost))
    return best,len(values)

def project(near,alternate,weights,degree):
    out=near.copy();records=[];total_cost=0.;count=0
    for n,starts in [(16,np.arange(0,(len(near)//16)*16,16)),(len(near)%16,np.array([(len(near)//16)*16]))]:
        if not n or not len(starts):continue
        c=code(n,degree);angles=near.shape[1]
        ai=np.repeat(starts,angles)[:,None]+np.arange(n)[None,:]
        ti=np.tile(np.arange(angles),len(starts))[:,None]
        p=(near[ai,ti]&1).astype(bool);w=weights[ai,ti]
        flip,cost=dp(p,w,c);out[ai,ti]=np.where(flip,alternate[ai,ti],near[ai,ti])
        for row in (p^flip):reconstruct(sum(int(x)<<i for i,x in enumerate(row)),c)
        expected,enumerated=brute(p[0],w[0],c)
        assert abs(expected-cost[0])<1e-10*max(1.,abs(expected))
        total_cost+=float(cost.sum());count+=int(flip.sum())
        records.append(dict(valid_rows=n,blocks=len(starts),degree=degree,dimension=c['dimension'],dual_checks=len(c['checks']),states=1<<len(c['checks']),bruteforce_codewords=enumerated,brute_cost=expected,dp_cost=float(cost[0]),flips=int(flip.sum()),weighted_extra=float(cost.sum()),polynomial_reconstruction=True))
    return out,dict(degree=degree,flips=count,weighted_extra=total_cost,codes=records)
