"""Public portable 5-word promised-sign loader: auto-selects low3 / low4.

Example: sys.path.insert(0,'exp/loader_port'); import loader
    circ, metadata, plan, schedule = loader.choose_delta(delta, brot=8, seconds=20)
Tables contain integer words whose top two bits agree. All APIs emit a
promise-only XOR oracle, not a true XOR oracle on arbitrary target states.
"""
import time
import low3,compiler

def build_delta(delta,plan=None,saved_schedule=None,seconds=0,brot=8,low_bits=None):
 if plan is not None:low_bits=plan.low_bits
 if low_bits is None:low_bits=3 if len(delta)<=(752 if brot==7 else 720) else 4
 if low_bits==3:
  if seconds>0 and plan is None:return low3.choose_delta(delta,brot=brot,seconds=seconds)
  return low3.build_delta(delta,brot=brot,plan=plan)
 if low_bits==4:return compiler.build_delta(delta,plan=plan,saved_schedule=saved_schedule,seconds=seconds,brot=brot)
 raise ValueError('low_bits must be 3 or 4')

def choose_delta(delta,seconds=30,seed=772601,brot=8):
 start=time.time();a=len(delta)
 low3_fits=a<=(752 if brot==7 else 720)
 if low3_fits:
  # Low3 has fewer bilinear products and has consistently won at this scale.
  # Allocate almost all available search time to this route.
  winner=low3.choose_delta(delta,seconds=seconds,seed=seed,brot=brot)
 else:winner=compiler.choose_delta(delta,seconds=seconds,seed=seed,brot=brot)
 return winner
