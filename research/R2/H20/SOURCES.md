# Sources and mathematical evidence actually retrieved

1. Xu Bai, Yinhang Wang, Mingchen Jia, Xinchen Tan, Liqing Zhou, Liang Chu,
   Di Zhao (2024). *An NMPC-Based Integrated Longitudinal and Lateral Vehicle
   Stability Control Based on the Double-Layer Torque Distribution.* Sensors
   24(13), 4137. DOI: **10.3390/s24134137**.
   https://www.mdpi.com/1424-8220/24/13/4137
   Read level: indexed publisher HTML passages, especially section 4.3/equation 32,
   and PubMed metadata, not a complete critical review of the full paper. Slip
   sign motivates the hypothesis only. Four-wheel vehicle control with torque
   allocation is not a validated two-bogie speed estimator. Direct PMC page
   returned a browser challenge; no inaccessible full text is claimed as read.

2. M. Tanelli, S. Savaresi, Carlo Cantoni (2006). *Longitudinal vehicle speed
   estimation for traction and braking control systems.* IEEE joint CACSD/CCA/ISIC,
   pp. 2790–2795.
   https://consensus.app/papers/longitudinal-vehicle-speed-estimation-for-traction-and-tanelli-savaresi/33ebe35727a054a0814745199f086d9e/
   Consensus search and fetch were both executed; read level: metadata + abstract.
   Four wheel speeds **and a longitudinal acceleration sensor**; that sensor is
   forbidden in this project, so the method/performance is not transferred.
   Citation count returned by the service: 84; not independent verification.

Scite `search_literature` was actually called for DOI 10.3390/s24134137. It returned
monthly MCP quota exhaustion (25 calls, reset 2026-10-01). No Scite paper cards,
full text or citation contexts were obtained. No purchase or permissions change.

Wolfram Language evaluator executed two worksheet calls. `wolfram.wl` combines
those same formula checks and the corrected paired numerical integral. Actual
returned values are transcribed in `wolfram-output.json`. The first quadrature
split omitted the -0.3 Huber kink and generated convergence warnings; the second
paired positive-axis integration included the 0.3 kink and returned without those
warnings. Both attempts are retained; warnings are not called a successful exact
integration. Bounds, units and a local bias example are not a global nonlinear
observer stability proof and not accuracy evidence on real recordings.

For e=z-v, one accepted wheel, P=0.01, R=0.04, c=b=0.3 m/s and zero-mean Gaussian
noise sigma=0.1 m/s, traction-oriented expected correction is negative for alpha>0;
braking reverses its sign. This is precisely a possible clean-motion bias risk.
The static measurement matrix for [v,b_front,b_rear] has rank 2 and null direction
[-1,1,1]; command/model assumptions do not create an independent speed reference.
