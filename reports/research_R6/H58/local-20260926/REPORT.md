# R6-H58 — FOUNDATION_FAILED / INCONCLUSIVE

Проверка основания завершена на 36 train-fit bags / 20 исходных группах, 3761 событиях. Runtime-кандидат C1 и контроль C0 не реализованы: preregistered gates A и C не пройдены. Никакого train-check, development, validation/test, изменения main, merge или auto-merge. PR-кандидат не создаётся без прохождения development, как требует карточка R6-H58.

## Основной результат

Причинные признаки хорошо различают выбранную направленную H42 proxy-разметку, но этого недостаточно для безопасного ослабления d.

| Проверка | Результат | Требование |
|---|---:|---:|
| Potentially useful d: events / distinct starts / groups | 35 / **6** / 3 | >=30 / **>=10** / >=3 |
| Risk-direction d: events / starts / groups | 60 / 11 / 7 | >=30 / >=10 / >=3 |
| Feature coverage of otherwise eligible events | 112/112 | >=80% |
| Weighted OOF AUROC | 0.9714285714285714 | >=0.65 |
| Weighted balanced accuracy | 0.85 | >=0.60 |
| Log-loss gain over fold-training intercept | 71.362782529% | >=2% |
| Precision at p>=0.8 | 96.202531646% | >=80% |
| False-positive rate within useful-direction class | **10.714285714%** | **<=10%** |
| Decision starts / groups | 11 / 8 | >=10 / >=3 |

95 labelled duration variants represent only 17 distinct starts in 9 source groups, not 95 independent trips. All 20 leave-one-group-out summaries are retained. Min leave-one-group-out OOF AUROC 0.95; min precision 95.522388%. No thresholds, features or regularization changed after results. Strong directional discrimination is supported; general uselessness of reliability-aware observers is not established. Scientific verdict is INCONCLUSIVE, operational stage FOUNDATION_FAILED.

## Counterexample and limits

All 7 false positives are 7 duration variants of one start in `30618_bab2fe58`, group `5c1be3e9a2189121`, anchor `3cae01d56213bd9d85ef`. At braking, d=+0.6 m/s² and prefault speed 2.068668 m/s, p_risky=0.918690. Mean signed magnitude-speed proxy bias is negative: -2.032061 m/s at 10 s and -2.534425 m/s at 15 s. Positive d opposes that error under the local directional surrogate, but the classifier calls it unreliable. The actual attenuation intervention was NOT evaluated.

Terminal delta_s -19.904320 m (10 s), -47.413193 m (15 s), and recovery delta_s -10.437135 m (15 s) are **v8 faulted minus v8 clean**, not measured H58 error or ground-truth XYZ. H42 is an unsigned-speed proxy, not true signed route velocity. AUC does not prove improvement of full distance or recovery. No claim of enabled ROS resource/latency verification.

## Versions and methodology

Baseline `b2783206000091ab11a1c11ac3ff79082188a4fb`; tree `973d50d288e050325ee1c71a90fa8d81f2a099af`; all 320 paths/bytes/modes verified. Full `GuardedReadoutObserver` / `champion_v8.yaml`, 20 Hz, delay 0. Preregistration commit `ee22f6bbb31ff98604c208ae8d85ce212a0180e5`; execution source binding `352c4b70834b7b14caa85611e1c4013285f519a4`.

The latter is a content-hash binding to the **passive diagnostic source archive in Drive**, not a runtime candidate commit. Source ZIP SHA256 `38004621ff8af4677c0829848ff72c96a069e9d6b175d93462e8a9ac3ef22f3e`, 60458 bytes, file ID `11UXWMzB_dOpWVEcx3NnKPK1O6R7bzHrn`.

FD2 frozen ZIP SHA256 `2ecda6c68a31c921fe7dc6bda1fcc02d6d39264629e87772903b98100b95f08a`; unchanged FD1 replay/FD2 schedule/event_features and 10 frozen class predicates. PyArrow was unavailable, so a pre-measurement transport addendum authorized exact B0 fit replay instead of reading mixed fit/check Parquet. No fitting of F/P/B. SQL read-only, controller/front/rear only; H42 is external offline labeling. Eight fixed causal features, one logistic structure, L2=0.001, p-threshold 0.8; group/anchor/duration weighting and whole-group LOGO. Eighteen fits for nonempty held-out groups, no global final runtime calibration. Four bags without FD2 events and missing reference are retained explicitly.

## Actual checks

161 baseline +43 integrity +14 H58 tests PASS; synthetic pipeline and portable bootstrap PASS. 728978 real clean published outputs and d series exactly match canonical replay. Full internal-state parity is synthetic, not falsely claimed for all real fields. Monitor max histories 41 ticks /22 pairs; limits 64/64. No future held input. All 36 DB hashes and baseline source hashes remain unchanged.

24 historical FD2 fit NPZ witnesses compared: max absolute difference 9.094947e-13. Not all historical raw traces are present upstream. Independent audit recomputed the metrics using a separate pairwise AUC implementation: max difference 1.110223e-16; all 3761 model predictions max difference 2.220446e-16. No model refit in that audit.

Local B0 run exit 0; wall 559.08 s, user CPU 2165.06 s, system CPU 2.73 s, 4 workers. GNU time max RSS 159560 KiB is process accounting, not total workers or a ROS node benchmark. No Actions run is claimed.

## Delivery

- [Detailed Russian report](https://drive.google.com/file/d/1owIm_-HoiViUZ9SqLCVts1sunLXIwVwK/view)
- [SUMMARY.json](https://drive.google.com/file/d/1jh07YQJheGf-nFs0oFQNKbXC911U6q5E/view)
- [FOUNDATION.json](https://drive.google.com/file/d/1oX-GdzDOzq1h1brzlYbGjmkuXNP_CvdX/view)
- [Compact complete package, 50 members](https://drive.google.com/file/d/18XRuQpk1PVNOmt2J1G59aH1Jl7X1IknE/view): 446600 bytes, SHA256 `e0ea3658daa101e1499b71bb004f4e2434ea1b8c656496b8fb08713d3547c8bb`.
- [Raw foundation evidence, 180 members](https://drive.google.com/file/d/1WsMShp_HEuxVZd-XWJtBBozfWFeqffr6/view): 66459666 bytes, SHA256 `b47ce46782d4f5747df3818307157df893425669b1a00ee845cbe8a3dff3232f`.
- [H58 workspace](https://drive.google.com/drive/folders/1zS737e6EhH2LlAMNFCSiYw-643i2Oich).

The compact package contains exact measured source, PLAN, FEATURE_CONTRACT, DEPENDENCIES.lock, CV_RESULTS, PER_GROUP, FAULT_CLASS_RESULTS, OOF predictions/models, correlations, independent audit, counterexamples, tests, source-only foundation.patch and reproducible bootstrap. Raw contains all 36 compact per-event results and clean feature/proxy arrays, no db3 or shared canonical copies. TRAIN_CHECK_CONFIRMATION.csv contains an explicit NOT_RUN row, not fabricated measurements. DEVELOPMENT.csv and candidate.patch are intentionally absent: no admitted or implemented runtime candidate.

Reproduce with the six authenticated shared archives named in DEPENDENCIES.lock:

```bash
python delivery/bootstrap.py --inputs /downloaded/shared --destination /new/R6_H58
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python /new/R6_H58/src/test_foundation.py
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python /new/R6_H58/src/h58.py --root /new/R6_H58 --workers 4
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python /new/R6_H58/src/analyze_foundation.py --root /new/R6_H58
```

Runtime candidate/freeze/accuracy metrics = N/A; ready_to_merge=false. Do not lower the support gate or change p-threshold using these outcomes. Continuation would require a separately authorized protocol, not an automatic train-check/development pass.
