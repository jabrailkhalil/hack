"""One-time offline instrumentation amendment before source publication.

Fault identity remains exclusively in Monitor, never in the observer. No score,
source grid, model parameters, candidate choice or safety rule changes.
"""
from pathlib import Path
p = Path(__file__).with_name('run.py')
s = p.read_text()
replacements = [
("    def __init__(self, inner, check_disabled=False):\n        self.inner=inner\n", "    def __init__(self, inner, check_disabled=False, trace_fault=None):\n        self.inner=inner\n        self.trace_fault=trace_fault\n"),
("        self.ticks=0;self.accepted=0;self.changed=0\n", "        self.ticks=0;self.accepted=0;self.changed=0\n        self.fault_trace=[]\n"),
("        for key in ('v','s','a','variance_v','variance_s','disturbance'):\n", "        if self.trace_fault and self.ticks % 4 == 0 and len(self.fault_trace) < 128:\n            start,end=self.trace_fault['start'],self.trace_fault['end']\n            middle=(start+end)*.5\n            if abs(e.t-start)<=1. or abs(e.t-middle)<=.5 or abs(e.t-end)<=1.:\n                self.fault_trace.append(dict(t=e.t,segment='before' if e.t<start else 'during' if e.t<end else 'after',\n                    published_v=e.v,published_s=e.s,inner_v=self.inner.v,inner_s=self.inner.s,\n                    pv=self.inner.pv,drive_a=self.inner.drive_a,disturbance=self.inner.disturbance,\n                    readout_correction=self.inner._velocity_correction,mode=e.mode,\n                    front_status=e.front_status,rear_status=e.rear_status,soft_update=d))\n        for key in ('v','s','a','variance_v','variance_s','disturbance'):\n"),
("            trace=self.traces,disabled_full_state_ticks=self.ticks if self.off else 0)", "            trace=self.traces,fault_trace=self.fault_trace,disabled_full_state_ticks=self.ticks if self.off else 0)"),
("        monitor=Monitor(inner,check_disabled=check_disabled and name==BASE)", "        monitor=Monitor(inner,check_disabled=check_disabled and name==BASE,trace_fault=scenario)")
]
for old,new in replacements:
    if s.count(old) != 1:
        raise ValueError('Unexpected instrumentation anchor: '+old[:60])
    s=s.replace(old,new)
p.write_text(s)
print('Applied prereplay offline trace instrumentation only')
