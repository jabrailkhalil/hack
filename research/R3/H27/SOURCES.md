# Sources and actually verified scope

Task R3-H27: supplied user card, fixed v8 baseline e3b0c9c039d2953fbfcda51231263d38ef9f1024.
Read relevant mechanisms, methods, results and limitations in PR20/H03, R2-H13 report91b7d9a6925dae64cfff51d514706d82bb801c56 and R2-H15 report2f959a41e1d7212f535f222ef2ac294dc5e8aeaf. Previous research is not independent proof of H27.

Primary institutional record and complete abstract read on2026-09-26:
Sariyildiz E., Hangai S., Uzunovic T., Nozaki T. (2021), Discrete-time analysis and synthesis of disturbance observer-based robust force control systems, IEEE Access9,148911–148924. DOI10.1109/ACCESS.2021.3123365.
https://keio.elsevierpure.com/en/publications/discrete-time-analysis-and-synthesis-of-disturbance-observer-base/
The abstract describes a different force-control system with velocity/acceleration measurements and noise/tuning constraints. Full text was not read in this session; its sensors and results are not transferred to H27.

Consensus and Scite: no new calls because the user card records existing monthly quota stops. No quota bypass or claim of newly checked citation contexts.

oracle.py and oracle-output.json are an actually executed independent local SymPy oracle. Equal-initial-state constant additive acceleration error gives delta_v=delta_d*T, delta_s=delta_d*T²/2; zero limits and trapezoidal discrete counterpart checked. Clipping counterexample recorded. No nonlinear stability or real disturbance contamination claim.
