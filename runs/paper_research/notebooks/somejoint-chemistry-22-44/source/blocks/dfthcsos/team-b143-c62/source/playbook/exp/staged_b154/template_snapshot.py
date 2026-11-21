"""Template planner: a full-width plan may use 136 virtual qubits;
borrowed-sign emitter must actually fit128. No generic compiler modified.
"""
"""Local right-kernel relations and paired-template basis compiler.

All Boolean algebra is over GF(2), packed in Python integers. Every search
candidate is verified; failure is bounded-search evidence only. No fallback
or shared compiler globals are modified.
"""
from pathlib import Path
import sys,time
from dataclasses import dataclass
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
from .paired_anf import anf,coefficient_polys,matrix,bits,Product,Plan,poly_product,rank_decomposition

def xor(xs):
    value=0
    for x in xs:value^=int(x)
    return value

def reduce(row,piv):
    while row:
        p=row.bit_length()-1
        if p not in piv:break
        row^=piv[p]
    return row

def insert(row,piv):
    row=reduce(row,piv)
    if not row:return False
    piv[row.bit_length()-1]=row;return True

def remainder(row,piv):
    # Full reduction, including non-leading known pivots. Standard insertion
    # stops at a novel leading bit; quotient coordinates must reduce all pivots.
    for p in sorted(piv,reverse=True):
        if row>>p&1:row^=piv[p]
    return row

def nullspace(columns):
    piv={};null=[]
    for j,value in enumerate(columns):
        row=int(value);comb=1<<j
        while row:
            p=row.bit_length()-1
            if p in piv:old,c=piv[p];row^=old;comb^=c
            else:piv[p]=(row,comb);break
        if not row:null.append(comb)
    return null

def combination(basis,rng):
    mask=int.from_bytes(rng.bytes((len(basis)+7)//8),'little')&((1<<len(basis))-1)
    return xor(basis[j] for j in bits(mask))

def directions(basis):
    if len(basis)>6:return list(basis)
    values=[0]
    for row in basis:values += [x^row for x in values]
    return values[1:]

def tensor(lowform,v,m=35):return xor(v<<(m*i) for i in bits(lowform))

@dataclass(frozen=True)
class Template:
    first: int
    second: int
    direction: int
    vertex: int = -1   # the single vertex of a neighbour-sum template

class TensorProblem:
    def __init__(self,delta,output_indices=None,relations_per_block=5,brot=8):
        self.delta=np.asarray(delta,np.int64).copy();self.A,self.J=self.delta.shape
        self.brot=int(brot)
        if self.brot not in (7,8) or self.J!=5 or np.any(self.delta<0) or np.any(self.delta>=(1<<self.brot)):raise ValueError('need five canonical7or8bit words')
        original=coefficient_polys(anf(self.delta,self.brot),5*self.brot);free=self.brot-1
        assert all(original[self.brot*j+self.brot-1]==original[self.brot*j+self.brot-2] for j in range(5))
        all_polys=[original[self.brot*j+b] for j in range(5) for b in range(free)]
        all_fans=[(1<<(self.brot*j+b))|((1<<(self.brot*j+self.brot-1)) if b==free-1 else 0) for j in range(5) for b in range(free)]
        self.output_indices=list(range(5*free)) if output_indices is None else list(map(int,output_indices))
        if not self.output_indices or len(set(self.output_indices))!=len(self.output_indices) or any(i<0 or i>=5*free for i in self.output_indices):raise ValueError('invalid raw free-output subset')
        self.polys=[all_polys[i] for i in self.output_indices];self.fans=[all_fans[i] for i in self.output_indices]
        self.m=len(self.polys);self.L=15;self.H=(self.A-1)>>4
        self.relations_per_block=int(relations_per_block);self.relation_count=15*self.relations_per_block
        self.target_dimension=15*self.m-self.relation_count
        if self.relations_per_block<1 or self.target_dimension<=0 or self.target_dimension%2:raise ValueError('need a positive even annihilator dimension')
        self.template_target=self.target_dimension//2
        self.rows=[sum(((p>>(l|(h<<4)))&1)<<(self.m*(l-1)+j) for l in range(1,16) for j,p in enumerate(self.polys)) for h in range(1,self.H+1)]
        self.columns=[sum(((row>>j)&1)<<h for h,row in enumerate(self.rows)) for j in range(15*self.m)]
    def relations(self,order,seed):
        rng=np.random.default_rng(seed);relations=[];piv={};dims=[]
        for start in range(15):
            vertices=[order[(start+j)%15] for j in range(3)]
            columns=[self.columns[self.m*v+j] for v in vertices for j in range(self.m)]
            kernel=nullspace(columns);dims.append(len(kernel));found=0
            for _ in range(500):
                local=combination(kernel,rng)
                embedded=xor(((local>>(self.m*j))&((1<<self.m)-1))<<(self.m*v) for j,v in enumerate(vertices))
                if insert(embedded,piv):relations.append(embedded);found+=1
                if found==self.relations_per_block:break
            if found!=self.relations_per_block:return None,dict(reason='local relations fail global independence',block=start,kernel_dimensions=dims,rank=len(piv))
        assert len(piv)==self.relation_count
        assert all(not((r&t).bit_count()&1) for r in relations for t in self.rows)
        return relations,dict(relation_rank=self.relation_count,annihilator_dimension=self.target_dimension,local_kernel_dimensions=dims)

class TemplateSpace:
    def __init__(self,problem,relations,order):
        self.problem=problem;self.relations=relations;self.order=list(order);columns=[0]*(15*problem.m)
        for j,row in enumerate(relations):
            for i in bits(row):columns[i]|=1<<j
        single=[columns[problem.m*v:problem.m*(v+1)] for v in range(15)]
        self.V=[nullspace(s) for s in single];self.Vpiv=[]
        for basis in self.V:
            piv={}
            for value in basis:assert insert(value,piv)
            self.Vpiv.append(piv)
        self.pairs={};self.Wpiv=[{} for _ in range(15)];pair_dims=[]
        for a in range(15):
            for b in range(a+1,15):
                basis=nullspace([x|(y<<problem.relation_count) for x,y in zip(single[a],single[b])]);values=directions(basis)
                self.pairs[a,b]=values;pair_dims.append(len(basis))
                for v in values:insert(v,self.Wpiv[a]);insert(v,self.Wpiv[b])
        self.Wdim=sum(map(len,self.Wpiv));self.quotient_target=problem.target_dimension-self.Wdim
        sums=sorted({tuple(sorted((order[i],order[(i+d)%15]))) for i in range(15) for d in (1,2)})
        assert len(sums)==30
        self.sums=[];sum_dims=[];quotient_piv={};self.single_span_full=all(len(a)==len(b) for a,b in zip(self.Wpiv,self.Vpiv))
        for a,b in sums:
            syn=[x^y for x,y in zip(single[a],single[b])]
            for c in range(15):
                if c in (a,b):continue
                basis=nullspace([x|(y<<problem.relation_count) for x,y in zip(syn,single[c])]);sum_dims.append(len(basis))
                for v in directions(basis):
                    template=Template((1<<a)|(1<<b),1<<c,v,c)
                    # Sum-leg coordinates modulo the direct-sum W0.
                    q=tensor(1<<a,remainder(v,self.Wpiv[a]),problem.m)^tensor(1<<b,remainder(v,self.Wpiv[b]),problem.m)
                    if q:self.sums.append((template,q));insert(q,quotient_piv)
        self.quotient_available=len(quotient_piv)
        self.metadata=dict(single_vertex_dimensions=list(map(len,self.Vpiv)),W0_vertex_dimensions=list(map(len,self.Wpiv)),
            W0_dimension=self.Wdim,quotient_target=self.quotient_target,quotient_available=self.quotient_available,
            single_span_full=self.single_span_full,single_pair_templates=sum(map(len,self.pairs.values())),
            sum_templates=len(self.sums),single_pair_kernel_dimensions=pair_dims,sum_pair_kernel_dimensions=sum_dims)
    def select(self,seed,trials=64):
        if not self.single_span_full:return None,dict(reason='single templates do not span all single-vertex directions',**self.metadata)
        if self.quotient_available!=self.quotient_target:return None,dict(reason='template quotient rank shortfall',**self.metadata)
        best=dict(stage1_rank=0,total_templates=0);records=[]
        for trial in range(trials):
            rng=np.random.default_rng(seed+1000003*trial);selected=[];pivs=[{} for _ in range(15)];quotient={}
            for index in rng.permutation(len(self.sums)):
                template,q=self.sums[int(index)];v=template.direction;c=template.vertex
                if not reduce(q,quotient) or not reduce(v,pivs[c]):continue
                assert insert(q,quotient) and insert(v,pivs[c]);selected.append(template)
                if len(quotient)==self.quotient_target:break
            if len(quotient)!=self.quotient_target:
                record=dict(trial=trial,reason='stage1 greedy shortfall',stage1_rank=len(quotient),templates=len(selected))
            else:
                while sum(map(len,pivs))<self.Wdim:
                    deficits=[len(self.Wpiv[a])-len(pivs[a]) for a in range(15)]
                    pairs=[(a,b) for a,b in self.pairs if deficits[a]>0 and deficits[b]>0]
                    # Largest combined remaining deficit, random tie order.
                    pairs=sorted(pairs,key=lambda ab:(-(deficits[ab[0]]+deficits[ab[1]]),rng.random()))
                    found=False
                    for a,b in pairs:
                        values=self.pairs[a,b]
                        for j in rng.permutation(len(values)):
                            v=values[int(j)]
                            if reduce(v,pivs[a]) and reduce(v,pivs[b]):
                                assert insert(v,pivs[a]) and insert(v,pivs[b])
                                selected.append(Template(1<<a,1<<b,v));found=True;break
                        if found:break
                    if not found:break
                done=sum(map(len,pivs))==self.Wdim
                record=dict(trial=trial,reason='success' if done else 'stage2 greedy shortfall',stage1_rank=len(quotient),
                    templates=len(selected),vertex_deficits=[len(self.Wpiv[a])-len(pivs[a]) for a in range(15)])
                if done:
                    assert len(selected)==self.problem.template_target
                    piv={}
                    for template in selected:
                        for low in (template.first,template.second):assert insert(tensor(low,template.direction,self.problem.m),piv)
                    assert len(piv)==self.problem.target_dimension
                    return selected,dict(trial=trial,selection_rank=self.problem.target_dimension,stage1_templates=self.quotient_target,
                        stage2_templates=self.problem.template_target-self.quotient_target,trials=records+[record],**self.metadata)
            records.append(record)
            if (record['stage1_rank'],record['templates'])>(best['stage1_rank'],best['total_templates']):best=dict(stage1_rank=record['stage1_rank'],total_templates=record['templates'])
        return None,dict(reason='bounded64 selection failed',best=best,trials=records,**self.metadata)

def compile_selected(problem,relations,templates):
    vectors=[tensor(low,t.direction,problem.m) for t in templates for low in (t.first,t.second)];piv={}
    for j,original in enumerate(vectors):
        assert all(not((original&r).bit_count()&1) for r in relations)
        row=original;coord=1<<j
        while row:
            bit=row.bit_length()-1
            if bit not in piv:piv[bit]=(row,coord);break
            old,c=piv[bit];row^=old;coord^=c
        assert row
    assert len(piv)==problem.target_dimension
    high=[0]*problem.target_dimension
    for h,original in enumerate(problem.rows,1):
        row=original;coord=0
        while row:
            bit=row.bit_length()-1;old,c=piv[bit];row^=old;coord^=c
        assert xor(vectors[j] for j in bits(coord))==original
        for j in bits(coord):high[j]|=1<<h
    pure={}
    def add(poly,fan,shift):
        for mask in bits(poly):
            globalmask=mask<<shift
            if globalmask<problem.A:pure[globalmask]=pure.get(globalmask,0)^fan
    for poly,fan in zip(problem.polys,problem.fans):
        _,lo,hi=matrix(poly,4,problem.A);add(lo,fan,0);add(hi,fan,4)
    products=[]
    for j,t in enumerate(templates):
        h1,h2=high[2*j:2*j+2]
        if not(h1 or h2):continue
        low1=sum(1<<(i+1) for i in bits(t.first));low2=sum(1<<(i+1) for i in bits(t.second))
        fan=xor(problem.fans[i] for i in bits(t.direction));products.append(Product(low1,h1,low2,h2,fan))
        add(poly_product(low1,low2,15),fan,0);add(poly_product(h1,h2,problem.H),fan,4)
    cache=sorted([m for m in range(1,16) if m.bit_count()>=2]+[h<<4 for h in range(1,problem.H+1) if h.bit_count()>=2])
    plan=Plan(problem.A,5,problem.brot,4,products,{m:f for m,f in pure.items() if f},[],cache,parity_scratch=0)
    assert plan.toffoli<=len(cache)+problem.template_target and plan.qubits<=136
    return plan,dict(exact_tensor_reconstruction=True,selected_basis_rank=problem.target_dimension,templates=problem.template_target,
        output_indices=problem.output_indices,m=problem.m,brot=problem.brot,relations_per_block=problem.relations_per_block,relation_count=problem.relation_count,
        products=len(products),cache=len(cache),T=plan.toffoli,Q=plan.qubits,
        relations=list(relations),
        selected=[dict(first=t.first,second=t.second,direction=t.direction) for t in templates])

def rebuild(delta,metadata):
    verified=metadata['verified'];templates=[Template(**x) for x in verified['selected']]
    return compile_selected(TensorProblem(delta,verified.get('output_indices'),verified.get('relations_per_block',5),verified.get('brot',8)),verified['relations'],templates)

def search(delta,seconds=600,orders=100,trials=64,callback=None,*,output_indices=None,relations_per_block=5,brot=8):
    started=time.time();problem=TensorProblem(delta,output_indices,relations_per_block,brot);history=[];rng=np.random.default_rng(903271)
    for order_index in range(orders):
        order=list(range(15)) if order_index==0 else list(map(int,rng.permutation(15)))
        for relation_seed in range(8):
            if time.time()-started>=seconds:return None,dict(reason='time budget',history=history,elapsed=time.time()-started)
            relations,relmeta=problem.relations(order,relation_seed)
            if relations is None:
                history.append(dict(order_index=order_index,relation_seed=relation_seed,relations=relmeta));continue
            space=TemplateSpace(problem,relations,order)
            chosen,meta=space.select(99173+relation_seed+8191*order_index,trials)
            record=dict(order_index=order_index,order=order,relation_seed=relation_seed,relations=relmeta,
                selection=meta,elapsed=time.time()-started);history.append(record)
            if callback:callback(record)
            if chosen is not None:
                plan,verified=compile_selected(problem,relations,chosen)
                return plan,dict(history=history,verified=verified,elapsed=time.time()-started)
    return None,dict(reason='bounded orders exhausted',history=history,elapsed=time.time()-started)
