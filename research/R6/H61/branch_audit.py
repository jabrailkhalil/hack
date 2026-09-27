"""Passive executed-path/clip tracing of original H44 scalar observer."""
import sys,hashlib
from collections import Counter
import numpy as np
from reserve_odometry.core import Observer,clip
from reserve_odometry.guarded_readout import GuardedReadoutObserver

class BranchAudit:
 def __init__(self,nwin,nticks=201):
  self.nwin=nwin;self.nticks=nticks;self.tick=-1;self.path=[];self.rows=[Counter() for _ in range(nwin)];self.paths=np.zeros((nwin,nticks),dtype='S16');self.previous={}
  functions=[Observer.step,Observer.drive_target,Observer.resistance,Observer._wheel,Observer._valid,Observer._take_pending_pair,Observer._clear_reacquire,Observer._reacquire_pair,Observer._output,GuardedReadoutObserver.step]
  self.codes={f.__code__:i for i,f in enumerate(functions)}
 def __enter__(self):
  self.old=sys.gettrace();sys.settrace(self.trace);return self
 def __exit__(self,*args):sys.settrace(self.old)
 def trace(self,f,event,arg):
  code=f.f_code
  if event=='call':
   if code is GuardedReadoutObserver.step.__code__:
    self.tick+=1;self.path=[]
   if code in self.codes:return self.trace
   if code is clip.__code__:f.f_trace_lines=False;return self.trace
   return None
  if self.tick<0:return self.trace
  w,k=divmod(self.tick,self.nticks);c=self.rows[w]
  if event=='line' and code in self.codes:self.path.append(1000*self.codes[code]+f.f_lineno)
  if event=='return':
   q=f.f_locals
   if code is clip.__code__:
    state=-1 if q['x']<q['lo'] else 1 if q['x']>q['hi'] else 0
    self.path.extend([20000+f.f_back.f_lineno,21000+state]);c['clip_'+str(state)]+=1
    cfg=f.f_back.f_locals.get('c',None)
    if cfg is not None and state:
     if q['hi']==cfg.max_speed_mps and q['lo']==-cfg.max_speed_mps:c['speed_clipping']+=1
     if q['hi']==cfg.max_accel_mps2 and q['lo']==-cfg.max_accel_mps2:c['acceleration_clipping']+=1
   elif code is Observer.drive_target.__code__ and 'force' in q:
    cfg=q['c'];power=cfg.max_power_w/max(abs(q['v']),1.);force=cfg.efficiency*cfg.gear_ratio*cfg.total_motor_torque_nm/cfg.wheel_radius_m
    state=0 if force<power else 1 if power<force else 2;self.path.append(22000+state);c['drive_limit_'+('force','power','tie')[state]]+=1
   elif code is Observer.step.__code__:
    c['zero_lock']+=bool(q.get('zero_pair',False));c['zero_crossing']+=bool(q.get('u',1)<=q['c'].command_deadband and q.get('previous_v',0)*(q.get('previous_v',0)+q.get('dt',0)*q.get('a_model',0))<0)
   elif code is GuardedReadoutObserver.step.__code__:
    e=arg;o=q['self'];part='warmup' if k<=100 else 'forecast'
    c['mode_'+e.mode]+=1;c[part+'_mode_'+e.mode]+=1
    for ch,stat in [('front',e.front_status),('rear',e.rear_status)]:c[ch+'_'+stat]+=1
    c['mode_transitions']+=int(w in self.previous and self.previous[w]!=e.mode);self.previous[w]=e.mode
    c['quarantine_active']+=int(e.t<o.reacquire_blocked_until);c['reacquire_state_active']+=int(o.reacquire_since is not None)
    c['readout_healthy']+=bool(q.get('healthy',False));c['readout_holdoff']+=bool(e.t<o._blocked_until);c['readout_nonzero']+=int(o._velocity_correction!=0)
    c['output_ticks']+=1
    self.path.extend([23000+int(np.sign(e.v)),24000+int(o.reacquire_since is not None),25000+int(e.t<o.reacquire_blocked_until)])
    self.paths[w,k]=hashlib.blake2b(np.asarray(self.path,dtype=np.uint16).tobytes(),digest_size=8).hexdigest().encode()
  return self.trace
