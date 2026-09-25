# H20 / R2-v7-fixed — асимметричный soft weight колёс

## Вердикт

**REJECTED. Исследовательский отрицательный результат, не готов к merge.** Выбранный на development кандидат `H20_alpha025` не достиг общего порога выигрыша: validation clean group-macro RMSE улучшился лишь на **0.00789934%** при требовании 2%; original fault-event group-macro RMSE ухудшился на **0.00236685%**, вместо требуемого альтернативного улучшения 5%. Автоматическая причина `insufficient_gain`; численные guards регрессии/coverage/false stops/recovery/причинности не нарушены.

Механизм действительно активен, а не лишён покрытия. Однако отдельная development-диагностика выявляет межзнаковый trade-off: уменьшение ошибки при отрицательном single-wheel slip в торможении сопровождается увеличением ошибки при положительном slip. Это дополнительный отрицательный результат механизма, а не основание заменить общую цель. Не утверждается опровержение всего семейства асимметричных likelihood. Проверены только две предзаданные силы одной реализации; на validation — только alpha=0.25.

## Неизменяемые версии и evidence

| Назначение | SHA / идентификатор |
|---|---|
| Общий baseline | `65bba39ed05c781f3f69a65c02f69931152cbfd9` |
| PLAN до реализации и измерений | `050c3fcece61de37bc42c0da9d7aa14d6f009c7f` |
| Измеренный алгоритм и driver | `130c96421931e307a9aedc207f4c835d54e4ac9c` |
| Отдельный опубликованный freeze | `17b9033cb7becd71008b99cf660ab133253a2f7c` |
| Итоговый checkpoint evidence | `f45d87f2ea3c6a8816d0c6a0add2ba424e3261ad` |
| Ветка реализации | `research/round2-H20` |
| Ветка evidence | `checkpoint/R2-H20-36185299933-1` |
| Измерительный run / attempt | `36185299933 / 1` |
| Evidence artifact | `H20-evidence-36185299933-1`, ID `10885179124` |
| SHA256 evidence ZIP | `168bfbd33b5c538d705eea762c68803581b8627e152ad5ebcb024dcf20a1e761` |

[Измерительный workflow](https://github.com/jabrailkhalil/hack/actions/runs/36185299933) завершён `success`: это успешное исполнение отрицательного эксперимента, не подтверждение улучшения.

[Все неизменяемые результаты](https://github.com/jabrailkhalil/hack/tree/f45d87f2ea3c6a8816d0c6a0add2ba424e3261ad/reports/research_R2/H20/36185299933-1), включая PLAN, freeze/publication, source archive, patch, access journal, logs, per-bag JSON/CSV и summaries. [Исходный PLAN](https://github.com/jabrailkhalil/hack/blob/050c3fcece61de37bc42c0da9d7aa14d6f009c7f/reports/research_R2/H20/preregistered-01/PLAN.md). Более поздний commit этого отчёта не является измеренным source SHA.

Baseline — настоящий `GuardedReadoutObserver` с `guarded_readout_v7.yaml`, gain=1, holdoff_s=0.5, inner wheel_time_compensation=0, adaptation_tau_s=0.5, 20 Hz / delay=0. Измерялись опубликованные Estimate.v/s, а не внутренние состояния. Числа H01–H10 относительно старого v5 не подставлялись. Текущий движущийся main, H11/v8 и чужие R2-кандидаты не включались. Main/чужие ветки/исторические отчёты не изменялись; merge/auto-merge не выполнялись.

## Реальное изменение алгоритма

[factory.py измеренного source](https://github.com/jabrailkhalil/hack/blob/130c96421931e307a9aedc207f4c835d54e4ac9c/research/R2/H20/factory.py) загружает pristine v7 и независимую приватную копию core с двумя hook-точками: получение уже рассчитанного модельного контекста и изменение z/R после прежних hard gates. Guarded readout наследуется без изменений. Канонические runtime-файлы не перезаписываются.

Для принятого колеса e_i=sign(v_pred)*(z_i-v_pred), b=3*sigma_wheel. Режим m=+1 — подтверждённая тяга, m=-1 — торможение:

```text
x_i = max(0, m*e_i)
q_i = x_i^2 / (b^2 + x_i^2)
w_i = 1 / (1 + alpha*q_i)
z_weighted = sum(w_i*z_i) / sum(w_i)
R_weighted = max(R_original, R_floor*max(1, abs(z_weighted-v_pred)/b)) / mean(w_i)
```

R_floor сохраняет прежнюю корреляционную границу: sigma² для согласованной принятой пары, иначе 4*sigma². R не уменьшается; фиктивного выигрыша 1/N нет. Вес лежит в [1/(1+alpha),1]. При alpha=0, неподтверждённом режиме или всех w=1 возвращаются исходные z/R без нового округления.

Режим требует |v_pred|>=0.5 м/с, согласованного направления предыдущей скорости/прогноза, свежей команды, согласия знаков drive_target, drive_a и a_model в направлении движения, порога 0.05 м/с² и непрерывной выдержки 0.5 с. Команда должна превышать deadband+0.05 по модулю. Смена режима/направления, stale, near-zero или рассогласование немедленно возвращают симметричный вариант. Это согласованность модели и controller, не доказательство истинного ускорения.

Истории не растут: фиксированное число скаляров и последняя диагностика максимум двух колёс. Нет GNSS/IMU/future/oracle inputs. Hard gates, абсолютный scale, stop/recovery, disturbance formula/tau, Timeline, matching и readout не меняются. Поправка inner soft update может косвенно влиять на последующие состояния; её нельзя считать output-only гипотезой.

**Включение:** `factory.candidate(0.25)` в изолированном driver. Checkout ветки сам по себе НЕ включает H20 в установленном ROS node. `algorithm.patch` — только две hook-точки; реализация класса находится в factory.py. Не применять hook patch к canonical core перед запуском factory: factory уже накладывает его на приватную копию. Полный исследовательский патч распространяется вместе с исходниками factory/driver/tests.

## Дизайн, роли данных, фиксация

Два разрешённых варианта alpha=0.25 и 0.50, baseline/off не считаются вариантами. Идентификация физических параметров не выполнялась; train GNSS не использован. Все 17 настоящих development bags, 7 исходных групп. Все 19 validation bags, 10 исходных групп. Два GNSS receiver одной записи не трактовались как независимые поездки; основная агрегация — неизменный group-macro. Бутстреп по ticks не применялся.

Baseline/candidates прошли один оригинальный `evaluate.replay/score` с заменой только factory. Сохранены исходные временная сетка, reference masks, matching и `guarded.fault_windows`, `legacy.summary/decide`. Совместимость имён старого decide обеспечена явным alias v4/v5 -> фактически исполненный baseline_v7, а не запуском этих старых observers. Дополнительно проверены pooled RMSE и per-case новые невосстановления. Формулы/пороги evaluator не переписывались. Хеши входов, выходных timestamps и reference masks сохранены; в driver проверяется точное совпадение timestamp arrays.

Распаковщик `stage_data.py` заменил предварительный эскиз команды общего get_dataset.py: тот же pinned organizer archive и read-only decoder, но распаковываются только DB разрешённой роли. На development validation DB ещё не распакованы. Train/test DB не распаковывались и не открывались; чтение ZIP metadata не является чтением SQL payload. Внешний evaluator получает разрешённый reference, runtime — только vehicle inputs. Архивные release-отчёты тесты читают, measurement test DB — нет.

Измеренный source опубликован push в **20:22:00 UTC**, development начат **20:22:30.866 UTC**. Оба варианта прошли запрограммированные development eligibility guards. По правилу минимального original fault RMSE, затем clean RMSE/меньшего alpha выбран alpha=0.25. Freeze создан в **20:24:57.305 UTC**, commit в **20:24:59 UTC**, push завершён **20:25:06.548 UTC**. Только затем распакован validation; его driver начат в **20:25:10.664 UTC**. Один validation, без изменений параметров после него. Эти времена подтверждаются Actions log и started.json, не только полем published_before_validation.

Контракт R2: gain clean>=2% ИЛИ original fault>=5%; clean/fault/pooled regression<=0.5%, scalar distance<=1%; clean per-bag/receiver<=base+max(0.005 м/с,5%); без потери coverage, дополнительных false stops, новых unrecovered/causality/resets. Числа/пороги не менялись после результатов.

## Покрытие и development

| Метрика | v7 | alpha=0.25 | alpha=0.50 |
|---|---:|---:|---:|
| Clean group-macro RMSE, м/с | 0.092668142983 | 0.092666120261 | 0.092666946658 |
| Изменение clean | — | -0.00218276% | -0.00129098% |
| Original fault group-macro RMSE, м/с | 0.237548612056 | 0.237558294407 | 0.237568018921 |
| Изменение fault | — | +0.00407594% | +0.00816964% |
| Scalar-span distance RMSE, м | 5.310295004801 | 5.310475440679 | 5.310656675796 |
| Pooled clean RMSE, м/с | 0.129305694477 | 0.129307484178 | 0.129309746074 |

Источник: `experiment/development/summary.json`. 394221 matched reference samples, 19 clean bag/receiver pairs с reference; ещё 15 пар без reference сохранены как missing, не как нулевая ошибка. 56 original fault scenarios / 60 reference comparisons. 308 отдельных диагностических fault scenarios. В synthetic suite — 18 предзаданных комбинаций направления, mismatch и fault; это не доказательство реальной accuracy.

Alpha=0.25 изменил **34215 из 148238 accepted updates (23.0811%)**; alpha=0.50 — 34228 (23.0899%). Подтверждённая тяга 2951.05 с, торможение 3125.25 с. У 6 исходных групп выполнен порог >=5 с обоих режимов; требовалось >=2 группы и >=200 changed updates. Оба знака реально взвешивались в diagnostic suite. Механизм не был неактивным. На validation alpha=0.25 изменил 54224 из 215000 accepted updates (25.2205%). Знаки innovations/weights, fallback, состояние inner/readout и ограниченные traces до/во время/после отказов сохранены в per-bag JSON. Fault identity содержится только во внешнем Monitor, не передаётся observer.

## Главный validation результат

Отрицательное изменение RMSE означает улучшение.

| Основная метрика | v7 | H20 alpha=0.25 | Абсолютная дельта | Изменение |
|---|---:|---:|---:|---:|
| Clean group-macro RMSE, м/с | 0.114549861317 | 0.114540812637 | -0.000009048681 | -0.00789934% |
| Original fault-event group-macro RMSE, м/с | 0.538286782601 | 0.538299523032 | +0.000012740431 | +0.00236685% |
| Pooled clean RMSE, м/с | 0.216406794155 | 0.216398385221 | -0.000008408934 | -0.00388571% |
| Scalar-span distance RMSE, м | 4.595480653018 | 4.595142342585 | -0.000338310433 | -0.00736181% |

Источник: [validation summary](https://github.com/jabrailkhalil/hack/blob/f45d87f2ea3c6a8816d0c6a0add2ba424e3261ad/reports/research_R2/H20/36185299933-1/experiment/validation/summary.json). 698891 matched samples; 30 clean bag/receiver comparisons с reference; 8 пар без reference. 76 original fault scenarios / 120 reference comparisons. Ни одна запись не исключалась по ошибке кандидата.

Дополнительные описательные clean group-macro: MAE 0.047549651404 -> 0.047547026045 м/с; signed bias -0.015975155952 -> -0.015977212550 м/с; p95 0.131696583956 -> 0.131696504186 м/с. Они не заменяют admission RMSE. Recovery_s совпадает во всех исходных fault-сравнениях; mean по 120 непустым сравнениям 0.254840173467 с у обоих. Clean false-stop samples 18 -> 18, fault 0 -> 0; unrecovered 0 -> 0. На development исходные unrecovered 4 -> 4 у обоих кандидатов, не скрыты.

Coverage/n совпадают для всех paired comparisons. Causal errors и неожиданные resets: 0 у всех. Validation Timeline dropped events: 66 у baseline и candidate; это существующие одинаковые drops, не ноль. Дополнительного снижения coverage нет.

## Локальные регрессии и межзнаковый компромисс

На validation clean RMSE улучшился в 13/30 пар и ухудшился в 17/30; это не равномерный выигрыш. Максимальная абсолютная clean-регрессия: `30639_9f0b519f/master`, 0.035390834649 -> 0.035396486858 м/с, +0.000005652209 (+0.0159708%). Максимальная относительная clean-регрессия: `30618_437e855c/master`, +0.0163648%. Все ниже per-bag guard.

Original fault event RMSE ухудшился в 50/120 сравнений. Наибольшая относительная регрессия: `30618_2f104a1d/master`, bias [125.2,130.2), 0.039658175450 -> 0.039840283536 м/с, +0.000182108086 (+0.459194%). Наибольшая абсолютная: `30639_3b3d9eb8/rover`, lock [122,125), 0.144284293467 -> 0.144543447537 м/с, +0.000259154070 (+0.179614%). Distance ухудшилась в 11/30 clean pairs; худшая `30639_50956d6e/master`: 1.289284923030 -> 1.290488337946 м, +0.001203414916 (+0.0933397%). Замедлений recovery/new unrecovered на validation нет.

Заранее объявленная дополнительная development-suite, alpha=0.25, описательный event group-macro по исходным группам, НЕ admission suite:

| Режим/сценарий | v7, м/с | H20, м/с | Изменение |
|---|---:|---:|---:|
| Торможение, front bias -0.3 | 0.150430653 | 0.148318053 | -1.40437% |
| Торможение, front bias +0.3 | 0.166130686 | 0.168292198 | +1.30109% |
| Торможение, front gradual -0.8 | 0.236185416 | 0.229091300 | -3.00362% |
| Торможение, front gradual +0.8 | 0.263888820 | 0.271997709 | +3.07284% |
| Торможение, rear gradual -0.8 | 0.237994498 | 0.230882364 | -2.98836% |
| Торможение, rear gradual +0.8 | 0.264364851 | 0.272518486 | +3.08424% |
| Тяга, front gradual +0.8 | 0.237057255 | 0.235117295 | -0.81835% |
| Тяга, front gradual -0.8 | 0.266293587 | 0.267669221 | +0.51659% |

Для каждой braking строки 5 reference groups / 15 receiver comparisons, traction 6 / 17. Знаки amplitude заданы в исходных единицах wheel speed; режим — vehicle-only label, не истинная фаза по GNSS. Полный breakdown всех front/rear, обоих знаков и common faults воспроизводит соседний `audit.py`; raw per-case данные уже в checkpoint. Для common-mode gradual сдвиг event RMSE порядка тысячных/сотых процента, отдельной устойчивой защиты от общей ошибки не получено. Улучшение выбранного физически ожидаемого знака ценой противоположного видно непосредственно в paired metrics; не выдаём post-hoc объяснение динамики внутреннего состояния за доказанную причинность.

**Ограничение порядка проверки:** автоматический development eligibility проверял численные regression guards, clean-phase/mismatch и дополнительные false stops/recovery/causality, но не реализовал отдельное veto за качественное условие «улучшение одного знака faults ценой другого». Поэтому validation был выполнен, несмотря на уже присутствовавший в development межзнаковый trade-off. Это недостаток этого driver, не основание считать все качественные предусловия выполненными. Данный отчёт не меняет задним числом PLAN/evaluator/замороженный выбор. Итог остаётся REJECTED и по общему численному контракту, и по этому диагностическому риску.

## Реально выполненные тесты, аудит, стоимость

В измерительном Actions run: **144/144** full unit, **43/43** research-integrity, **27/27** H20 unit; compileall PASS. Дополнительно повторены subset core 26/26, Timeline 10/10, guarded 34/34 — это подмножества, не ещё 70 уникальных тестов. Исторические hash/release guards не удалялись и не ослаблялись. Disabled candidate проверен потактово против pristine v7: все возвращаемые поля Estimate и всё исходное внутреннее состояние, **359956 development + 516894 validation = 876850 ticks**, на clean+original-fault replays. Sanity включает prefix causality, duplicates, stale/future/nonfinite, reset, bounded state, zero-lock, fallback и correlation floor.

Локально скачан artifact, его SHA256 совпал. Проверены **26/26** freeze source hashes; development и validation source manifests идентичны. Повторный расчёт summaries и decision reasons неизменным измеренным driver дал точное равенство сохранённым JSON (24 development +16 validation числовых summary fields). Подготовленный полный research patch применён к точному baseline: `git apply --check` PASS, после применения **19/19 файлов совпадают**; затем локально снова 144/144 +43/43 +27/27 tests и compileall PASS. Локальные тесты — CPython 3.13.5; реальные replay — CPython 3.13.15, NumPy 2.3.5, SciPy 1.17.0. Повторного локального real-bag replay не было: доступ к данным и реальное исполнение обеспечены Actions, прямой git clone в локальной среде не работал из-за DNS.

Benchmark на первом development bag `30618_0652866c`: warmup, 6 AB/BA пар для каждого alpha, все thread env=1, одинаковый сбор outputs. Для alpha=0.25 медиана paired overhead: **step CPU +13.0969%, replay CPU +8.5784%, replay wall +8.5710%**. Медианы абсолютных step cost: 26.7263 -> 30.2663 мкс/step; replay CPU 1.202944 -> 1.308147 с на 29287 step calls /29207 outputs. Alpha=0.50: step +13.1599%, replay CPU +8.8130%. Все повторения каждого implementation дали один output hash. Последняя runtime-диагностика включена в стоимость.

Это Python/offline cost, не installed ROS latency/RSS. **Свежий установленный включённый H20 под 2 CPU /500000000 bytes в обоих clock modes НЕ измерялся**, поскольку accuracy-gate уже отклонён. Стандартный CI успешен для неизменённого canonical runtime; его feature-off ROS результат не сертифицирует enabled H20. Не заявляются runtime-ready/merge-ready.

## Источники и математика

До измерений прочитаны core/readout/Timeline/evaluator/roles, v6, H02 #15, H05 #17, успешные #14/#23, соседний #26/H11; механизмы соседей не включались. [SOURCES.md](https://github.com/jabrailkhalil/hack/blob/130c96421931e307a9aedc207f4c835d54e4ac9c/research/R2/H20/SOURCES.md) фиксирует уровни чтения и конкретные ограничения доступа.

Bai et al. (2024), *An NMPC-Based Integrated Longitudinal and Lateral Vehicle Stability Control Based on the Double-Layer Torque Distribution*, Sensors 24(13),4137, DOI 10.3390/s24134137: использованы доступные metadata/HTML-фрагменты slip-модели (4.3/32), не полный PDF и не готовый estimator для двух тележек. Через Consensus выполнен узкий поиск и прочитан abstract/metadata Tanelli, Savaresi, Cantoni (2006), *Longitudinal vehicle speed estimation for traction and braking control systems*: четыре колеса и acceleration sensor не соответствуют нашему интерфейсу, поэтому метод не перенесён. Scite реально вызван, но вернул monthly MCP limit; карточки/full text/citation context через него **не получены**, независимая верификация цитирования не заявлена. Дальнейшая попытка полного HTML MDPI/PMC не дала доступного полного текста.

Wolfram фактически проверил bounds веса, alpha->0, непрерывность и нулевую правую производную в e=0, положительность производной weighted residual при alpha<=0.5, dimensional scaling, Joseph identity и common-mode rank/nullspace. Матрица двух колёс для трёх неизвестных [v,b_front,b_rear] имеет rank2, null direction [-1,1,1]: общую ошибку колёс сами два канала не идентифицируют. При оригинальном Huber-подобном R предельная положительная scalar correction p*c/[R*(1+alpha)] ограничена. Это не доказательство глобальной устойчивости всего нелинейного observer.

Для локального single-measurement примера P=.01, R=.04, b=c=.3 м/с и симметричного Gaussian noise sigma=.1 м/с Wolfram дал traction correction bias: alpha0=0, alpha.25=-0.000242751340150085 м/с, alpha.5=-0.000463830989724808 м/с; для braking знак зеркален. Первый NIntegrate выдал warning на изломе; исправленная парная интеграция повторена без warning, оба фактических исхода сохранены в `wolfram-output.json`, исполнимые формулы — `wolfram.wl`. Аналитика/синтетика не заменяют реальную accuracy.

## Команды воспроизведения

Полное исполнение находится в измеренном `research/R2/H20/execute.sh`; фактический журнал — `logs/execute.log`. Основные команды из полного checkout измеренного SHA:

```bash
git checkout 130c96421931e307a9aedc207f4c835d54e4ac9c
python -m pip install -r requirements-research.txt
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
export H20_SOURCE_SHA=130c96421931e307a9aedc207f4c835d54e4ac9c
PYTHONPATH=src/reserve_odometry python -m unittest discover -s tests -v
python -m unittest discover -s research/tests -v
python -m unittest discover -s research/R2/H20/tests -v
python research/R2/H20/stage_data.py --stage development --journal /tmp/H20-development-staging.json
python research/R2/H20/run.py --stage development --output /tmp/H20-fresh --workers 2
```

В исходном эксперименте после этого отдельным commit/push опубликован FREEZE и записан FREEZE_PUBLICATION.json, затем выполнены:

```bash
python research/R2/H20/stage_data.py --stage validation --journal /tmp/H20-validation-staging.json
python research/R2/H20/run.py --stage validation --output /tmp/H20-fresh --workers 2
```

Вторая стадия требует настоящего опубликованного freeze и совпадения source/development hashes, не формального самодельного флага. Для проверки уже опубликованного результата без обращения к данным используйте соседний `audit.py` с измеренным checkout и распакованным evidence. Повтор frozen run — воспроизведение, не разрешение на донастройку по validation. Source tar сохраняет нужные src/tools/research, но не все исторические отчёты, поэтому полный full-suite replay тестов требует полного Git checkout; сокращённый архив не подменяет его.

[Development CSV](https://github.com/jabrailkhalil/hack/blob/f45d87f2ea3c6a8816d0c6a0add2ba424e3261ad/reports/research_R2/H20/36185299933-1/experiment/development/per_bag.csv) и [Validation CSV](https://github.com/jabrailkhalil/hack/blob/f45d87f2ea3c6a8816d0c6a0add2ba424e3261ad/reports/research_R2/H20/36185299933-1/experiment/validation/per_bag.csv) содержат все bags/receivers/faults, RMSE/MAE/bias/recovery/coverage/distance. ZIP evidence 23049074 bytes; development raw JSON из-за полного trace и дублирования per-bag aggregate вырос до 68.39 MiB и получил GitHub large-file warning. Он уже опубликован и не переписывается; это недостаток размера evidence, а не raw bag upload. Для чтения предпочтительны CSV/per-bag JSON или сжатый artifact.

## Границы вывода

Final/test measurement payload не использован. Повторный исторический validation не независимый final test. Есть missing reference; pseudo phase/controller/model agreement не ground truth. Scalar-span distance — интегральный speed surrogate, не независимая XY-траектория. Общая ошибка двух колёс не наблюдаема из них самих. Installed enabled ROS latency/RSS не проверены. Scite/full-text обзор ограничен доступом. Автоматический gate не блокировал межзнаковый trade-off до validation, как описано выше. Параметры после freeze/validation не изменены.

**Итог:** минимальная причинная реализация H20 и воспроизводимые проверки выполнены; активности и численной безопасности недостаточно для выигрыша. Выбранный кандидат REJECTED, полезность механизма как универсального улучшения не подтверждена, merge readiness=false.
