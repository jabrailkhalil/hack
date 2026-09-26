"""One fixed GNSS-only offline policy. Never import observer or vehicle data."""
import numpy as np

REASONS = {name: 1 << i for i, name in enumerate((
    'MISSING_MASTER', 'MISSING_ROVER', 'NONFINITE_VELOCITY',
    'CONFLICTING_DUPLICATE', 'PAIRING_AMBIGUITY', 'SPEED_DISAGREEMENT',
    'VELOCITY_FRAME_MISMATCH', 'MISSING_FIX', 'INVALID_FIX',
    'TEMPORAL_JUMP', 'BAD_SOURCE_TIME'))}
FLAGS = {name: 1 << i for i, name in enumerate((
    'BOTH_ZERO', 'ONE_ZERO', 'ZERO_VS_GT2', 'EXACT_PAIR', 'NEAR_PAIR',
    'UNKNOWN_COVARIANCE', 'ZERO_COVARIANCE', 'ALTITUDE_UNKNOWN',
    'GAP_BEFORE', 'ISOLATED_ZERO', 'DUPLICATE_COLLAPSED', 'SOURCE_REORDERED'))}
POLICY = {'id':'R5-H42-teacher-v1','version':1, 'offline_only':True,
    'target':'mean of two horizontal speed magnitudes in m/s',
    'pair_tolerance_ns':50_000_000,'fix_tolerance_ns':200_000_000,
    'agreement_absolute_mps':0.30,'agreement_relative':0.02,
    'temporal_max_gap_ns':500_000_000,'temporal_jump_margin_mps':0.5,
    'temporal_acceleration_mps2':8.0,'uses_future_GNSS_history':True,
    'fitted_scales':False,'canonical_reference_mask_replaced':False,
    'single_receiver_fallback':False,'reasons':REASONS,'flags':FLAGS,
    'state_values':{'0':'AGREED','1':'AMBIGUOUS','2':'MISSING'},
    'limitations':['not official combined reference','not signed route speed',
                  'receiver agreement does not exclude common bias',
                  'UNKNOWN covariance is not a calibrated accuracy bound',
                  'fixes are raw antenna positions, not base_link',
                  'full GNSS bag finalization required; never a causal feature']}

def unique(raw):
    """Keep exact duplicate rows in raw; never choose among conflicting payloads."""
    t = raw['stamp_ns']
    order = np.argsort(t, kind='stable')
    ts, first, counts = np.unique(t[order], return_index=True, return_counts=True)
    ix = order[first]
    conflict = np.zeros(len(ix), bool)
    for k in np.flatnonzero(counts > 1):
        j = order[first[k]:first[k]+counts[k]]
        conflict[k] = len(set(raw['wire_sha256'][j])) != 1
    return ts, ix, counts, conflict

def nearest(source, target, tolerance):
    """Unique nearest timestamp; equal-distance ties abstain."""
    out = np.full(len(source), -1, np.int64)
    ties = np.zeros(len(source), bool)
    if not len(target): return out, ties
    for i, stamp in enumerate(source):
        p = int(np.searchsorted(target, stamp))
        candidates = [j for j in (p-1, p) if 0 <= j < len(target)]
        dist = [abs(int(target[j])-int(stamp)) for j in candidates]
        best = min(dist)
        if best > tolerance: continue
        choices = [j for j,d in zip(candidates,dist) if d == best]
        if len(choices) != 1: ties[i] = True
        else: out[i] = choices[0]
    return out, ties

def pairing(mt, rt):
    """Exact first, then one pass of mutual-nearest among remaining unique times."""
    common, mi, ri = np.intersect1d(mt, rt, assume_unique=True, return_indices=True)
    pairs = [(int(i),int(j),False) for i,j in zip(mi,ri)]
    usedm, usedr = set(mi), set(ri)
    lm = np.array([i for i in range(len(mt)) if i not in usedm],dtype=np.int64)
    lr = np.array([i for i in range(len(rt)) if i not in usedr],dtype=np.int64)
    a,ta = nearest(mt[lm], rt[lr], POLICY['pair_tolerance_ns'])
    b,tb = nearest(rt[lr], mt[lm], POLICY['pair_tolerance_ns'])
    for k,j in enumerate(a):
        if j >= 0 and b[j] == k:
            i,z = int(lm[k]),int(lr[j]); pairs.append((i,z,False)); usedm.add(i);usedr.add(z)
    for k,i in enumerate(lm):
        if i not in usedm: pairs.append((int(i),-1,bool(ta[k] or a[k]>=0)))
    for k,j in enumerate(lr):
        if j not in usedr: pairs.append((-1,int(j),bool(tb[k] or b[k]>=0)))
    return sorted(pairs,key=lambda p: ((int(mt[p[0]])+int(rt[p[1]]))//2 if min(p[:2])>=0
                                      else int(mt[p[0]]) if p[0]>=0 else int(rt[p[1]]),p[0],p[1]))

def preparation(vel, fix):
    ts, ix, counts, conflict = unique(vel)
    speed = np.hypot(vel['linear'][ix,0], vel['linear'][ix,1])
    finite = np.all(np.isfinite(vel['linear'][ix]),axis=1)
    jump, gap, isolated = (np.zeros(len(ix),bool) for _ in range(3))
    if len(ix)>1:
        dt = np.diff(ts)
        gap[1:] = dt > POLICY['temporal_max_gap_ns']
        bad = ((dt>0)&(dt<=POLICY['temporal_max_gap_ns'])&finite[:-1]&finite[1:]
               &(np.abs(np.diff(speed)) > POLICY['temporal_jump_margin_mps']+
                 POLICY['temporal_acceleration_mps2']*dt/1e9))
        jump[:-1] |= bad; jump[1:] |= bad
    if len(ix)>2:
        isolated[1:-1] = ((speed[1:-1]==0)&(speed[:-2]>2)&(speed[2:]>2)
                         &(np.diff(ts)[:-1]<=500_000_000)&(np.diff(ts)[1:]<=500_000_000))
    ft,fi,fc,ff = unique(fix)
    f,tie = nearest(ts,ft,POLICY['fix_tolerance_ns'])
    findex = np.where(f>=0,fi[np.maximum(f,0)],-1) if len(fi) else np.full(len(ix),-1,dtype=np.int64)
    fbad = np.zeros(len(ix),bool)
    if len(fi): fbad[f>=0] = ff[f[f>=0]]
    reorder = np.r_[False,np.diff(vel['stamp_ns'])<0] if len(vel['stamp_ns']) else np.array([],bool)
    return dict(t=ts,ix=ix,count=counts,conflict=conflict,speed=speed,finite=finite,
                jump=jump,gap=gap,isolated=isolated,fix=findex,fix_bad=fbad,fix_tie=tie,reorder=reorder[ix])

def make_teacher(master_vel, rover_vel, master_fix, rover_fix):
    """The API deliberately accepts ONLY four GNSS streams; no other kwargs."""
    m,r = preparation(master_vel,master_fix),preparation(rover_vel,rover_fix)
    pairs=pairing(m['t'],r['t']); n=len(pairs)
    arrays={k:np.full(n,-1,np.int64) for k in ('stamp_ns','master_index','rover_index','master_fix_index','rover_fix_index')}
    arrays.update(speed_mps=np.full(n,np.nan),raw_mean_mps=np.full(n,np.nan),
                  master_speed=np.full(n,np.nan),rover_speed=np.full(n,np.nan),
                  reason_bits=np.zeros(n,np.uint32),flag_bits=np.zeros(n,np.uint32),
                  accepted=np.zeros(n,bool),raw_agree=np.zeros(n,bool),state=np.ones(n,np.uint8))
    for k,(i,j,ambiguous_pairing) in enumerate(pairs):
        reason=REASONS['PAIRING_AMBIGUITY'] if ambiguous_pairing else 0;flags=0
        stamps=[]
        for idx,prep,vel,fix,name in ((i,m,master_vel,master_fix,'master'),(j,r,rover_vel,rover_fix,'rover')):
            if idx<0:
                reason |= REASONS['MISSING_'+name.upper()]; continue
            rawidx=int(prep['ix'][idx]);arrays[name+'_index'][k]=rawidx
            stamps.append(int(prep['t'][idx])); arrays[name+'_speed'][k]=prep['speed'][idx]
            if not prep['finite'][idx]:reason |= REASONS['NONFINITE_VELOCITY']
            if prep['t'][idx]<=0:reason |= REASONS['BAD_SOURCE_TIME']
            if prep['conflict'][idx]:reason |= REASONS['CONFLICTING_DUPLICATE']
            if prep['jump'][idx]:reason |= REASONS['TEMPORAL_JUMP']
            if prep['count'][idx]>1:flags |= FLAGS['DUPLICATE_COLLAPSED']
            for prop,flag in [('gap','GAP_BEFORE'),('isolated','ISOLATED_ZERO'),('reorder','SOURCE_REORDERED')]:
                if prep[prop][idx]:flags |= FLAGS[flag]
            fx=int(prep['fix'][idx]);arrays[name+'_fix_index'][k]=fx
            if fx<0:
                reason |= REASONS['MISSING_FIX']
                if prep['fix_tie'][idx]:reason |= REASONS['PAIRING_AMBIGUITY']
                continue
            pos=fix['position'][fx];status=int(fix['status'][fx])
            if (prep['fix_bad'][idx] or status<0 or not np.all(np.isfinite(pos[:2]))
                or abs(pos[0])>90 or abs(pos[1])>180 or fix['stamp_ns'][fx]<=0):reason |= REASONS['INVALID_FIX']
            if not np.isfinite(pos[2]):flags |= FLAGS['ALTITUDE_UNKNOWN']
            if fix['covariance_type'][fx]==0:flags |= FLAGS['UNKNOWN_COVARIANCE']
            if np.all(fix['covariance'][fx]==0):flags |= FLAGS['ZERO_COVARIANCE']
        arrays['stamp_ns'][k]=sum(stamps)//len(stamps)
        if i>=0 and j>=0:
            a,b=float(m['speed'][i]),float(r['speed'][j])
            flags |= FLAGS['EXACT_PAIR'] if m['t'][i]==r['t'][j] else FLAGS['NEAR_PAIR']
            if np.isfinite(a) and np.isfinite(b):
                arrays['raw_mean_mps'][k]=(a+b)/2
                agrees=abs(a-b)<=max(POLICY['agreement_absolute_mps'],POLICY['agreement_relative']*max(a,b))
                arrays['raw_agree'][k]=agrees
                if not agrees:reason |= REASONS['SPEED_DISAGREEMENT']
                if a==0 and b==0:flags |= FLAGS['BOTH_ZERO']
                elif a==0 or b==0:flags |= FLAGS['ONE_ZERO']
                if min(a,b)==0 and max(a,b)>2:flags |= FLAGS['ZERO_VS_GT2']
            fm=master_vel['frame_id'][m['ix'][i]];fr=rover_vel['frame_id'][r['ix'][j]]
            if not fm or fm!=fr:reason |= REASONS['VELOCITY_FRAME_MISMATCH']
        arrays['reason_bits'][k]=reason;arrays['flag_bits'][k]=flags
        if reason==0:
            arrays['accepted'][k]=True;arrays['state'][k]=0;arrays['speed_mps'][k]=arrays['raw_mean_mps'][k]
        elif reason & (REASONS['MISSING_MASTER']|REASONS['MISSING_ROVER']|REASONS['MISSING_FIX']):arrays['state'][k]=2
    return arrays
