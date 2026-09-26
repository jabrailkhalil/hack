# R5-H44 — DEPENDENCY_PENDING / NOT_EVALUATED

**Контрольная точка незавершённого исследования, не готова к merge. Это не REJECTED.** Выполнены source/data preflight, интерфейс только трёх effective coefficients, tests и новый baseline-only development replay. Обязательные teacher/atlas payload не получены через разрешённую raw-byte выдачу. GNSS fit, matched wheel-control fit, candidate comparison, validation/final test и enabled ROS не запускались. Candidate metrics=N/A, не 0% gain.

## Версии

Baseline `b2783206000091ab11a1c11ac3ff79082188a4fb`, tree `973d50d288e050325ee1c71a90fa8d81f2a099af`. PLAN этапа0 до нового development IO: `d155cae00b372da5930afe3aee961499fa0e9f76`. Диагностический исходник, опубликованный до replay: `2748b8e4ce53ea4cda91f08716993ea38fff28a3`, tree `471c4070b480df5962073b6c5eb738342474b760`. Это НЕ measured candidate SHA: fitted candidate отсутствует. Ветка `research/R5-H44`. Freeze=null. Последующий report-only commit не является новой измеренной версией.

## Точный blocker

Launch-пакет требует реальные R5_H42_teacher_component.zip и R5_H43_atlas_handoff.zip. Они найдены в Library; соответствующие PR56/H42 и PR55/H43 прочитаны. Но actual files.materialize для каждого вернул:

> This Project file does not have an authorized raw-byte materialization path.

Ожидаемый teacher ZIP: 28190115bytes, SHA256 `2ee08edb32343350bf6ae6202836644de4fb309640f2d140a1eb9d5791af28b8`, manifest `5c8129133758bbb715f2e170122b976f95d0240c18daa731472d910f0bf274d0`.
Ожидаемый atlas ZIP: 1076521bytes, SHA256 `6a759f4bafe4ece014e9dd4f25b201549e317f2ca9db7b47b6c15d4443d9b011`, manifest `73d3269f012f25f4c46787369bdb85fc218fbf149d29cd60c63eb8f20687bd5c`.

Эти hashes прочитаны из контракта, НЕ подтверждены локальным чтением payload. Нет transport/native verification, фактического folds bridge и DEPENDENCIES.lock.json. PR receipts и DEPENDENCIES.expected.json не заменяют arrays/manifest. Отказ не обходился; H42/H43 не перезапускались, teacher не пересоздавался, wheel targets не использовались вместо GNSS. Запись GitHub доступна: недоступен именно компонентный raw-byte этап. Необходимы только два точных ZIP; source и dataset уже получены.

## Source и dataset

`hack-main-2 2(2).zip`, SHA256 `4823fbdbbb979d7b561841e2831e68f2f7d9d8ec0d14e970f09a38cd51dff4c4`, 3871238bytes: все320paths/bytes/executable bits дают точный R5 tree. Позднее названный `hack-main-2(20260926-135511).zip` оказался старым R4 snapshot:301files/tree eae49a504bc59b5c9b408445150bef32e111956f, SHA256 a8e0bfa033e0a02c460c30b02f34a5c64ece85b05003512941387d3cf1f319a2. Он исключён и сохранён как MISMATCH относительно R5.

Dataset получен разрешённой Files materialization:256294592bytes/SHA256 d0b2483e13990edb8219b0d7bbcafc7ed001cce549a4d3af467069b2472e7d52. Извлечены только64train+17development DB, каждый SHA256 проверен до и после replay. Validation/test DB не извлекались. SQL measurement access нового прохода:17development, 0train/validation/test. Train подготовлен, но payload не декодировался. Все320baseline files неизменны;29launch files сверены с manifest. Полный324file tree диагностического source восстановлен и совпал с опубликованным.

## Реализация preflight, не кандидата

`research/R5/H44/interface.py` читает полный canonical model/readout из champion_v8.yaml без Config defaults. Преобразует F/m,P/m,B/m в прежние torque/power/brake поля; остальные параметры неизменны. Theta0 даёт exact original floats; тестовый1% shift — только fixture, не fitted вариант. Training entrypoint намеренно отказывает: обучающего пути в checkpoint нет.

`baseline_preflight.py` добавляет development-only read-only role adapter с исходными decoding/scales/order и hash/role check доSQLite. Использует неизменные guarded.compare/predict/fault_windows, evaluate.replay/distance_surrogate, ex.match/metrics и v6.summary. Историческая factory с main=v5 не вызывается. Реальный GuardedReadoutObserver/champion_v8,20Hz/delay0,readout1/.5,tau.5,quarantine1.5,compensation0. Outputs — возвращаемые Estimate.v/s. Canonical core/readout/Timeline/profile/executable не изменены.

## Новый реальный baseline-only replay

Все17development bags/7groups, reference6groups/19clean bag-receiver pairs.56original cropped fault scenarios/60reference comparisons. Missing и спорные GNSS точки остаются в исходных masks; новый teacher не строился.

| Метрика | Реальный v8 | H44 |
|---|---:|---|
|Clean group-macro RMSE,m/s|0.09266814298282507|N/A|
|Original fault-event RMSE,m/s|0.2375486120563008|N/A|
|Pooled clean RMSE,m/s|0.1293056944774334|N/A|
|Clean scalar-span distance RMSE,m|5.310295004801444|N/A|
|Matched clean samples|394221|N/A|
|False stops clean/original|0/0|N/A|
|Original unrecovered|4|N/A|

Все5fingerprint-полей совпали точно, delta0. Это реально исполненный baseline, не исторические цифры вместо replay. Невосстановления30639_e4379d7f/rover:bias5/dropout5/dropout10/lock3; H43 classification здесь не переоценивалась. Causal errors/reset0. Пер-bag/per-receiver/per-fault RMSE/MAE/p95/bias/coverage/recovery сохранены в raw baseline results.json/CSV в выдаче. Нет full-faulted candidate/safety suite/регрессионного сравнения: candidate отсутствует. Accuracy contract не оценивался.

## Фактически выполнено

161original unit +43research-integrity +13launch-toolkit fixtures +13H44preflight tests — PASS. Наборы не считаются суммарным числом уникальных тестов. H44:2000ticks полного state/Estimate identity, полный профиль, только3поля, runtime force/power/brake oracle, invalidparams, no-new-runtime-inputs, read-only роли доIO, N/Areference, no-overwrite и fail-closed training. Дополнительно patch apply/roundtrip с повтором13tests и compileall PASS. Логи содержат TERM environment variable not set после успеха; exitcode0.

Локальная среда Python3.13.5/NumPy2.3.5/SciPy1.17.0. Wall5.206010849s — весь baseline probe, не ROS latency/candidate cost. Новые CI/Actions/ROS/Wolfram не запускались; [skip ci] не означает зелёный CI. Elementary parameter mapping проверен local runtime oracle, не заявлением об идентифицируемости. Enabled runtime status=NOT_RUN_DEPENDENCY_PENDING.

## Возобновление без повторного baseline/fitting

Бюджет не расходован:0GNSS fit,0matched-control fit,0actual residual/Jacobian calls. После exact ZIPs: original transport verifier; собственный native verifier каждого producer в разных roots; bridge реальных folds; единый DEPENDENCIES.lock. Затем до первого fit опубликовать полную numeric matched-window/loss policy (с учётом неизвестного знака GNSS magnitude). Сейчас есть только PLAN этапа0 и неизменные budgets/gates, не готовая реализация fitter.

Один fit GNSS и один wheel control, max_nfev80each/total residual calls<=1000; те же windows/weights/warmup/.5-2-5s horizons/prefix integral/prior/bounds. Не заполнять teacher missing колёсами, не использовать noncausal quality как runtime feature/init, не обучаться на atlas development errors, не копировать чужое prefault state. Общий LONGITUDINAL contract, check и attribution gates, полная faulted-distance и safety suites сохранены. Validation только после положительного кандидата и опубликованного freeze; final test закрыт.

Повтор baseline — не требуется лишь ради возобновления при тех же pins. При необходимости, в diagnostic checkout:

```bash
python -m pip install -r requirements-research.txt
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
python -m unittest discover -s research/R5/H44/tests -v
OUT=$(mktemp -d)
python research/R5/H44/baseline_preflight.py \
 --data-root /path/to/verified/data --source-receipt /path/to/SOURCE_RECEIPT.json \
 --output "$OUT/baseline" --workers 2 \
 --diagnostic-source-sha 2748b8e4ce53ea4cda91f08716993ea38fff28a3
```

В чате выдаётся полный checkpoint: preflight-only patch, точные sources/PLAN, expanded REPORT/SUMMARY, raw baseline metrics, receipts, access/tests/команды/hash manifest и original launch bundle. Без DB или teacher arrays; не выдуман Actions artifact ID/retention. **NOT_EVALUATED из-за DEPENDENCY_PENDING; runtime-кандидата и вывода о точности H44 пока нет.** Main/upstream/старые отчёты не менялись, merge/auto-merge не выполнялись.
