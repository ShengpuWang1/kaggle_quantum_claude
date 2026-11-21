"""Split high-cache pressure into two exact staged signed-gauge passes."""
from staged_b154.paired_anf import Plan,Product,bits,poly_product

def split_plan(plan,threshold=64):
 A=plan.addresses;H=(A-1)>>4; stages=[dict(products=[],pure={}),dict(products=[],pure={})]
 def addpure(mask,fan):
  if mask>=A:return
  i=int((mask>>4)>=threshold);p=stages[i]['pure'];p[mask]=p.get(mask,0)^fan
 for mask,fan in plan.pure.items():addpure(mask,fan)
 def maskpart(v,part):
  return sum(1<<h for h in bits(v) if (h>=threshold)==bool(part))
 for p in plan.products:
  aa=[maskpart(p.right1,k) for k in (0,1)];bb=[maskpart(p.right2,k) for k in (0,1)]
  for k in (0,1):
   x=p.left1|(bb[k]<<16);y=p.left2|(aa[k]<<16)
   if not x or not y:continue
   if x==y:
    for l in bits(p.left1):addpure(l,p.fanout)
    for h in bits(bb[k]):addpure(h<<4,p.fanout)
   else:stages[k]['products'].append(Product(p.left1,aa[k],p.left2,bb[k],p.fanout))
  for l in bits(poly_product(p.left1,p.left2,15)):addpure(l,p.fanout)
  corr=poly_product(aa[0],bb[1],H)^poly_product(aa[1],bb[0],H)
  for h in bits(corr):addpure(h<<4,p.fanout)
 out=[]
 for stage in stages:
  pure={m:v for m,v in stage['pure'].items() if v};used=set(m for m in pure if m>=16)
  for p in stage['products']:
   used.update(h<<4 for h in bits(p.right1|p.right2))
  for m in list(used):
   while (m>>4).bit_count()>=2:
    used.add(m);h=m>>4;m=(h^(1<<(h.bit_length()-1)))<<4
  high=sorted(m for m in used if (m>>4).bit_count()>=2)
  cache=sorted([m for m in range(1,16) if m.bit_count()>=2]+high)
  out.append(Plan(A,5,plan.brot,4,stage['products'],pure,[],cache,parity_scratch=0))
 return out
