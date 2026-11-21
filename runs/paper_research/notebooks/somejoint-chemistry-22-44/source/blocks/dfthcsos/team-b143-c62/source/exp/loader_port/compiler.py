"""Variable-address, 7/8-bit promised signed-gauge lookup compiler.

The outputs are only valid for signed-gauge input targets, as in playbook.
Import this directory on sys.path, then import compiler. All plans are audited.
"""
import sys,time
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'playbook'/'exp'))
from staged_b154 import template_snapshot as g
from staged_b154.coded_helpers import code_diagnostics
from staged_b154.validation_helpers import assert_independent
from staged_b154.scheduler import product_requirement
from planning import row_plan, schedule
from emitter import build_staged
from partition import split_plan
from staged_b154.paired_anf import Plan
from staged_b154.emitter import high_masks
import kickmix as km

class SparseProblem(g.TensorProblem):
 def __init__(self,delta,brot,extra):
  super().__init__(delta,brot=brot,relations_per_block=5 if brot==8 else 4)
  self.zeros=[self.m*v+j for v in range(15) if (v+1).bit_count()>1 for j in range(self.m) if self.columns[self.m*v+j]==0]
  self.extra=4 if (15*self.m-len(self.zeros)-60)%2==0 else 3
  extra=self.extra
  self.zero_set=set(self.zeros);self.relation_count=len(self.zeros)+60+extra
  self.target_dimension=15*self.m-self.relation_count
  assert self.target_dimension>0 and self.target_dimension%2==0
  self.template_target=self.target_dimension//2
 def relations(self,order,seed):
  rng=np.random.default_rng(seed);relations=[1<<i for i in self.zeros];piv={}
  for r in relations:assert g.insert(r,piv)
  blocks=[[order[(s+j)%15] for j in range(3)] for s in range(15)]
  counts=[sum((v+1).bit_count()==1 for v in b) for b in blocks]; priorities=rng.random(15)
  raised=set(sorted(range(15),key=lambda s:(-counts[s],priorities[s]))[:self.extra]);dimensions=[]
  for s,vertices in enumerate(blocks):
   active=[self.m*v+j for v in vertices for j in range(self.m) if self.m*v+j not in self.zero_set]
   kernel=g.nullspace([self.columns[i] for i in active]);dimensions.append(len(kernel));needed=4+int(s in raised);found=0
   for _ in range(500):
    local=g.combination(kernel,rng);embedded=g.xor(1<<active[i] for i in g.bits(local))
    if g.insert(embedded,piv):relations.append(embedded);found+=1
    if found==needed:break
   if found!=needed:return None,dict(reason='active local independence shortfall',block=s,rank=len(piv))
  assert len(piv)==self.relation_count and all(not((r&t).bit_count()&1) for r in relations for t in self.rows)
  return relations,dict(structural_zero_relations=len(self.zeros),local_kernel_dimensions=dimensions,relation_count=len(relations))

def validate(delta,brot):
 delta=np.asarray(delta,np.int64)
 if brot not in (7,8) or delta.ndim!=2 or delta.shape[1]!=5 or not 2<=len(delta)<=1400 or np.any(delta<0) or np.any(delta>=1<<brot) or np.any((delta>>(brot-1))!=((delta>>(brot-2))&1)):
  raise ValueError('need D x 5 signed-gauge table, 2<=D<=1400 and brot 7 or 8')
 return delta

def build_delta(delta,plan=None,saved_schedule=None,seconds=0,brot=8):
 delta=validate(delta,brot)
 route='provided_exact_plan'
 if plan is None and seconds>0:
  plan,proof=g.search(delta,seconds=seconds,brot=brot,relations_per_block=5 if brot==8 else 4);route='ordinary_template'
 if plan is None or max((product_requirement(x).bit_count() for x in plan.products),default=0)>8:
  plan=row_plan(delta,brot);route='sparse_row_fallback';saved_schedule=None
 if (plan.addresses,plan.batch,plan.brot)!=(len(delta),5,brot):raise ValueError('plan/table dimensions disagree')
 assert_independent(plan,delta)
 capacity=128-(len(delta)-1).bit_length()-5*brot-3
 if len(high_masks(len(delta)))<=capacity:
  sched=saved_schedule or schedule(plan,8)
  circuit,meta=build_staged(plan,sched)
 else:
  # Preserve correctness at the cache cliff by splitting products into two
  # exact polynomials and recomputing each part with its own high cache.
  threshold=next(t for t in range((len(delta)-1)//16,0,-1)
                 if sum(1 for m in high_masks(len(delta)) if (m>>4)<t)<=capacity)
  parts=split_plan(plan,threshold);combined=Plan(len(delta),5,brot,4,[],{},[],[],blocks=parts)
  assert_independent(combined,delta)
  sched=saved_schedule or [schedule(p,8) for p in parts]
  emissions=[build_staged(p,sc) for p,sc in zip(parts,sched)]
  # Register declarations occur only in first text; all public qubits and
  # classical measurement slots have identical indices in the next stage.
  prefix=str(emissions[0][0]);extra='\n'.join(line for line in str(emissions[1][0]).splitlines() if not line.startswith(('APPEND_TO_REGISTER ','REGISTER ')))
  circuit=km.Circuit(prefix+'\n'+extra+'\n')
  metas=[x[1] for x in emissions]
  meta=dict(addresses=len(delta),high_cache=[m['high_cache'] for m in metas],low_slots=8,
       products=sum(m['products'] for m in metas),T=sum(m['T'] for m in metas),
       Q=max(m['Q'] for m in metas),partition_threshold=threshold,partitioned=True,
       promise_top_two_bits_equal=True)
  assert int(circuit.num_qubits)==meta['Q'] and int(circuit.operation_statistics().num_toffoli_like)==meta['T']
 return circuit,dict(route=route,**meta),plan,sched

def sparse_search(delta,seconds,seed,brot):
 p=SparseProblem(delta,brot,4 if brot==8 else 3);rng=np.random.default_rng(seed);started=time.time();attempts=0
 for oi in range(10000):
  order=([0,1,3,7]+[i for i in range(15) if i not in (0,1,3,7)]) if oi==0 else list(map(int,rng.permutation(15)))
  for rs in range(8):
   if time.time()-started>=seconds:return None,dict(reason='time budget',attempts=attempts)
   attempts+=1;rels,rm=p.relations(order,rs)
   if rels is None:continue
   space=g.TemplateSpace(p,rels,order)
   if space.quotient_available!=space.quotient_target or not space.single_span_full:continue
   chosen,sm=space.select(seed+8191*oi+rs,64)
   if chosen is None:continue
   plan,proof=g.compile_selected(p,rels,chosen)
   return plan,dict(verified=proof,order=order,relation_seed=rs,selection=sm,relations_metadata=rm,attempts=attempts)
 return None,dict(reason='orders exhausted',attempts=attempts)

def choose_delta(delta,seconds=60,seed=772601,brot=8):
 delta=validate(delta,brot); started=time.time();winner=build_delta(delta,brot=brot);chosen='sparse_row_fallback';proofs={}
 if seconds>0 and (len(delta)-1).bit_length()+5*brot+len(high_masks(len(delta)))+11<=136:
  # Sparse route recognizes any output's punctured affine column, not only LSBs.
  probe=SparseProblem(delta,brot,0);coded=bool(probe.zeros)
  if coded:p,proof=sparse_search(delta,seconds*.65,seed,brot);name='sparse_RM1'
  else:p,proof=g.search(delta,seconds=seconds,brot=brot,relations_per_block=5 if brot==8 else 4);name='ordinary_template'
  proofs[name]=proof
  if p is not None and max((product_requirement(x).bit_count() for x in p.products),default=0)<=8:
   candidate=build_delta(delta,p,brot=brot)
   if (candidate[1]['T'],candidate[1]['Q'])<(winner[1]['T'],winner[1]['Q']):winner=candidate;chosen=name
  if coded and chosen=='sparse_row_fallback' and time.time()-started<seconds:
   p,proof=protected_plan(delta,brot,seconds-(time.time()-started));proofs['protected']=proof
   if p is not None and max((product_requirement(x).bit_count() for x in p.products),default=0)<=8:
    candidate=build_delta(delta,p,brot=brot)
    if (candidate[1]['T'],candidate[1]['Q'])<(winner[1]['T'],winner[1]['Q']):winner=candidate;chosen='protected'
 circuit,meta,plan,sched=winner
 return circuit,dict(**meta,selected=chosen,proofs=proofs,RM1=code_diagnostics(delta,1)['valid'],seconds=time.time()-started),plan,sched

def protected_plan(delta,brot,seconds):
 """Protect all affine columns, synthesize remaining outputs, then add exact coded columns."""
 from staged_b154.paired_anf import anf,coefficient_polys,matrix,rank_decomposition,Product,poly_product,bits
 from staged_b154.emitter import high_masks
 a=len(delta);p=SparseProblem(delta,brot,0);affine=[]
 for j in range(p.m):
  if all(p.columns[p.m*v+j]==0 for v in range(15) if (v+1).bit_count()>1):affine.append(j)
 high=[j for j in range(p.m) if j not in affine]
 if not affine or not high:return None,dict(reason='no usable affine/protected partition')
 r=5 if len(high)%2 else 4
 hp,proof=g.search(delta,seconds=seconds,brot=brot,relations_per_block=r,output_indices=high)
 if hp is None:return None,dict(high=proof,affine=affine)
 polys=coefficient_polys(anf(delta,brot),5*brot);pure=dict(hp.pure);products=list(hp.products);H=(a-1)>>4
 def add(poly,fan,shift):
  for m in bits(poly):
   m<<=shift
   if m<a:pure[m]=pure.get(m,0)^fan
 for idx in affine:
  word,bit=divmod(idx,brot-1);fan=1<<(word*brot+bit)
  if bit==brot-2:fan|=1<<(word*brot+brot-1)
  cols,lo,hi=matrix(polys[word*brot+bit],4,a);factors=rank_decomposition(cols)
  for t in range(0,len(factors),2):
   l1,r1=factors[t];l2,r2=factors[t+1] if t+1<len(factors) else (0,0)
   products.append(Product(l1,r1,l2,r2,fan));lo^=poly_product(l1,l2,15);hi^=poly_product(r1,r2,H)
  add(lo,fan,0);add(hi,fan,4)
 cache=sorted([m for m in range(1,16) if m.bit_count()>=2]+high_masks(a))
 plan=Plan(a,5,brot,4,products,{m:v for m,v in pure.items() if v},[],cache,parity_scratch=0)
 assert_independent(plan,delta)
 return plan,dict(high=proof,affine=affine)
