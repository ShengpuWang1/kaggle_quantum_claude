"""Low-3 split, all-low-cache, signed-gauge paired ANF lookup."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'playbook'/'exp'))
import numpy as np
import kickmix as km
from staged_b154.paired_anf import bits,make_plan,Plan
from staged_b154.validation_helpers import assert_independent,independent_truth
from partition3 import split_plan

def emit(plan):
 if plan.low_bits!=3 or plan.blocks is not None or plan.parity_scratch:raise ValueError('need in-place low3 plan')
 A=plan.addresses;J=plan.batch;brot=plan.brot
 if J!=5 or brot not in (7,8):raise ValueError('need five 7/8-bit words')
 low=[m for m in plan.cache_masks if m<8];high=[m for m in plan.cache_masks if m>=8]
 if len(low)>J:raise ValueError('not enough borrowed bits for low monomials')
 Q=(A-1).bit_length()+J*brot+len(high)
 if Q>128:raise ValueError(f'cache uses {Q} qubits')
 b=km.CircuitBuilder();selection=b.create_quantum_register((A-1).bit_length(),'selection')
 words=[b.create_quantum_register(brot,f'word_{j}') for j in range(J)]
 targets=[q for word in words for q in word];borrowed=[w[-1] for w in words]
 keep=((1<<(J*brot))-1)^sum(1<<(brot*j+brot-1)for j in range(J))
 for w in words:b.cx(w[-2],w[-1])
 cache={0:True,**{1<<i:q for i,q in enumerate(selection)}}
 pool=b.alloc_qubits(len(high))
 for m,q in zip(low+high,borrowed[:len(low)]+list(pool)):
  top=1<<(m.bit_length()-1);b.init_and(cache[m^top],cache[top],q);cache[m]=q
 for p in plan.products:
  aa={cache[m].id for m in bits(p.left1)}|{cache[h<<3].id for h in bits(p.right2)}
  bb={cache[m].id for m in bits(p.left2)}|{cache[h<<3].id for h in bits(p.right1)}
  assert aa and bb and aa!=bb
  pp=min(aa);use_a=pp in bb;bprime=bb^aa if use_a else bb;assert bprime;qq=min(bprime)
  ops=[(km.q(t),km.q(pp)) for t in sorted(aa-{pp})]
  ops.extend((km.q(t),km.q(qq)) for t in sorted(bprime-{qq}))
  if use_a:ops.append((km.q(pp),km.q(qq)))
  for control,target in ops:b.cx(control,target)
  out=list(bits(p.fanout&keep));assert out;pivot=targets[out[0]]
  assert pivot.id not in aa|bb
  for k in out[1:]:b.cx(pivot,targets[k])
  b.ccx(km.q(pp),km.q(qq),pivot)
  for k in out[1:]:b.cx(pivot,targets[k])
  for control,target in reversed(ops):b.cx(control,target)
 for m,fan in plan.pure.items():
  for k in bits(fan&keep):b.cx(cache[m],targets[k])
 for m in reversed(low+high):
  top=1<<(m.bit_length()-1);b.del_and(cache[m^top],cache[top],cache[m])
 b.free(pool)
 for w in words:b.cx(w[-2],w[-1])
 c=b.finish_circuit();T=len(low)+len(high)+len(plan.products)
 assert int(c.num_qubits)==Q and int(c.operation_statistics().num_toffoli_like)==T
 return c,dict(T=T,Q=Q,low_cache=len(low),high_cache=len(high),products=len(plan.products),low_bits=3,borrowed=5,promise_top_two_bits_equal=True)

def build_delta(delta,brot=8,plan=None,share_odd=True):
 d=np.asarray(delta,np.int64);A,J=d.shape
 if J!=5 or brot not in (7,8) or np.any(d<0) or np.any(d>=1<<brot) or np.any((d>>(brot-1))!=((d>>(brot-2))&1)):
  raise ValueError('need D x 5 signed-gauge table, 7 or 8 bits')
 if plan is None:plan=make_plan(d,brot,3,share_odd=share_odd,in_place_parity=True)
 assert_independent(plan,d)
 if plan.blocks is None:
  try:
   c,m=emit(plan)
   return c,m,plan,None
  except ValueError as e:
   if 'qubits' not in str(e):raise
  capacity=128-(A-1).bit_length()-5*brot
  high=[m for m in plan.cache_masks if m>=8]
  threshold=next(t for t in range((A-1)//8,0,-1) if sum((m>>3)<t for m in high)<=capacity)
  first,_=split_plan(plan,threshold)
  vals=independent_truth(first);mask=(1<<brot)-1
  residual=np.array([[int(d[a,j]) ^ ((vals[a]>>(brot*j))&mask) for j in range(5)] for a in range(A)],dtype=np.int64)
  second=make_plan(residual,brot,3,share_odd=True,in_place_parity=True)
  assert_independent(second,residual)
  plan=Plan(A,5,brot,3,[],{},[],[],blocks=[first,second])
  assert_independent(plan,d)
 c0,m0=emit(plan.blocks[0]);c1,m1=emit(plan.blocks[1])
 extra='\n'.join(line for line in str(c1).splitlines() if not line.startswith(('APPEND_TO_REGISTER ','REGISTER ')))
 c=km.Circuit(str(c0)+'\n'+extra+'\n')
 m=dict(T=m0['T']+m1['T'],Q=max(m0['Q'],m1['Q']),products=m0['products']+m1['products'],
        low_cache=[m0['low_cache'],m1['low_cache']],high_cache=[m0['high_cache'],m1['high_cache']],
        low_bits=3,borrowed=5,partitioned=True,promise_top_two_bits_equal=True)
 assert int(c.num_qubits)==m['Q'] and int(c.operation_statistics().num_toffoli_like)==m['T']
 return c,m,plan,None

def protected_rank_plan(delta,brot):
 """Process affine coded outputs first, preserving their cheap output basis."""
 from staged_b154.paired_anf import anf,coefficient_polys,matrix,Product
 d=np.asarray(delta,np.int64);a=len(d);polys=coefficient_polys(anf(d,brot),5*brot)
 def affine(poly):
  cols,_,_=matrix(poly,3,a)
  return all(not (col & sum(1<<l for l in range(1,8) if l.bit_count()>1)) for col in cols)
 order=[i for i,p in enumerate(polys) if affine(p)]+[i for i,p in enumerate(polys) if not affine(p)]
 p=make_plan(d,brot,3,share_odd=True,in_place_parity=True,poly_override=[polys[i] for i in order])
 def remap(fan):return sum(1<<order[i] for i in bits(fan))
 p.products=[Product(q.left1,q.right1,q.left2,q.right2,remap(q.fanout)) for q in p.products]
 p.pure={m:remap(f) for m,f in p.pure.items()}
 assert_independent(p,d)
 return p

def choose_delta(delta,seconds=10,seed=772601,brot=8):
 """Return best exact low3 candidate; `seconds` bounds template search."""
 import time,template3
 started=time.time();winner=build_delta(delta,brot);chosen='paired_rank';proofs={}
 def left():return max(0,seconds-(time.time()-started))
 def consider(p,label,proof):
  nonlocal winner,chosen
  proofs[label]=proof
  if p is None:return
  candidate=build_delta(delta,brot,plan=p)
  if candidate[1]['T']<winner[1]['T']:winner=candidate;chosen=label
 p=template3.SparseProblem(delta,brot)
 if p.zeros:
  q=protected_rank_plan(delta,brot);consider(q,'protected_rank',dict(zeros=len(p.zeros)))
 if p.zeros and left()>0:
  q,proof=template3.sparse_search(delta,seconds=(.3 if brot==7 else .6)*left(),brot=brot,seed=seed);consider(q,'sparse_template',proof)
  if brot==7 and chosen!='sparse_template' and left()>0:
   q,proof=template3.sparse_search(delta,seconds=.6*left(),brot=brot,seed=seed,base=0,extra=4);consider(q,'sparse_relaxed',proof)
 if left()>0:
  q,proof=template3.search(delta,seconds=left(),brot=brot,relations_per_block=3 if brot==8 else 2);consider(q,'ordinary_template',proof)
 c,m,plan,sched=winner
 return c,dict(**m,selected=chosen,proofs=proofs,seconds=time.time()-started),plan,sched
