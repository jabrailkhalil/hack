"""Bounded scalar additive-error joint state. Pure Python; no replay.

Exact only for known piecewise deterministic drift, Brownian process noise and
independent fixed-R observations. The vehicle observer is a local approximation.
"""
from bisect import bisect_left
import math

class JointHistory:
    MAX_STATES = 32
    MAX_EVENTS = 64
    def __init__(self, t, mean, variance, window=.25):
        if not all(math.isfinite(v) for v in (t,mean,variance,window)) or variance<=0 or window<=0:
            raise ValueError('Invalid joint initial state')
        self.times=[float(t)];self.means=[float(mean)];self.p=[[float(variance)]]
        self.q=[];self.events=[];self.window=window
    def _drop_first(self):
        self.times.pop(0);self.means.pop(0);self.p.pop(0)
        for row in self.p:row.pop(0)
        if self.q:self.q.pop(0)
    def prune(self,now):
        cutoff=now-self.window
        while len(self.times)>1 and self.times[0]<cutoff-1e-9:self._drop_first()
        self.events=[(t,k) for t,k in self.events if t>=cutoff-1e-9]
    def append(self,t,mean,q):
        if not all(math.isfinite(v) for v in (t,mean,q)) or t<=self.times[-1] or q<0:
            raise ValueError('Invalid joint transition')
        self.prune(t)
        if self.times[-1]<t-self.window-1e-9:raise ValueError('Joint history gap')
        while len(self.times)>=self.MAX_STATES:self._drop_first()
        last=list(self.p[-1]);new_var=last[-1]+q*(t-self.times[-1])
        for i,row in enumerate(self.p):row.append(last[i])
        self.p.append(last+[new_var]);self.times.append(t);self.means.append(mean);self.q.append(q)
    def index(self,t):
        if not math.isfinite(t) or t<self.times[0]-1e-9 or t>self.times[-1]+1e-9:
            return None
        i=bisect_left(self.times,t)
        for j in (i-1,i):
            if 0<=j<len(self.times) and abs(self.times[j]-t)<=1e-9:return j
        if i==0 or i==len(self.times) or len(self.times)>=self.MAX_STATES:return None
        dt=self.times[i]-self.times[i-1];w=(t-self.times[i-1])/dt;v=1-w
        left,right=self.p[i-1],self.p[i]
        cross=[v*x+w*y for x,y in zip(left,right)]
        variance=v*v*left[i-1]+2*v*w*left[i]+w*w*right[i]+self.q[i-1]*dt*v*w
        mean=v*self.means[i-1]+w*self.means[i]
        for j,row in enumerate(self.p):row.insert(i,cross[j])
        self.p.insert(i,cross[:i]+[variance]+cross[i:])
        self.times.insert(i,t);self.means.insert(i,mean)
        self.q.insert(i-1,self.q[i-1])
        return i
    def observe(self,i,z,r,key):
        if key in [k for _,k in self.events]:raise ValueError('Duplicate evidence')
        if len(self.events)>=self.MAX_EVENTS:raise ValueError('Event ledger capacity')
        if not math.isfinite(z) or not math.isfinite(r) or r<=0:raise ValueError('Invalid observation')
        cross=[row[i] for row in self.p];s=self.p[i][i]+r
        if s<=0 or not math.isfinite(s):raise ValueError('Invalid innovation variance')
        gains=[c/s for c in cross];residual=z-self.means[i]
        means=[m+k*residual for m,k in zip(self.means,gains)]
        n=len(means);p=[row[:] for row in self.p]
        # Expanded Joseph update; old cross terms used for every entry.
        for j in range(n):
            for k in range(j,n):
                value=self.p[j][k]-gains[j]*cross[k]-gains[k]*cross[j]+gains[j]*gains[k]*s
                p[j][k]=p[k][j]=value
        if not all(math.isfinite(m) for m in means) or any(p[j][j]<-1e-10 for j in range(n)):
            raise ArithmeticError('Nonfinite or negative covariance')
        self.means,self.p=means,p
        self.events.append((self.times[i],key))
        return means[-1],p[-1][-1]
