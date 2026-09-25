# H15 / R2-v7-fixed — предварительная регистрация

Baseline: 65bba39ed05c781f3f69a65c02f69931152cbfd9; GuardedReadoutObserver, guarded_readout_v7.yaml, readout gain=1 / holdoff=0.5, inner compensation=0 / tau=0.5; 20 Hz, delay=0. Не брать moving main или H11/v8.

## До данных
Прочитаны core/guarded_readout/Timeline, evaluator score/replay/matching, calibration/data roles, отчёты v5/v6 и PR #19 H04, #22 H07, #18 H10, #14/#23, #26 H11. H04 менял learning rate; H07 привод; H10 joint observer; v6 decay. H15 ничего из этого не объединяет. Исторические числа не являются R2 measurements.
Consensus нашёл Vahidi et al. (2005), Scite: metadata/abstract первого и начало полного текста Rhode/Gauterin (2013). Условия возбуждения и errors-in-variables мотивируют safeguards, не обещают выигрыш. Wolfram выполнил вывод det(X'X)=n*sxx-sx^2, gamma=Cov(x,y)/(Var(x)+lambda), det=0 при постоянном x, continuity и nonexpansive clip. b/gamma не являются идентифицированными массой/уклоном.

## Механизм и заранее фиксированные параметры
Добавить auxiliary windowed ridge residual y=b+gamma*drive_a. y совпадает с legacy wheel-derived desired disturbance. Legacy d, its learning, Kalman fusion, physics, readout, guards, timestamps unchanged in healthy operation. Minimal research patch adds hooks after unchanged wheel gates and at existing trusted adaptation; new subclass of GuardedReadoutObserver implements them. Feature off must exactly reproduce all original instance fields, returned Estimate, statuses, counters.
Обучение только на двух НОВЫХ FUSED колёсах и valid command, abs(speed)>1, age<=0.20 s, skew<=0.05 s, pair difference<=0.15 m/s, innovation<=0.6 m/s, abs(residual)<=1.2 m/s^2. Existing derivative dt/rate gates remain. Window<=2 s, <=40 points; min6 points spanning>=0.5s; Var(drive)>=0.0025 (m/s^2)^2; condition number raw Gram after SI normalization x/(1m/s^2)<=1000; residual-fit RMSE<=0.5 m/s^2; freshest trusted point age<=0.5s at loss. These are fixed engineering bounds, not fitted physical properties.
Budget exactly two variants: lambda=0.01 and 0.04 (m/s^2)^2 in mean squared residual objective + lambda*gamma^2. Gamma clipped to [-0.25,0.25]; diagnostic intercept clipped to +/-legacy disturbance limit but never used in prediction. No other alternatives or tuning after development. Baseline/off is not a candidate.
Loss detection occurs after original gating: zero accepted wheels AND a status other than DUPLICATE_OR_OLD, not ordinary prediction-only ticks. Snapshot d_loss/drive_loss/gamma; evaluate d_eff=clip(d_loss+gamma*(drive-drive_loss),+/-limit) only for no-accepted-wheel prediction. First loss correction is zero. No oracle flags. Freeze gamma during loss, clear learning window, prohibit learning during loss; stale command permanently invalidates that session gamma and uses legacy d. At accepted wheel return to ordinary prediction/fusion/adaptation; recovery/stop resets auxiliary loss. Insufficient/old/ill-conditioned training or nonfinite input -> gamma=0, legacy hold. Prediction uses current causally updated drive. No GNSS/IMU/bag IDs/future input.

## Order and activation gate
Sanity before data: relevant original tests, off tick-equivalence, causal prefix/future rejection, duplicates, stale, reset, finite/bounded 40-point/time-window memory, constant-drive identifiability, continuity, clipping, frozen gamma, recovery, zero-lock; explicit contaminated common-mode ramp diagnostic (not claimed detectable from identical wheels).
Train: ALL64 train bag prefixes<=180s, Store train only vehicle topics; coverage and activation diagnostics, no GNSS/no parameter changes. Development: ALL17 genuine development bags, full streams, authorized read-only loader; both receivers only outside runtime. Original4 fault scenarios unchanged. Require before validation: >=100 trusted fits across >=3 development bags AND effective nonzero loss correction |d_eff-d_loss|>1e-6 for >=20 ticks across >=3 development bags in original or declared phase suite. If no coverage: INCONCLUSIVE, do not read validation.
Predeclared separate phase diagnostic on every development bag: first eligible traction->coast and coast->brake transition >25s, valid paired wheels speed>2, >=15s before end; both-wheel dropout starting0.3s before transition for5s, warmup20s/recovery10.1s; anchors from vehicle channels only. This suite does not replace original admission. Save trace d/gamma/condition/drive before,during,after every original/phase loss (bounded output sampling).
Selection: discard safety failures (new false stops/unrecovered/coverage/causality/reset or per-bag clean regression); among remaining choose smallest ORIGINAL fault group-macro RMSE, tie1e-12 favors lambda0.04. No requirement development gain>=5%; one validation can falsify the selected candidate, but activation and safety mandatory. If neither safe: REJECTED, no validation. After selection publish separate freeze commit hashing sources/configs/split/data/driver/evaluator/PLAN/dev outputs before ONE validation. Repeated validation is not an independent final test. Test/final payloads never opened.

## Fixed R2 contract
clean gain>=2% OR original fault gain>=5%; clean/fault/pooled regression<=0.5%; scalar span distance<=1%; clean per bag/receiver <=base+max(0.005m/s,5%base); identical coverage; no additional false stops, no NEW unrecovered cases, causality errors, unexpected resets. Baseline zero: absolute error tolerance1e-12 only, no division. Original immutable score/masks/aggregation reused; separate stricter veto for omissions in legacy decide. Show MAE, bias, recovery and all meaningful local regressions. No relaxed thresholds.

## Cost / runtime / artifact plan
One fixed development bag (first split member) prefix180s, warmup10s, 3 AB and 3 BA paired repetitions; threads1, same output collection; separate CPU/wall replay and instrumented step costs. No interpretation as installed ROS latency/RSS. If accuracy gate passes, fresh enabled candidate ROS both clocks on real development replay offline2CPU/500000000bytes required; otherwise explicitly omit full ROS benchmark. Never edit historical release pins/tests.

## Commands (implemented by new isolated driver)
```bash
python tools/get_dataset.py
python -m pip install -r requirements-research.txt
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH=src/reserve_odometry
python research/R2/H15/apply.py
python -m unittest discover -s research/R2/H15/tests -v
python research/R2/H15/run.py train --output "$OUT/train"
python research/R2/H15/run.py development --output "$OUT/development"
python research/R2/H15/run.py freeze --development "$OUT/development" --output "$OUT/FROZEN.json"
# COMMIT AND PUSH freeze to unique checkpoint/H15-${run_id}-${run_attempt} BEFORE next command.
python research/R2/H15/run.py validation --frozen "$OUT/FROZEN.json" --output "$OUT/validation"
```
Artifacts: reports/research_R2/H15/<run-id>/, immutable own checkpoint, raw metrics/CSV, access logs, applied patch and manifest, Wolfram worksheet/output and sources. Draft PR Russian; REJECTED/INCONCLUSIVE explicitly not merge-ready. No force push/merge/auto-merge/main/other branches modifications. Infrastructure retries get separate IDs; no candidate changes after validation.
