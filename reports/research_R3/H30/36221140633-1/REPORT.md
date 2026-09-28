# R3-H30 — REJECTED на development

**Исследовательский отрицательный результат, не готов к merge.** Один кандидат `H30_joint_native` реализован и измерен на всех development bags. Clean-выигрыш недостаточен, original fault RMSE и дополнительная H11 common-mode suite регрессировали. Validation/final test не открывались. Параметры, алгоритм и пороги после результатов не менялись. Merge/auto-merge не выполнялись.

## Версии и изоляция

| Назначение | SHA / значение |
|---|---|
| Round | R3-v8-fixed |
| Общий baseline | e3b0c9c039d2953fbfcda51231263d38ef9f1024 |
| Baseline класс / профиль | GuardedReadoutObserver / champion_v8.yaml |
| Предварительная регистрация диагностики | fb56cdcc950622f86fa9720da87d8d7d0d0dafcc |
| Vehicle-only diagnostic source | e0948bfcbfc11105077021001891a15e731563fc |
| PLAN до реализации и accuracy | 4f99d977f263d260b79b149f99dadd61a398c200 |
| **Измеренный candidate/driver/tests** | **f1a940ebb8ea4694efcbc20d96b9062befdc4ab5** |
| Development run / attempt | 36221140633 / 1 |
| Immutable outcome checkpoint | f0398cfc1d10e5491f9945650311973a259164dc |
| Validation freeze | **N/A — допуск не пройден** |
| Ветка | research/R3-H30 |

Поздний commit этого отчёта содержит только отчёт/аудит/манифест, не новую версию алгоритма. Его SHA указан в PR. Перед созданием своей ветки проверены exact scientific ID в branches/PR и exact ref, совпадений не найдено. Moving main/чужие R3-кандидаты не включались.

Полный effective profile загружен из точного YAML: 20 Hz, delay=0, readout gain1/holdoff.5, adaptation_tau.5, wheel_time_compensation0, quarantine1.5. Сравниваются возвращаемые Estimate.v/s, не observer.v/s. Canonical src/profile/launch/scorer/split не изменены.

## Предварительно измерено основание

[Vehicle-only run 36220315911](https://github.com/jabrailkhalil/hack/actions/runs/36220315911): 17 development bags /7 исходных групп, 616942 input events, 319835 ticks. Instrumented observer точно совпал с обычным v8. GNSS/reference не загружался.

147997 потенциальных согласованных delayed pairs в7 группах; 73257 со stamp старше предыдущего output. Для296255 accepted wheel samples: mean age53.948ms, p50 49.737ms, p95 108.250ms, p99 129.467ms, max249.971ms. Это потенциальное вмешательство, не accuracy gain.

**Область покрытия:** accepted sample со stamp старше уже усвоенного последнего wheel measurement —0. Межканальных source-time inversions111387; это не равно такому OOSM. До последнего output Timeline не передал observer24077 уникальных controller stamps,74 front и105 rear (coalescing/drop не разделены); ещё17/2/2 относятся к хвосту. H30 не меняет Timeline и не восстанавливает невидимые события. Реальное покрытие — запаздывание assimilation относительно output; общий OOSM — только в линейном oracle.

## Один механизм, не повторная ассимиляция

Выбрана совместная cross-covariance, **не forward replay**. Для локальной additive-error модели с F=1 хранятся bounded states, cross covariance, переходы и event ledger. Вставка tau между l,r использует conditional Brownian bridge, включая q*dt*lambda*(1-lambda), затем:

```
S = P[tau,tau] + R
K[i] = P[i,tau] / S
mean[i] += K[i] * (z - mean[tau])
P_new = expanded Joseph update with old cross terms
```

Уточняются прошлые внутренние means и текущая marginal, но уже опубликованные Estimate не переписываются. Nominal drift удерживается между узлами; drive/dynamics не переигрываются. Прежний disturbance update выполняется один раз по raw samples, без повторного обучения d.

Native branch: только два уже принятых исходными hard gates согласованных колеса с одним timestamp, свежая команда, доступная history, отсутствие near-zero/sign/clamp границ. R сохраняет sigma² correlation floor (НЕ /2) и прежнюю robust форму по native innovation. Source raw/rate/model, stop/zero-lock/quarantine/recovery predicates сохранены. Дополнительный native-model gate — только veto.

Single/skew pair, stale, hard rejection, out-of-history, capacity и nonlinear boundaries используют явный legacy fallback. Event ledger и original used stamps исключают повторное conditioning/assimilation. Пределы:32 state slots/32×32 covariance и64 retained input/ledger records. Runtime без NumPy/SciPy. В реальном эксперименте отдельные максимумы:9 state slots,3 assimilation-ledger entries,11 input entries.

Feature-off воспроизводит **весь v8 с readout gain1**. При native update и допустимых prediction ticks прежняя age-поправка не накладывается второй раз. При legacy fallback возвращается исходный guarded readout/holdoff. Накопленная distance correction не сбрасывается, s остаётся trapezoidal integral опубликованной v.

**Включение:** `research/R3/H30/factory.py: candidate(enabled=True)`. Checkout и canonical ROS launch H30 не включают. `algorithm.patch` — hook-точки core/readout; ему нужны factory.py/joint.py, это не самостоятельная installed ROS-интеграция.

## Измеритель и данные

Один кандидат без настройки коэффициентов. Все17 development bags/7 групп; clean reference в6 группах/19 bag-receiver парах,15 missing receiver-пар не заменены нулём.394221 matched samples. Два receivers одной записи не считаются независимыми поездками.

Original suite56 faults/60 reference comparisons (5 reference groups); low-speed lock26/34 (6 reference groups); H11 common-mode28/30 (5 reference groups). Всего127 paired replay cases с clean. Original score/anchors/windows прежние. H11 injection/anchors использованы из baseline функций, low-speed predicate перенесён из опубликованного PR13 на разрешённый development. Новые suites не подменяют original-suite admission.

Исполнены исходные evaluate.replay/score, match/distance, v6 summary/decide. Меняются factory и прозрачный collector. Legacy ключ v5 в decide — технический alias реально исполненного полного v8, не подставленные старые числа. R3 добавляет внешние veto без изменения scorer. Inputs/injections/arrival order, output schedule и masks у baseline/candidate одинаковы; hashes сохранены.

Read-only loader проверяет role/DB hash до IO. Распакованы только development DB members checksum-pinned архива. Train/fitting в этом беспараметрическом кандидате не требовались. Train GNSS, validation/test measurement payload не читались. Исторические integrity tests проверяют старые артефакты, не запускают новый final test.

## Агрегаты — только development

Положительная delta ошибки означает ухудшение.

| Метрика | Baseline v8 | H30 | Delta |
|---|---:|---:|---:|
| Clean macro RMSE, m/s | 0.092668142983 | 0.092624472109 | −0.0471261% |
| Original fault-event macro RMSE, m/s | 0.237548612056 | 0.244565657514 | **+2.9539408%** |
| Pooled clean RMSE, m/s | 0.129305694477 | 0.129269944935 | −0.0276473% |
| Scalar-span distance RMSE, m | 5.310295004801 | 5.313445070127 | +0.0593200% |
| Clean macro MAE, m/s | 0.034933352905 | 0.034906850929 | −0.000026501976 m/s |
| Clean macro signed bias, m/s | +0.006390677420 | +0.006390365955 | −0.000000311465 m/s |
| Clean macro p95 error, m/s | 0.090092790092 | 0.089986145458 | −0.000106644634 m/s |
| Original fault+recovery-window macro MAE, m/s | 0.153796529331 | 0.156067110455 | +0.002270581124 m/s |
| Original fault+recovery-window signed bias, m/s | +0.011170307852 | +0.016163349863 | +0.004993042011 m/s |

≥2% clean ИЛИ≥5% original fault gain —FAIL. Original fault regression≤0.5% —FAIL. Legacy reasons: aggregate_regression, insufficient_gain. R3 добавляет common_mode:event_regression.

| Дополнительная suite | v8 event RMSE | H30 event RMSE | Delta | Veto |
|---|---:|---:|---:|---|
| Low-speed lock | 0.368545673306 | 0.361019982370 | −2.0420% | PASS по event/safety gate |
| H11 abrupt common-mode | 0.100632272301 | 0.103226034445 | **+2.5775%** | **FAIL** |

Low-speed window RMSE, несмотря на event gain, ухудшился0.317137344560→0.318737051645 (+0.50442%). Улучшение common-mode window RMSE не отменяет failure event gate.

**Активность:**95878 native updates/95878 material changes относительно обычной коррекции из того же pre-update state;47005 updates со stamp до предыдущего output. В6 группах≥100 изменений, в7-й24. Coverage gate пройден. Меняются212945 clean outputs; max clean |delta_v|=0.111983156m/s. Это активность, не accuracy gain.

## Группы и существенные регрессии

| Группа | Clean RMSE delta | Original fault-event delta |
|---|---:|---:|
| 2cd82bc27dbad052 | −0.77527% | N/A |
| 664cca45aeb0db23 | N/A | N/A |
| 70bb14d1c90f301f | −0.00998% | −4.49127% |
| 711abb923942f9fe | −0.15131% | −5.34261% |
| 8269991eafa82c45 | −0.01751% | +1.32189% |
| a0c46036cc19092a | +0.01224% | **+20.35100%** |
| a8a4c11ebcc1dde2 | +0.04090% | +0.18030% |

У a0c46036cc19092a common-mode event +26.62455%. Low-speed группы2cd82bc27dbad052/8269991eafa82c45 ухудшились на2.98999%/6.28569%, хотя общий event aggregate лучше.

Clean pairs:12 лучше/5 хуже/2 равны. Worst clean30639_9c362687/master:0.078329692212→0.078395116640m/s (+0.08352%), ниже per-bag gate. Distance8 лучше/9 хуже/2 равны; worst relative30639_0ab96c59/master:0.110114683798→0.111619795549m (+1.36686%); distance gate ограничивает агрегат.

Существенные fault cases:
- Original lock3s,30618_27e994fc/rover:0.038466047613→0.062333283619m/s (**+62.0475%**); master+58.2557%.
- Original lock3s,30639_e4379d7f/rover:0.157777966146→0.213868991868m/s (+35.5506%).
- Common-mode+5m/s на0.7s,30639_e4379d7f/rover:0.034210231865→0.077883677452m/s (**+127.6619%**).
- Low-speed lock5s,30639_c31df386/master:0.169302441948→0.197514803529m/s (+16.6639%).

Original recovery медленнее в3 receiver cases:30618_073f08d1/dropout10s master/rover2.165782164→2.265782164s (+0.1s);30618_27e994fc/rover/dropout10s2.400035175→2.450035175s (+0.05s). Low-speed:1 case медленнее на0.1s,2 быстрее на0.05s,2 быстрее на0.15s. Common-mode recovery не изменился. Все8 изменений сохраняет audit.py.

Coverage/n одинаковы. False stops clean/original/low/common0→0. Unrecovered original4→4, low6→6, common2→2; индивидуальных новых нет. Causal errors/unexpected Timeline resets0 во всех127 cases. `hard_resets=98604` в activation — сброс собственной covariance history при fallback, **не** Timeline reset; s/d им не обнуляются.

## Математика, проверки, цена

Wolfram подтвердил порядок conditioning, exact conditional bridge и неотрицательный bridge noise для явно заданной linear-Gaussian модели. Independent batch/chronological oracle:30 seeded streams/360 delayed updates; Actions max mean error3.3306690738754696e−15, max covariance error4.440892098500626e−16, min eigenvalue4.301316453749452e−5. Thresholds1e−9/−1e−10 PASS. Worksheets/output/assumptions сохранены. Нелинейная устойчивость не доказана.

[Research run](https://github.com/jabrailkhalil/hack/actions/runs/36221140633) success:156/156 full unit,43/43 integrity,25/25 H30,compileall. Feature-off по каждому original field/Estimate на395043 ticks всех127 cases совпал с независимым полным v8; replay arrays/counters равны. Тесты покрывают PSD/zero-age/irregular arrivals, duplicate accounting, bounds/causal-prefix, once-only d, no-double-readout, integral/immutable outputs, stale/future/reset/zero-lock/quarantine.

[CI измеренного source](https://github.com/jabrailkhalil/hack/actions/runs/36221140600):core/research-integrity/ros-humble/offline-limited все success. ROS проверяет неизменённый canonical runtime, **не enabled H30**.

Локальный аудит artifact: ZIP SHA256 совпал,26/26 source/pin hashes; summary/decisions пересчитаны без replay с точным совпадением;17/17 baseline array hashes совпали с отдельной vehicle-only диагностикой. Полный research patch прошёл git apply --check/применение,18/18 файлов совпали с measured source. Повторно156+43+25 tests/compileall/oracle PASS. Локального нового real-bag replay нет. Local CPython3.13.5; Actions3.13.15,NumPy2.3.5,SciPy1.17.0.

На первом dev bag30618_0652866c:1 warmup pair+6 alternating AB/BA pairs,threads1,одинаковые collectors. Median paired overhead: **step CPU+66.6729%,replay CPU+45.8663%,replay wall+45.8653%**. Median step36.1813→60.5222µs; replay CPU1.609286→2.359279s на29287 calls/29207 outputs. Output hash каждой реализации постоянен между её повторами.

Это offline cost, не ROS latency/RSS. Installed enabled H30 в обоих clock modes под2CPU/500000000bytes: **NOT_RUN_AFTER_REJECTION**. Validation:**NOT_RUN_AFTER_REJECTION**,freeze N/A. Final/test:**NOT_OPENED**. Runtime verification/merge readiness=false.

## Источники и ограничения

H01/PR21, точные H12/H14 отчёты, baseline/runtime/evaluator прочитаны; уровни чтения в research/R3/H30/SOURCES.md. Indexed IEEE abstract Bar-Shalom2002, DOI[10.1109/TAES.2002.1039398](https://ieeexplore.ieee.org/document/1039398/) подтверждает постановку exact OOSM update; full text не прочитан. Known Consensus/Scite quota stops не обходились, новых запросов к ним в R3 не было, citation contexts не проверены.

F=1/удерживаемый drift — локальная additive-error approximation; нет joint uncertainty d/drive. R зависит от innovation, поэтому exact fixed-R oracle нельзя полностью перенести на nonlinear runtime. Raw gates не превращены в универсальный OOSM ingestion. Distance — scalar GNSS-speed surrogate, не XY/ENU. Нет нового independent final test/installed enabled benchmark. Причина fault-регрессии по внутреннему state trace не локализована: объяснение через доотказное состояние остаётся гипотезой.

## Воспроизведение и evidence

```bash
git checkout f1a940ebb8ea4694efcbc20d96b9062befdc4ab5
python -m pip install -r requirements-research.txt
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
PYTHONPATH=src/reserve_odometry python -m unittest discover -s tests -v
python -m unittest discover -s research/tests -v
python -m unittest discover -s research/R3/H30/tests -v
python research/R3/H30/oracle.py
python research/R3/H30/stage_data.py --stage development --journal /tmp/H30-stage.json
python research/R3/H30/run.py --stage development --output /tmp/H30-fresh --workers 2
```

Output должен быть новым. Validation/test stages отсутствуют. Фактические команды: logs/execute.log в checkpoint. Повтор — воспроизведение, не новый подбор.

[Immutable checkpoint](https://github.com/jabrailkhalil/hack/tree/f0398cfc1d10e5491f9945650311973a259164dc/reports/research_R3/H30/36221140633-1) содержит experiment/bags/*.json, per_bag_receiver_fault.csv, per_group.json, SUMMARY.json, COST.json, STARTED.json, ORACLE.json, algorithm.patch и логи. Raw bags и гигантские дублирующие traces не коммитились.

[Evidence ZIP](https://github.com/jabrailkhalil/hack/actions/runs/36221140633/artifacts/10899183691):3776715bytes,SHA256`05e1c22dc85c97f689492cac4e3fa84918da4f3ff19d43a5e11606c844d9c78c`,retention до26.10.2026. ZIP содержит полный measured source.zip, не дублируемый в Git checkpoint. Компактные данные остаются в checkpoint независимо от retention.

Поля: mechanism_status=IMPLEMENTED_AND_SANITY_TESTED;coverage_status=SUFFICIENT;scientific_verdict=REJECTED;accuracy_contract_passed=false;runtime_verified=false;ready_to_merge=false. Отвергнут один проверенный вариант, не всё семейство native-time updates. **Не сливать.**
