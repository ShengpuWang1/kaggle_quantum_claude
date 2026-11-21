"""Bounded deterministic coverage beam over53closed eight-slot phase caches.

Each phase executes all currently available product requirements. This searches
only a prescribed maximal-cache phase family; every returned order is then
rechecked by the exact fixed-order retention DP and the emitter.
"""
from .scheduler import states_and_cost,product_requirement,closure

def orders(plan,capacity=8,width=64,max_depth=8):
    req=sorted(set([product_requirement(p)for p in plan.products]+[closure([m])for m,v in plan.pure.items()if v and m<16 and m.bit_count()>=2]))
    states,_=states_and_cost(capacity);states=[int(s)for s in states if int(s).bit_count()==capacity]
    full=(1<<len(req))-1
    cover=[sum(1<<j for j,r in enumerate(req)if r&~s==0)for s in states]
    need_vertices=[r for r in req];beam=[(0,0,0,())];solutions=[];expanded=0
    for depth in range(1,max_depth+1):
        candidates={}
        for oldcov,oldstate,cost,path in beam:
            for si,S in enumerate(states):
                cov=oldcov|cover[si]
                if cov==oldcov:continue
                newcost=cost+(S&~oldstate).bit_count();newpath=path+(si,);expanded+=1
                if cov==full:solutions.append((newcost,newpath));continue
                key=(cov,si);prior=candidates.get(key)
                if prior is None or newcost<prior[2]:candidates[key]=(cov,S,newcost,newpath)
        if not candidates:break
        def key(row):
            cov,S,cost,path=row;unseen=full^cov;needed=0
            while unseen:
                bit=unseen&-unseen;needed|=need_vertices[bit.bit_length()-1];unseen^=bit
            lb=(needed&~S).bit_count()
            return(cost+lb,-cov.bit_count(),cost,path)
        beam=sorted(candidates.values(),key=key)[:width]
        if solutions and depth>=min(c for c,_ in solutions)-capacity+1:break
    solutions.sort();unique=[];seen=set()
    for cost,path in solutions:
        order=[];done=set()
        for si in path:
            S=states[si]
            for i,p in enumerate(plan.products):
                if i not in done and product_requirement(p)&~S==0:order.append(i);done.add(i)
        if len(done)!=len(plan.products):continue
        order=tuple(order)
        if order in seen:continue
        seen.add(order);unique.append(dict(order=list(order),phase_cost=cost,phase_states=[states[i]for i in path]))
        if len(unique)>=8:break
    return unique,dict(width=width,max_depth=max_depth,maximal_cache_states=len(states),requirements=len(req),
        expanded=expanded,complete_paths=len(solutions),retained_orders=len(unique),globally_optimal_claim=False)
