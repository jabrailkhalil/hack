# R4-H37 — REJECTED после возобновления с приложенным датасетом

**Исследовательский отрицательный результат, не готов к merge.** Прежний NOT_EVALUATED относился к недоступному исполнению. Пользователь предоставил dataset ZIP; первый candidate-development теперь выполнен полностью локально. Единственный прежний кандидат отклонён: original fault-event RMSE **+1.428931844%**, common-mode event RMSE **+3.169430841%**, необходимого выигрыша нет. Validation и final test не открывались. Нового fitting, изменения параметров, merge или auto-merge нет.

## 1. Версии, данные и выполненный этап

| Назначение | Значение |
|---|---|
| Round / hypothesis | R4-v8-fixed / R4-H37 |
| Baseline SHA | e3b0c9c039d2953fbfcda51231263d38ef9f1024 |
| Полный baseline tree | eae49a504bc59b5c9b408445150bef32e111956f |
| PLAN до исходных измерений | 8d14f9177271a258d1ad280352c61241e4b17e76 |
| **Фактически измеренные runtime и driver** | **14a9aa29a87a9b8e6d33c6b063bed1dac696bde7** |
| Execution ID | local-20260926-dataset4 |
| Ветка / draft PR | research/R4-H37 / #46 |
| Foundation checkpoint, не повторялся | eeb33182e0e2942f7e35fcb6dd55ed9577e01d53 |
| Validation freeze | N/A: development rejected |

Источник исполнения — проверенный ZIP baseline и точные research blobs из сохранённого пакета, не поддельный git checkout. Полностью перепроверены 301 исходный файл, байты и executable bits; tree совпал. Runtime/driver/cost/tests совпали с CANDIDATE_PINS и опубликованными Git blobs. После измерения повторно проверены все 305 baseline/candidate pins. Алгоритм и scorer при возобновлении не менялись.

Baseline ZIP SHA256: `a8e0bfa033e0a02c460c30b02f34a5c64ece85b05003512941387d3cf1f319a2`.
Приложенный `dataset(4).zip` SHA256: `d0b2483e13990edb8219b0d7bbcafc7ed001cce549a4d3af467069b2472e7d52`, точное совпадение с закреплённым organizer archive. Из внутреннего архива извлечены только 17 development DB, 98082816 байт; SHA256 каждого сверены с исходным split до read-only SQL. В этом продолжении train не извлекался и не переисполнялся. Индивидуальные validation/test DB не извлекались, не открывались и не декодировались.

Python 3.13.5, NumPy 2.3.5, SciPy 1.17.0; OPENBLAS_NUM_THREADS=1, OMP_NUM_THREADS=1. Offline development использовал 2 workers. Это не сертификация ROS-ноды под 2 CPU / 500 MB.

## 2. Неизменный кандидат

`TractionPowerObserver`, enabled=True, точные config/readout из champion_v8.yaml/json. Baseline — GuardedReadoutObserver, quarantine=1.5, readout gain=1/holdoff=.5, adaptation_tau=.5, wheel_time_compensation=0, output 20 Hz, alignment=0.

```text
baseline:  direction*q*min(F,P/max(|v|,1))/mass
candidate: direction*min(q*F,P/max(|v|,1))/mass
```

Меняется только положительная тяга. q/deadband/exponent, торможение, tau, физические параметры, d-update, guards, readout и Timeline прежние. При feature-off вызывается исходный метод. Память O(1), одно поле enabled; runtime принимает только controller/front/rear. Нет GNSS/IMU, будущих samples, fault oracle или новых зависимостей. Обычный ROS launch кандидата не включает.

SHA256 runtime traction_power.py: `0bc92ac6c4b5d5a4804f9e44be8475c7dbe00b2d166f3358f5d4b40b439aeed1`.
Git blob: `86305053d6c7deb7520cff759e49fdc1648f69e4`.
Это сравнение двух допущений о смысле controller, не доказанная паспортная характеристика. Большая модельная тяга сама по себе не означает лучшую одометрию.

## 3. Методика и воспроизведение baseline

Реально заново исполнены все 17 development bags / 7 исходных групп. Reference есть в 6 группах / 19 bag-receiver парах, 394221 matched clean samples. Семь bag без reference сохранены как null, не нулевая ошибка. Оба receiver сохранены и не считаются независимыми поездками.

Неизменные evaluate.score/replay, matching, masks, timestamps, arrival order, original fault anchors и group aggregation. Подменяется только factory observer; сравниваются возвращаемые Estimate.v/s. Baseline fingerprint по clean/fault/pooled/distance/n совпал точно: **все пять отклонений 0.0**. Feature-off возвращаемые Estimate, все базовые поля состояния, массивы и runtime counters сверялись с отдельным canonical v8. В post-аудите расхождений off-метрик нет.

Выполнены 56 original faults, 26 low-speed, 28 common-mode и 13 traction-to-coast dropout: всего 123 инъекции. Каждая проверена и на штатном коротком окне, и на полном bag с исходного старта. Вместе с clean это 263 paired case replay; у каждого baseline/H37/off. Отдельный off-reference является проверкой, а не четвёртым кандидатом. Есть 60 original reference-сравнений. Отсутствующие reference не заменены нулями.

## 4. Основные development-метрики

Положительная процентная дельта означает рост ошибки.

| Метрика | Baseline v8 | H37 | Изменение |
|---|---:|---:|---:|
| Clean group-macro RMSE, м/с | 0.09266814298282507 | 0.09266841644233960 | +0.000295095% |
| Original fault-event group-macro RMSE, м/с | 0.23754861205630080 | 0.24094301981955932 | **+1.428931844%** |
| Pooled clean RMSE, м/с | 0.12930569447743340 | 0.12933690967421685 | +0.024140620% |
| Scalar-span clean distance RMSE, м | 5.310295004801444 | 5.310914777711141 | +0.011671158% |
| Full-original-faulted-bag distance RMSE, м | 6.269376947281123 | 6.278995240194583 | +0.153417046% |
| Matched clean samples | 394221 | 394221 | одинаково |
| False stops clean / original | 0 / 0 | 0 / 0 | без роста |
| Original unrecovered | 4 | 4 | те же случаи |

Отказ неизменного driver: `aggregate_regression:fault_rmse`, `insufficient_gain`, `v8_veto:common_mode`. Требовались >=2% clean gain ИЛИ >=5% original fault gain; регрессии clean/fault/pooled <=0.5%, distance <=1%, прежний per-bag допуск и safety. Пороги не пересматривались.

Clean MAE 0.034933352905 -> 0.034932288757 м/с; p95 0.090092790092 -> 0.090053418103; signed bias 0.006390677420 -> 0.006391344750. Для original fault+10s окна MAE 0.153796529331 -> 0.155679502911, p95 0.456670428618 -> 0.464701427213, signed bias 0.011170307852 -> 0.021005297845 м/с. Эти окна шире event-only RMSE.

Group-macro confirmed original recovery 0.724358284875 -> 0.716545784875 с, отдельно от четырёх unrecovered. Новых per-case false stops/unrecovered, потери coverage, causal errors и resets не обнаружено также в дополнительных и full-bag проверках. Сохранение этих свойств не отменяет отрицательный accuracy verdict.

## 5. Все clean bags

В каждой строке среднее RMSE доступных receivers данного bag; основной итог выше использует исходное групповое агрегирование.

| Bag | v8, м/с | H37, м/с |
|---|---:|---:|
| 30618_0652866c | 0.036107025889 | 0.036082085496 |
| 30618_073f08d1 | 0.033935203813 | 0.033934609141 |
| 30618_117c2d02 | N/A | N/A |
| 30618_1551d0a9 | 0.003988359652 | 0.003988359652 |
| 30618_27e994fc | 0.161364401745 | 0.161411260835 |
| 30618_3e012faf | N/A | N/A |
| 30618_46e21b9b | N/A | N/A |
| 30618_5036aa78 | N/A | N/A |
| 30618_74559c73 | N/A | N/A |
| 30618_88548b02 | 0.050600852667 | 0.050778514528 |
| 30618_bcc9e7a2 | N/A | N/A |
| 30618_e151d6e4 | N/A | N/A |
| 30639_0ab96c59 | 0.019185027740 | 0.019185027740 |
| 30639_9c362687 | 0.120351633512 | 0.120279285713 |
| 30639_c31df386 | 0.063707555446 | 0.063670349860 |
| 30639_dce52be4 | 0.231633603805 | 0.231691265374 |
| 30639_e4379d7f | 0.138142126696 | 0.138102138473 |

Clean RMSE хуже в 6/19 reference-парах, но все в прежнем per-bag допуске. Original event RMSE хуже в 13/60 сравнениях; число выигравших сравнений не отменяет величину регрессий и связность групп.

## 6. Отдельные suites, группы и регрессии

Original по типам: bias5 event RMSE -1.205335%, dropout5 -1.954204%, dropout10 **+6.615002%**, lock3 -4.079166%. Это описательные разрезы, не новый отбор.

| Отдельная suite | Baseline event RMSE | H37 | Изменение |
|---|---:|---:|---:|
| Low-speed lock3/5 | 0.368545673306 | 0.368545673306 | 0% |
| Abrupt common-mode | 0.100632272301 | 0.103821742576 | **+3.169431%** |
| Traction-to-coast dropout | 0.305613203670 | 0.305613203670 | 0% |

У low-speed совпал event RMSE, но post-fault MAE/p95 слегка выросли; это не заявление равенства всех метрик. В дополнительных suites baseline unrecovered 6/2/1 соответственно, у H37 столько же. Common-mode veto <=0.5% нарушен.

Групповые original RMSE v8 -> H37: 70bb14d1c90f301f 0.245582235 -> 0.230148211; 711abb923942f9fe **0.125038907 -> 0.171852019**; 8269991eafa82c45 0.419757752 -> 0.419757752; a0c46036cc19092a **0.230681884 -> 0.269906202**; a8a4c11ebcc1dde2 0.166682281 -> 0.113050916. У остальных групп original reference отсутствует. Все групповые clean/fault/MAE/p95/bias/recovery значения экспортированы в per_group.csv.

Существенные локальные ухудшения:

| Случай | Baseline -> H37 | Рост |
|---|---|---:|
| 30618_88548b02/rover, dropout10, event RMSE | 0.244900058 -> 0.563468217 м/с | **+130.080884%** |
| тот же bag/master, dropout10 | 0.244553348 -> 0.562048408 м/с | +129.826503% |
| 30639_e4379d7f/rover, dropout10 | 0.350459468 -> 0.507356737 м/с | +44.769020% |
| 30618_88548b02/master, dropout5 | 0.091524940 -> 0.131541715 м/с | +43.722262% |
| 30639_c31df386/rover, full-bag distance при dropout10 | 24.093163480 -> 25.578997533 м | **+6.167036%** |

Последняя строка — локальная дистанционная регрессия, не нарушение прошедшего aggregate distance gate +0.153417%. Все положительные локальные RMSE/MAE/p95/|bias|/distance/recovery изменения сохранены отдельно.

Диагностические clean-фазы: первые2s тяги RMSE +0.594176%, выбега -1.102129%, торможения -0.294738%; high-speed partial-command slice +0.380719%. Они не используются как новые критерии и не заменяют original suite.

## 7. Активация и дистанция после восстановления

44 409 clean ticks с существенным прямым target delta на baseline-состоянии. Выходная скорость изменилась более1e-6 м/с на 86 840 clean ticks; 59 470 из них относятся к bags с reference в 5 исходных группах. Поле driver `effective_reference_ticks` означает ticks в reference-bearing bags, не обязательно пересечение каждого tick с reference mask. Зарегистрированный минимум200ticks/3группы выполнен. Соседние такты не объявлены независимыми опытами.

Пример original dropout10 `30618_88548b02` [125.6,135.6)s, штатное cropped окно: перед отказом t=125.550029 drive_a v8/H37=0.841910/0.882581, d=0.007258/-0.049225 м/с². В outage t=130.600029 drive_a=0.121586/0.218829, d=0.029909/-0.024480, v=10.721164/10.889696 м/с. К t=135.550029 v=10.412741/10.899930. После восстановления t=145.550029 скорости совпали до округления, но delta_s=+2.503903м не стерлась.

В ОТДЕЛЬНОМ полном replay этой инъекции остаточная delta_s на первом общем подтверждённом rover-recovery составляет +2.577185м, через10s +2.576175м, в конце bag **+2.579124м**. Различие с cropped delta_s ожидаемо: полный replay имеет другой начальный контекст. Эти offsets — разница выходов, не самостоятельный GNSS distance score; scorer.distance_surrogate сохранён отдельно. Ничего не сбрасывалось ради метрик.

Трасса показывает изменение drive_a и обученного d при прежнем learning rule. Она не доказывает истинную семантику controller, нагрузку или причинную декомпозицию ошибки. Retuning по трассе не проводился.

## 8. Тесты, CPU и отсутствующие этапы

В текущей локальной среде повторно выполнены: **156 штатных tests PASS; 43 research-integrity PASS; 22 H37/foundation PASS; compileall PASS**. Наборы не выдаются за новые независимые bag-испытания. Проверены целостность полного snapshot, all-state/off parity, q0/q1/force-limited/braking, causal prefix/future/duplicate/stale/reset, quarantine/zero-lock, bounded state и согласованность интеграла.

Cost.py исполнен без изменения, exit0. Два заранее заданных workload: первый development bag 30618_0652866c, prefix180s, и первый original fault с baseline target activation: 30618_117c2d02/bias5,15 active target ticks. Последний bag без reference допустим для CPU; он выбран не по ошибке. Для каждого workload три AB/BA цикла, всего24 replay,10s прогрев исключён, threads1, одинаковые collectors; output hashes стабильны во всех повторах.

| Workload | Step CPU, медиана парной дельты | Диапазон | Replay CPU |
|---|---:|---:|---:|
| Prefix180 | +0.710249% | -1.225733..+2.661768% | -0.069405% |
| Active original | -0.000908% | -6.599371..+8.187382% | -0.384962% |

Шумовые интервалы пересекают0: убедительного выигрыша или существенного роста CPU этот небольшой замер не устанавливает. Это offline CPU, не publisher/subscriber latency или RSS ноды. **Enabled installed ROS оба clocks / 2CPU / 500000000bytes / latency / RSS / GetParameters / import hashes: NOT_RUN_AFTER_REJECTION.**

Предыдущие Actions run36231364281 attempts1/2 без runner/шагов остаются неуспешными. Новый результат получен локально, не объявляется успешным CI и не запускает новый train. Foundation run36230785305 остаётся ранее выполненным. Validation/test отсутствуют по stop rule, не из-за нынешней недоступности датасета. Runtime readiness=false.

## 9. Исходные результаты и воспроизведение

В новом пакете `R4-H37-completed-evidence.zip`: неизменные raw development SUMMARY/results/bags/access/traces, cost repeats и execution receipt, source/data receipts, тестовые логи, PLAN, runtime patch, exact source overlay и baseline ZIP. Крупные сжатые traces и dataset не коммитятся. Сам dataset в evidence ZIP не включён. Пакет возвращён в ответе текущего чата; Git сохраняет этот отчёт и компактный SUMMARY. Предыдущие blocked/foundation отчёты не переписаны.

CSV: per_bag_receiver, per_group, regressions, full_distance_offsets, recovery, activation, phases. Postprocessing только читает сохранённые JSON; не запускает replay или новый подбор. Оригинальные SUMMARY/results остаются неизменными.

Воспроизведение из полного repository checkout; сначала положить приложенный архив в dataset/dataset.zip:

```bash
git fetch origin research/R4-H37 checkpoint/R4-H37-foundation-36230785305-1
git worktree add --detach ../hack-H37-repro 14a9aa29a87a9b8e6d33c6b063bed1dac696bde7
cd ../hack-H37-repro
python3.13 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-research.txt
export PYTHONPATH=src/reserve_odometry OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
export H37_MEASURED_SHA=14a9aa29a87a9b8e6d33c6b063bed1dac696bde7
python research/R4/H37/bootstrap.py
mkdir -p dataset
cp /path/to/dataset.zip dataset/dataset.zip
python research/R4/H37/prepare.py --output /tmp/H37-prepare-new
git show eeb33182e0e2942f7e35fcb6dd55ed9577e01d53:reports/research_R4/H37/foundation-36230785305-1/train/SUMMARY.json > /tmp/H37-foundation.json
python -m unittest discover -s tests -v
python -m unittest discover -s research/tests -v
python -m unittest discover -s research/R4/H37/tests -v
python research/R4/H37/development.py --foundation /tmp/H37-foundation.json --output /tmp/H37-dev-new --workers 2
python research/R4/H37/cost.py --development /tmp/H37-dev-new --output /tmp/H37-cost-new
```

Новые output directories обязательны. Repository prepare.py извлекает train+development, но train не запускает; фактическое продолжение использовало helper extract_development.py из пакета и извлекло только17 development DB. Для архивного воспроизведения без Git в пакете отдельный reproduce.sh с теми же pins. Checkout уже содержит модуль: повторный git apply не нужен.

**Вывод: область механизма покрыта, кандидат активен, но проверенный порядок saturation не улучшает резервную одометрию по контракту. REJECTED. Это не доказательство универсальной непригодности force-command моделей. Сохранить canonical v8; PR не для merge.**
