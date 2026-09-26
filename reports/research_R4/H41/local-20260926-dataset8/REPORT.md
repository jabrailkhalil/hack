# R4-H41 — REJECTED: совместная коррекция скорости и привода

**Исследовательский отрицательный результат, не готов к merge.** После получения датасета реализован и измерен один зарегистрированный observer [v,drive_a]. Clean RMSE улучшился на **0.631869%**, original fault-event RMSE — на **2.195826%**, но необходимые 2% либо5% не достигнуты. Единственная причина численного отказа — `insufficient_gain`. Механизм активен, покрытие достаточное. Пороги и параметры не менялись. Validation/final test не запускались, freeze не создавался.

## Версии и продолжение

- Baseline: `e3b0c9c039d2953fbfcda51231263d38ef9f1024`, полный tree `eae49a504bc59b5c9b408445150bef32e111956f`.
- PLAN до экспериментов: `40acde8b32ecceac5cb4b9099ef6ba22ff5740d1`, `research/R4/H41/PLAN.md`.
- Выполненная passive foundation: исходники `41dfa6a56945e670d920ca39420a084ca861a634`; foundation.py byte-identical прежнему опубликованному probe.
- **Измеренный candidate source: `d1381c61e771a104eb2fc65853b60ec5c861843c`**, опубликован до первого candidate development comparison.
- Execution ID: `local-20260926-dataset8`. Ветка `research/R4-H41`, существующий draft PR #53.
- Report/checkpoint SHA привязан в последующем SUMMARY.json; это более поздний отчётный commit, не новый алгоритм. Freeze SHA=N/A.

Предыдущий `blocked-36231187948-1` сохранён без редактирования. Это продолжение своей задачи, а не второй H41. Main, чужие ветки, release manifests и ci.yml не менялись; merge/auto-merge/force-push не выполнялись.

## Источники и реальные данные

Source ZIP SHA256 `a8e0bfa033e0a02c460c30b02f34a5c64ece85b05003512941387d3cf1f319a2`: повторно проверены **301/301 исходных paths/bytes/executable bits**, полный tree совпал. .git отсутствует, фиктивный remote ancestry не создавался. Все301 канонических файлов рабочей копии остались неизменными и после исследования.

`dataset(8).zip`: **256294592bytes**, SHA256 **`d0b2483e13990edb8219b0d7bbcafc7ed001cce549a4d3af467069b2472e7d52`**. Из nested archive распакованы только **64train и17development DB**; SHA256 каждого совпал с исходным split. Validation/test DB не распакованы и не открыты. Train SQL читает только controller/front/rear; GNSS доступен лишь внешнему scorer на development. Missing reference остаётся null, не нулём.

Первый локальный foundation вызов прерван лимитом инструмента после34bags, partial log/directory сохранены. Тот же код и данные повторены до завершения: это инфраструктурный повтор, не новый вариант. Предыдущий Actions run36231187948 остаётся failure до назначения runner. Новые успешные CI/Actions/artifacts не заявляются: это продолжение выполнено локально.

## Foundation до реализации

Все64train bags дали **1366299 outputs**, **79899 trusted transient pairs**, **14040 завершённых shadow episodes**. Переходы, эпизоды и RMS-условие представлены в25исходных группах. **99.786325%** эпизодов имеют изменение скорости>=0.01м/с при initial-A perturbation ±0.1м/с², вместо требуемых>=50%. Все зарегистрированные minima выполнены: `FOUNDATION_PLAUSIBLE_NOT_IDENTIFIED`.

Эти данные разрешили проверку заранее заданного кандидата, но не использовались для подбора covariance. Wheel residual — псевдоразметка, A±0.1 — условная чувствительность модели на реальных командах. Это **не измерение истинной ошибки A, не идентификация Q_A и не14040 независимых поездок**.

## Реальный алгоритм

`VelocityActuatorObserver` хранит симметричную2×2covariance состояния [v,A], A=drive_a. Один engineering prior: **S_A=0.09 (м/с²)²**, P_AA=S_A при reset/bootstrap/STOPPED, P_vA=0. Q_A=S_A(1−rho²)LLᵀ, rho=exp(−h/tau), L=[h*s_v*s_a,1]. Старый velocity Q сохранён, добавлено h²S_d, S_d=0.09, как step-local allowance. Оно **не гарантирует покрытие постоянного неизвестного d** и не является calibrated CI.

Mean predictor, физические коэффициенты и drive-before-Euler схема прежние. P-=F P Fᵀ+Q использует Jacobian именно этой схемы, включая torque/power/brake/coast, saturation/no-reversal. H=[1,0]. На новой доверенной FUSED-паре innovation корректирует v и A; при недостатке доверия K_A=0. A ограничен физическим диапазоном. Полная Joseph covariance использует фактически применённый K_A после clipping; K_A=0 также даёт согласованное cross-update. PSD/floors/congruent caps — численные safeguards, не доказательство nonlinear stability.

Legacy d не входит в joint state и не получает прямой joint innovation. Формула его адаптации прежняя; траектория d может косвенно измениться через исправленные A/v. Raw/rate/model/zero-lock/reacquisition/quarantine формулы не ослаблены. Новый prior влияет на прежнюю covariance-dependent часть gate, поэтому идентичность всех решений enabled-кандидата baseline не заявляется.

Readout получает **actual prior, K_v, pre-correction a_model**, без неверной старой scalar reconstruction и без acceleration из уже исправленного A. Интеграл опубликованной скорости согласован с s, distance correction при recovery не стирается. Runtime — только controller/front/rear, без GNSS/IMU/future samples/bag ID/fault flags. Дополнительные состояния — скаляры и насыщаемые counters, без тяжёлых runtime dependencies.

**Обычный checkout/canonical ROS launch не включает H41.** `runtime.py` создаёт isolated patched package; research factory явно конструирует `runtime.candidate_class()(config, readout=readout, enabled=True)`. Полный champion_v8 JSON/YAML, readout1/.5, quarantine1.5; не Config defaults. Фактические class/module paths, параметры и hashes сохранены в started.json.

Runtime patch SHA256 **`3693cc4e21c4e8cdd36de8994d623249c0ae0d6afac970e679d89b7a3f142625`**. `git apply --check/apply` на новой pristine-копии прошли, patched files совпали с измеренным package;6000enabled round-trip ticks дали точные outputs/состояния.

## Неизменный измеритель

Сначала canonical v8 заново исполнен на17development bags: все пять основных fingerprint полей совпали **точно, max delta0.0**. В paired candidate run baseline воспроизвёлся повторно. Старые значения не подставлены вместо исполнения.

`baseline_v2` в raw API — alias canonical v8, `balanced_physics` — enabled H41, `h41_off` — disabled. Off outputs/runtime counters точно равны canonical на всех clean/cropped original/low/common replay. Дополнительный full-faulted run исполняет canonical/enabled без третьего off.

Official score/replay/match/metrics/distance_surrogate и v6 aggregation не менялись. Подставлена только factory, пассивный collector не передаёт сведения estimator. Low-speed selection/durations взяты из точного PR13 source `f10e3cfc0689ecbd7894575945897a6696db3e72`, blob`7705f88fbcdfab49a8531dadffaa8e35e996f25c`. Common-mode +5м/с на0.7/1.2с — pinned H11. Дополнительные suites не заменяют original gain.

| Suite | Replays | Receiver cases с reference |
|---|---:|---:|
|Clean|17|19|
|Original cropped faults|56|60|
|Low-speed lock|26|34|
|Abrupt common-mode|28|30|
|Original faults на полных bags|56|60|

Development —7исходных групп, clean reference в6, original-fault reference в5. 15clean receiver-пар без reference сохранены. **394221 matched clean samples у обоих**, одинаковые timestamps/masks/n/coverage. Output source-time rate20Hz, delay0; это не измерение wall-clock ROS latency.

## Измеренная точность — development

Плюс означает рост ошибки.

| Метрика | Canonical v8 | H41 | Δ |
|---|---:|---:|---:|
|Clean macro RMSE, м/с|0.092668142983|0.092082601963|−0.631869%|
|Original fault-event macro RMSE, м/с|0.237548612056|0.232332457221|−2.195826%|
|Pooled clean RMSE, м/с|0.129305694477|0.128971287418|−0.258617%|
|Clean scalar-span distance RMSE, м|5.310295004801|5.304417592563|−0.110680%|
|Low-speed lock event RMSE, м/с|0.368545673306|0.369684271400|**+0.308944%**|
|Abrupt common-mode event RMSE, м/с|0.100632272301|0.098263345712|−2.354043%|
|Full-faulted scalar-span distance RMSE, м|6.269376947281|6.286614807452|**+0.274953%**|

**REJECTED / insufficient_gain**: clean0.631869%<2%, original fault2.195826%<5%. Остальные aggregate/per-bag/coverage/safety thresholds пройдены. Это не основание смягчить gain или расходовать validation. Decision точно пересчитан из raw results; алгоритм/параметры после измерений не менялись.

Clean MAE0.034933352905→0.034674632484, p950.090092790092→0.089091921946м/с. Signed bias **+0.006390677420→+0.006495120675м/с**, модуль хуже. Original fault+recovery MAE0.153796529331→0.151320079049, p950.456670428618→0.451175774411м/с, signed bias **+0.011170307852→+0.012392628026м/с**. Group-macro confirmed recovery0.724358284875→0.716545784875с; missing recovery не считается нулём.

False stops во всех suites0→0. Unrecovered: original4→4, low-speed6→6, common2→2, full-faulted4→4; это те же individual cases, не устранение baseline проблем. Нет новых individual failures/causal errors/unexpected resets. Receivers/ticks не считаются независимыми поездками; statistical significance не заявляется.

## Покрытие и регрессии

**102775 ненулевых actuator corrections в7группах**, **249424 изменённых v-ticks в7группах**, включая **17104 original-fault MODEL_ONLY ticks в6группах**. Предзаданный activation gate выполнен; это суммы коррелированных replay.

Clean RMSE:17/19пар лучше,2равны,0хуже. Но clean distance6/19хуже. Original event RMSE:37/60лучше, **23/60хуже**. Две из пяти reference-групп original fault ухудшились: `70bb14d1c90f301f` **+4.119860%**, `a8a4c11ebcc1dde2` **+4.275174%**.

| Случай | Показатель | Baseline | H41 | Регрессия |
|---|---|---:|---:|---:|
|30639_9c362687/rover/dropout10|original event RMSE, м/с|0.258670139|0.317420410|**+22.712429%**|
|30639_9c362687/master/dropout10|original event RMSE, м/с|0.257095610|0.315126535|+22.571729%|
|30639_c31df386/master/dropout10|original event RMSE, м/с|0.441399505|0.499039052|+13.058362%|
|30639_9c362687/rover/full dropout10|distance RMSE, м|19.581277723|20.025940176|**+0.444662453м**|
|30618_27e994fc/rover/dropout10|recovery, с|2.400035175|2.450035175|+0.05с|
|30618_0652866c/rover/low lock5|recovery, с|0.056501138|0.156501138|+0.10с|

Local full-faulted distance+2.270855% rover/+2.520756% master не равны нарушению aggregate1%: агрегат+0.274953%. Low-speed14/34event сравнений хуже, хотя агрегат+0.308944% проходит0.5%. Все строки и оставшиеся регрессии доступны в raw/per-case CSV пакета.

На всех56full-faulted replays сохранены delta_s после первого FUSED и в конце bag. Максимум |terminal candidate−baseline| **1.453624116521м** на30618_27e994fc/bias5. Это различие методов, **не ошибка относительно истины**. Distance — reanchored GNSS-speed scalar surrogate, не XYZ/ENU/полный terminal true drift.

После решения отдельный read-only replay неизменённого кандидата сохранил delta_s в exact reference-confirmed recovery:112receiver-строк с missing cases, **224 ранее сохранённых числовых значения воспроизвелись точно, max delta0.0**. Например30639_9c362687/rover/dropout10: recovery start146.05с, delta_s+0.569262878м; конец20-sample подтверждения147.0с, delta_s+0.569237118м; к концу bag+1.041573423м. Первый FUSED и подтверждённый recovery не смешиваются. Это post-result audit, не новый отбор.

## Проверки и вычислительная стоимость

156canonical unit +43integrity PASS. **16H41 tests PASS**, включая вложенный повтор27ObserverTests.6000exact-off ticks, bounded-state10000ticks для каждого synthetic scale0.5/1/2 (реальный кандидат только1), prefix/future/duplicate/stale/reset/NaN, zero-lock/quarantine, actual gain hook, непрерывный integral s. Матрицы/границы:

-1000actual Jacobian finite-difference cases, max delta`5.760738552851308e-10`;
-5000Joseph vs independent matrix cases с constrained gains, max delta`4.440892098500626e-16`, PSD PASS;
-compileall и patch round-trip PASS, все301canonical files неизменны.

8fixed synthetic cases прошли зарегистрированные veto: traction/coast/brake, load±.3/±.6 наoutage, false pair послеoutage, ramps±1.5. Небольшие negative-load RMSE регрессии сохранены: -0.6 case0.915669341→0.918793902, -0.3 case0.445955001→0.449331404м/с. Синтетика и ранняя Wolfram/SymPy algebra не доказывают real-data accuracy или nonlinear stability; текущие numeric checks проверяют уже реализованный observer.

Cost: первый180s development30618_0652866c,10s warmup; healthy и dropout[30,40). По1warmup+5измеренных AB/BAпар, threads1, одинаковые official replay/collectors,3400postwarmup steps. Output hashes стабильны в каждом методе, timestamps одинаковы.

| Scope | Метрика | Baseline | H41 | Ratio-of-medians Δ |
|---|---|---:|---:|---:|
|Healthy|step CPU, мкс/выход|27.388929|38.383726|**+40.143%**|
|Healthy|replay CPU, с|0.143725333|0.185618648|+29.148%|
|Dropout|step CPU, мкс/выход|25.196075|37.640411|**+49.390%**|
|Dropout|replay CPU, с|0.135630137|0.181935855|+34.141%|

Paired median stepCPU healthy+40.143%,active+49.308%; replayCPU+29.148%/+33.859%. Разброс healthy step+32.38…+73.87%,active+45.07…+64.62%; wall и все повторы сохранены. Replay timer заканчивается после materialization официального массива, одинаково содержащего warmup outputs. Whole offline RSS166608896bytes включает NumPy/входы/reference, **не RSS ноды**.

**Installed enabled ROS benchmark: NOT_RUN_AFTER_REJECTION.** ROS/rclpy/Docker локально отсутствуют, но основание остановки — уже отрицательный accuracy gate. Feature-off/default CI не сертифицирует H41. Новый CI не объявляется зелёным, новых успешных Actions не было. Финальный runtime_verified=false,ready_to_merge=false.

## Воспроизведение и evidence

Основное measurement source — d1381c61e771a104eb2fc65853b60ec5c861843c. Поздние benchmark/audit/recovery scripts добавлены в отчётный checkpoint и не меняют observer. Python3.13.5,NumPy2.3.5,SciPy1.17.0; исходные requirements-research.txt. В полном Git checkout:

```bash
export PYTHONPATH=src/reserve_odometry OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
export H41_MEASURED_SHA=d1381c61e771a104eb2fc65853b60ec5c861843c
OUT=$(mktemp -d /tmp/R4-H41.XXXXXX)
mkdir -p "$OUT/input"
cp /path/to/dataset.zip "$OUT/input/dataset.zip"
python research/R4/H41/foundation.py --stage data --output "$OUT/input"
python -m unittest discover -s research/R4/H41 -p test_joint.py -v
python research/R4/H41/synthetic.py --output "$OUT/synthetic.json"
python research/R4/H41/foundation.py --stage foundation --data-root "$OUT/input/data" --output "$OUT/foundation"
python research/R4/H41/compare.py --stage baseline --data-root "$OUT/input/data" --output "$OUT/baseline" --workers 2
python research/R4/H41/compare.py --stage development --data-root "$OUT/input/data" --output "$OUT/development" --workers 2
python research/R4/H41/benchmark.py --data-root "$OUT/input/data" --output "$OUT/cost.json"
python research/R4/H41/audit.py --input "$OUT/development" --output "$OUT/audit"
python research/R4/H41/recovery_audit.py --data-root "$OUT/input/data" --reference-results "$OUT/development/results.json" --output "$OUT/recovery"
```

Для исходного ZIP без.git сначала приложенный verifier; затем добавлять `--source-receipt /path/SOURCE_RECEIPT.json` к стадиям с source-check. Scorer/Timeline/split не редактировать. Outputs всегда новые; validation CLI отсутствует. Полные фактические локальные команды, журналы и точный PLAN переданы пакетом.

Raw development results SHA256: **`02fc61100f09914c49817447946ce70b086578602eea822169329eb7923e92d9`**. В Git — compact report/summary/tables/manifest. Полные JSON, per-bag/per-receiver/per-fault CSV, compressed traces и foundation episodes находятся в приложении чата, не в Git. Новый Actions artifact не создан,30-дневный retention не заявляется; raw bags не опубликованы.

Ограничения: инженерный prior не идентифицирован; persistent d/common wheel bias и correlated noise не превращены в наблюдаемые величины. Gain/PSD/clipping не гарантируют safety на всех inputs. Все conclusions относятся к одному reused-development эксперименту, без независимого final test. Прежние H10/H18/H26 отчёты прочитаны как контекст, их метрики не присвоены H41; исчерпанные Consensus/Scite квоты повторно не запрашивались.

**Оставить canonical v8. R4-H41 не продвигать, несмотря на измеренное частичное улучшение.**
