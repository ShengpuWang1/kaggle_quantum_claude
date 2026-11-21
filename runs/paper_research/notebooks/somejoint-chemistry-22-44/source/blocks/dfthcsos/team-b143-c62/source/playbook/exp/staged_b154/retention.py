"""Fixed-order exact retention DP, with commuting pure-low CNOTs eager."""
from .paired_anf import Plan
from .scheduler import optimize_cache,closure,members,audit

def optimize(plan,order,capacity=8,label='eager'):
    # The old DP is unchanged; omitting its terminal pure map removes the
    # artificial requirement to retain/reload all pure nodes after products.
    no_pure=Plan(plan.addresses,plan.batch,plan.brot,plan.low_bits,list(plan.products),{},list(plan.ranks),list(plan.cache_masks),parity_scratch=plan.parity_scratch)
    base=optimize_cache(no_pure,order,capacity,label)
    pending={m for m,v in plan.pure.items()if v and m<16 and m.bit_count()>=2};events=[]
    for event in base['events']:
        S=event['cache']
        for m in sorted(pending&set(members(S))):
            events.append(dict(kind='pure_low',monomial=m,required=closure([m]),cache=S));pending.remove(m)
        events.append(dict(event))
    # General fallback if a pure monomial does not occur in any product cache.
    for m in sorted(pending,reverse=True):events.append(dict(kind='pure_low',monomial=m,required=closure([m]),cache=closure([m])))
    base['events']=events;base['pure_low_eager']=True
    prev=0;count=0
    for e in events:count+=(e['cache']&~prev).bit_count();prev=e['cache']
    base['low_computations']=count;base['peak_live']=max([e['cache'].bit_count()for e in events]+[0])
    check=audit(plan,base);check['pure_low_deferred']=False;check['pure_low_eager']=True
    return base,check
