# R2 H18 — REJECTED: covariance при неизвестном disturbance

**Исследовательский артефакт, не готов к merge. Механизм ACTIVE; итоговый accuracy gate — REJECTED (`insufficient_gain`).**

Единственный preregistered вариант `fixed_consider` реализован и полностью измерен. На validation clean RMSE уменьшился на **0.000469108%**, original fault-event RMSE — на **0.001021415%**. Требуемые 2%/5% не достигнуты. Регрессионные и проверенные safety-пороги соблюдены. Это не опровержение всего семейства consider filters и не отсутствие активации.

## 1. Версии и история исполнения

| Назначение | SHA |
|---|---|
| Общий baseline R2, canonical v7 | `65bba39ed05c781f3f69a65c02f69931152cbfd9` |
| PLAN до экспериментов | `560222f56800d74b459604228a89ace2260335c3` |
| Измеренные алгоритм, driver и тесты | `2ddf918ec990085f070caed003e24b616ce27fe8` |
| Отдельный freeze, закоммичен и запушен до validation | `4791b9fa5d75f88c61d3cda39aa120fd32c5fba9` |
| Все исходные измерения и журналы | `3d95d5ef4258ed6d5bfa439d5a916dddcb5c4d0f` |

Ветка: `research/round2-H18`. Run: [36185008785](https://github.com/jabrailkhalil/hack/actions/runs/36185008785), attempt 1. [Исходные evidence по неизменному commit](https://github.com/jabrailkhalil/hack/tree/3d95d5ef4258ed6d5bfa439d5a916dddcb5c4d0f/reports/research_R2/H18/36185008785-1). Дата исполнения: 25 сентября 2026. Freeze создан в 20:23:44 UTC, после train/development и до validation. Исторические final-test значения не использованы. Ни main, ни чужие ветки, ни опубликованные отчёты не изменены; merge/auto-merge не выполнялись.

Реальный baseline — `GuardedReadoutObserver(Config(**guarded_readout_v7.config), readout={gain:1, holdoff_s:0.5})`, 20 Hz, delay 0, `wheel_time_compensation=0`, `adaptation_tau_s=0.5`. Старое поле `base_commit` внутри profile JSON — исторические метаданные профиля, не SHA сравниваемого R2 baseline. Driver проверяет реальные исходники/параметры/launch, а не это поле и не имя `main` старого runner. H11/v8 не включён.

## 2. Изменение и математический смысл

Новый отдельный модуль `outage_uncertainty.py` наследует канонический guarded observer. Core, readout, Timeline, ROS adapter, канонический launch и физические параметры остаются побайтно прежними. Среднее d, его tau/target, численное интегрирование, raw rate/zero-lock guard, hard innovation cap и bounded reacquisition не переписаны.

После `max_age_s=0.25` без нового принятого wheel measurement добавляется только covariance transport. Источник времени — stamp принятого sample, не wall time. Runtime не получает GNSS/IMU, reference, bag ID или oracle injection flag. Внешний scorer после шага отдельно считает ошибки и ложные принятия; диагностическая metadata не передаётся базовому шагу.

Для локальной линейной модели ошибок `ev'=ed+w_v`, `ed'=0`:

```text
F(T) = [[1, T], [0, 1]]
Pvv(T) = Pvv0 + 2*T*Pvd0 + T*T*Pdd0 + Qv*T
Pvd(T) = Pvd0 + T*Pdd0
Pdd(T) = Pdd0
```

Штатный core добавляет Qv ровно один раз. Дополнительная поправка `2*h*Pvd+h*h*Pdd` поступает в pv перед неизменным шагом, следовательно прежний scalar gain и covariance-dependent часть soft gate могут измениться; hard cap не расширяется. Mean prediction при полном отсутствии wheel corrections не меняется.

При неизвестной корреляции новый outage переякоряет `Pvd=+sqrt(Pvv*Pdd)` без уменьшения маргинальных дисперсий. Для фиксированных маргиналов и положительного горизонта это максимальная forward scalar variance среди допустимых корреляций. Это **не** доказательство Loewner-доминирования любой полной covariance и **не** калиброванная оценка истинной ошибки.

После scalar velocity update сохраняется Schmidt/consider-подобная структура: `Kd=0`, `Pvd+=(1-K)*Pvd-`, `Pdd+=Pdd-`; Pvv обновляет прежний Joseph step. При reacquisition нет фиктивного независимого measurement update. При recovery/STOPPED Pvv/Pdd не обнуляются; reset возвращает dormant lifecycle. Следующий outage заново учитывает неизвестную корреляцию после legacy d-адаптации. Новых неограниченных историй нет: только восемь дополнительных скаляров/флагов, O(1) памяти и работы на шаг.

Это episode-wise covariance approximation. Она не учитывает весь nonlinear Jacobian, неизвестность drive-history и точные корреляции legacy-адаптации вне outage. Часть ошибки может уже находиться в Qv: возможное double counting не устранялось дополнительным подбором Q.

Wolfram фактически подтвердил FPFᵀ, Joseph/determinant PSD identity, предел T=0 и скалярную верхнюю границу. Формулы random-walk добавок `Qd*T^3/3`, `Qd*T^2/2`, `Qd*T` выведены только для справки: **Qd=0**, второй вариант не добавлялся. Дополнительно проверены размерности и determinant локальной observability matrix T. Единичные eigenvalues дают полиномиальный рост, не асимптотическую устойчивость. Worksheet и фактический output сохранены; предупреждение Wolfram о символических именах во втором вызове не скрыто.

## 3. Один вариант и train-калибровка

Протокол разрешает ровно один `fixed_consider`; baseline/feature-off — контроли. Кандидат causal residual-based и произвольные Q×2/×4 не исследовались. На train открыты только controller/front/rear, без GNSS.

Из 64 train bags получены 441264 доверенных causal residuals. В 60 bags сформировано **70426** неперекрывающихся блоков длительностью не менее 0.5 s, по 25 исходным группам. 209 block means ограничены заранее заданным диапазоном ±1.2 m/s². Калибровка: equal-group mean квадратов block residual, затем заранее заданные bounds `[1e-6,0.36]`.

```text
Pdd_raw = Pdd = 0.026281054723820793 m²/s⁴
sqrt(Pdd) = 0.16211432609063517 m/s²
```

Это wheel-derived second moment, не независимая истинная дисперсия disturbance. Общий slip двух колёс может быть невиден. В одной из групп всего два блока; равный вес групп предзарегистрирован, но точность такой калибровки ограничена. Границы итогового Pdd не сработали. Ни одного альтернативного численного значения по development/validation не выбирали.

## 4. Development, freeze и неизменный измеритель

Все **17 development bags / 7 групп** обработаны настоящим read-only development loader; GNSS-метрики доступны в 6 группах и 19 bag/receiver парах. Не было переименования validation в development. 56 original fault случаев и 42 дополнительных diagnostic случаев. Четыре исходных unrecovered comparisons сохранены у обоих алгоритмов, новых нет.

| Development | Baseline | H18 | Изменение ошибки |
|---|---:|---:|---:|
| Clean RMSE, m/s | 0.092668142983 | 0.092667414566 | −0.000786049% |
| Original fault RMSE, m/s | 0.237548612056 | 0.237546344812 | −0.000954434% |
| Distance, m | 5.310295004801 | 5.310253207282 | −0.000787104% |

До validation достигнут preregistered coverage: 8070 active covariance ticks, 7674 изменённых принятых updates, 548 episode activations в 6 группах. Это счётчики активации, **не** количество независимых отказов/поездок. Safety/регрессионных отказов нет. Минимальный gain на development заранее не требовался для единственного кандидата; после прохождения guards создан отдельный freeze commit. Затем ровно один validation run; параметры после него не менялись.

`evaluate.score`, `evaluate.replay`, matching, маски, формулы distance и fault placement не изменены. Driver использует временные factory/pass-through capture, а не новые scoring formulas. Legacy aliases `baseline_v2` и `balanced_physics` означают два экземпляра **canonical v7**, не v2/v3; затем переименованы baseline/control. Их массивы и счётчики совпадают.

На каждом из 17 development и 19 validation bags direct canonical replay, baseline driver и H18 off совпали **побитно по выходным массивам** с одинаковыми runtime counters. Отдельные unit/supplement проверки сравнили Estimate, статусы и все базовые внутренние поля. В количественную оценку идут публикуемые Estimate.v/s, не внутренние v/s. Перед локальным повтором исходный patch применён к точному baseline; все **29** frozen source hashes совпали.

## 5. Validation: общий контракт не выполнен

Все **19 bags / 10 групп** обработаны. Reference есть в 9 группах / 30 clean bag/receiver парах. 76 original fault scenarios / 120 сравнений с reference, плюс 57 отдельных diagnostics. Четыре bags без reference (`30618_2255aade`, `30618_4e1e3181`, `30618_7bfbb5ed`, `30618_95c49c30`) сохранены как missing, не нулевые ошибки.

| Метрика | Canonical v7 | H18 | Изменение |
|---|---:|---:|---:|
| Clean group-macro RMSE, m/s | 0.114549861317 | 0.114549323955 | **−0.000469108%** |
| Original fault-event group-macro RMSE, m/s | 0.538286782601 | 0.538281284457 | **−0.001021415%** |
| Pooled clean RMSE, m/s | 0.216406794155 | 0.216406288144 | −0.000233824% |
| Scalar-span distance macro RMSE, m | 4.595480653018 | 4.595558379664 | **+0.001691371%** |
| Clean MAE, m/s | 0.047549651404 | 0.047549244878 | −0.000000406526 m/s |
| Clean signed bias, m/s | −0.015975155952 | −0.015975617708 | −0.000000461756 m/s |
| Fault+recovery MAE, m/s | 0.225316973762 | 0.225301490141 | −0.000015483621 m/s |
| Fault+recovery signed bias, m/s | −0.065924573423 | −0.065963338249 | −0.000038764826 m/s |
| Group-macro confirmed recovery, s | 0.226255203389 | 0.226255203389 | без изменения |
| Matched clean samples | 698891 | 698891 | без потери |
| False stop samples clean / fault | 18 / 0 | 18 / 0 | без роста |
| Unrecovered original comparisons | 0 | 0 | без роста |

MAE/bias в fault строках относятся к штатному окну fault + 10 s recovery; event-RMSE admission — только к самому fault-окну. Recovery совпадает **во всех 120 original comparisons**, а не только в среднем. Pooled mean recovery = 0.254840173467 s у обоих; он отличается от group-macro из-за весов.

Соблюдены ограничения clean/fault/pooled ≤0.5%, distance ≤1%, clean per-bag ≤baseline+max(0.005,5%), равенство coverage, отсутствие новых false stops/unrecovered/causal errors/resets. Но нет ни 2% clean gain, ни 5% original fault gain. Итоговый gate возвращает **только `insufficient_gain`**. Порог не снижен ради малого положительного числа.

В validation mechanism counters: 11107 active ticks, 9543 changed accepted updates, 679 episode activations по 10 группам. Это не неактивный механизм: ковариация/gain менялись, а необходимого изменения ошибки не возникло.

## 6. Существенные локальные эффекты и риски

Original-suite регрессии малы, но сохранены. Максимальная clean absolute RMSE-регрессия: `30618_defd0170/rover` 0.111658335289 → 0.111659292084 m/s, +0.000856895%. На этой же записи bias5s/master event RMSE 0.103110814941 → 0.103128316454 m/s, +0.016973499%. Дистанционный aggregate ухудшился на 0.000077726646 m.

Отдельный diagnostic **dropout5s → общая ложная прибавка +2m/s на1s** ухудшил group-macro event RMSE: **1.124793400886 → 1.129657356877 m/s (+0.432431057%)**. На `30618_2dbce472/rover`: **0.760654567933 → 0.771352413567 m/s (+1.406399973%)**. На `30639_3b3d9eb8/rover`: +1.171164864%. Этот диагностический результат не подменяет original-suite gate.

Количество принятых corrupted channel statuses в +2 diagnostic одинаково: 361 ACCEPTED и 0 REACQUIRE_ACCEPTED у обоих. То есть рост ошибки здесь не равен росту количества false acceptance: сильнее вес уже принимаемого ложного сигнала. Общий +5m/s на0.7s: 0→0 false statuses; на1.2s: 94→94 REACQUIRE_ACCEPTED statuses (канальные, не независимые измерения). H11/quarantine не переносился в H18.

Пример из сохранённых traces, `30618_2dbce472`, genuine dropout5s:

| Состояние/шаг | Baseline | H18 |
|---|---:|---:|
| В середине outage: опубликованная v, m/s | 3.631432454875 | 3.631432454875 |
| Там же Pvv | 0.261182190684 | 0.517662093456 |
| Первый исправный update: gain | 0.980812851669 | 0.992695603401 |
| Первый исправный update: v, m/s | 5.082197311336 | 5.083795513704 |
| Следующий исправный update: gain | 0.712710782621 | 0.713688189997 |

При ложной +2 скорости в тот же момент первый gain повышается с 0.877818996046 до 0.950251363949; v становится 6.823982870283 → 6.978589590481 m/s. Это наблюдение по frozen traces, не post-validation подбор. Полные traces, состояния до/во время/после отказа и variance-vs-error сохранены в `validation/traces.json.gz` и `validation/diagnostics.json`; компактный DIAGNOSTIC_EXAMPLE.json также включён в скачиваемый пакет отчёта.

Для genuine dropout в примере mean inner variance примерно удваивается, а ошибка к master почти та же. Отношения error²/inner variance различаются у master и rover; не выдаём это за калиброванный NEES или доверительный интервал. Более высокая covariance сама по себе не является выигрышем accuracy.

## 7. Проверки, стоимость и непроведённый ROS этап

Research workflow успешно выполнил train/freeze/validation — это **success исполнения отрицательного исследования**, не принятие кандидата. В нём прошли 144 штатных unit, 43 research-integrity и 16 H18/driver tests, compile. Локально дополнительно выполнено 12000 шагов отключённой эквивалентности с реальными каноническими параметрами, reset/alternating bootstrap/stamp проверки. Подлинные логи, исходный patch и hashes сохранены.

[Обычный CI исходного commit](https://github.com/jabrailkhalil/hack/actions/runs/36185008551): core, research-integrity, ros-humble, offline-limited — все success. Исторические release guards не удалялись. **ROS jobs проверяли канонический v7/штатные профили, а не включённый H18.**

Стоимость измерена на полном первом development bag `30618_0652866c`, после одного warmup каждого алгоритма, порядок AB, BA, AB, BA, OPENBLAS/OMP=1, одинаковый сбор outputs. Приведены медианы четырёх наблюдений каждого алгоритма; raw наблюдения не отбрасывались.

| Offline scope | Baseline CPU / wall, s | H18 CPU / wall, s | CPU delta |
|---|---:|---:|---:|
| Replay, 29207 published outputs | 1.471677 / 1.472016 | 1.641749 / 1.642119 | **+11.5563%** |
| Direct step, 29287 calls включая initialization | 0.989052 / 0.989151 | 1.145907 / 1.146047 | **+15.8592%** |

Direct step CPU: примерно 33.77 → 39.13 µs/call. Это средняя вычислительная стоимость, не end-to-end latency. RSS peak **218091520 bytes** относится ко всему offline research process со scorer/traces, **не** к изолированному ROS node или incremental H18 memory.

**Свежий установленный ВКЛЮЧЁННЫЙ H18 ROS benchmark, оба clock modes и real-bag latency/RSS не выполнялись:** accuracy gate уже отклонён, как допускает PLAN. Поэтому resource/latency contract кандидата не сертифицирован. Historical v4 benchmark и feature-off CI не используются как замена.

## 8. Источники, ограничения, воспроизведение

Через Consensus выполнен узкий поиск и fetch Zanetti/Bishop (2012), *Kalman Filters with Uncompensated Biases*: прочитаны metadata и вводный фрагмент карточки, не полный текст. Это мотивация consider uncertainty без обновления nuisance mean, не доказательство нашего выигрыша. Scite реально отказал из-за месячной MCP-квоты; citation contexts/full text через него не проверены. SOURCES.md фиксирует границы; покупки не производились.

Validation повторно использовался ранее: это **не независимый final test**. Access journals: 64 train +17 development +19 validation unique bags, без train GNSS и без final/test measurement queries. Оба reference receivers сохранены; они не считаются двумя независимыми поездками. Bootstrap по ticks не выполнялся, statistical significance не заявляется. Distance — scalar-span surrogate, не xyz/ENU и не полный terminal drift. Отрицательный итог относится к единственному описанному правилу Pdd/correlation lifecycle.

Для воспроизведения выбранного freeze (нужен доступ к private repo):

```bash
git fetch origin checkpoint/R2-H18-36185008785-1
git worktree add --detach /tmp/h18-repro 4791b9fa5d75f88c61d3cda39aa120fd32c5fba9
cd /tmp/h18-repro
python3.13 -m venv .venv-research
. .venv-research/bin/activate
python -m pip install -r requirements-research.txt
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
python tools/get_dataset.py
PYTHONPATH=src/reserve_odometry python -m unittest discover -s research/R2/H18 -p 'test_*.py' -v

# При повторе использовать новые каталоги; overwrite запрещён.
python research/R2/H18/run.py train --output /tmp/h18-repeat-train
python research/R2/H18/run.py development \
  --training reports/research_R2/H18/36185008785-1/train/calibration.json \
  --output /tmp/h18-repeat-development
python research/R2/H18/run.py validation \
  --freeze reports/research_R2/H18/36185008785-1/FREEZE.json \
  --output /tmp/h18-repeat-validation
```

В повторном validation используется именно закоммиченный original freeze/calibration; новый train — отдельная проверка воспроизводимости, не подбор. Python3.13.5, NumPy2.3.5, SciPy1.17.0. Полные фактически исполненные команды зафиксированы workflow и logs.

**Checkout сам по себе НЕ включает H18 в ROS.** Driver явно создаёт `OutageUncertaintyObserver(Config(**profile['config']), readout=ReadoutConfig(**profile['readout']), pdd=0.026281054723820793, enabled=True)`. Параметры также в candidate.json. Самостоятельный algorithm.patch в скачиваемом пакете добавляет модуль, а algorithm-and-runner.patch в репозитории содержит source/test/PLAN для измерений; прочие файлы baseline остаются прежними.

Raw JSON/CSV, access, train blocks, per-bag checkpoints, freeze, commands/logs и оба набора traces — в этом run directory, также закреплены в [неизменном evidence commit](https://github.com/jabrailkhalil/hack/tree/3d95d5ef4258ed6d5bfa439d5a916dddcb5c4d0f/reports/research_R2/H18/36185008785-1). `per_bag_summary.csv` — компактная сводка всех 19 bags; receiver/fault детали не потеряны в `validation/per_bag.csv`. Поздний REPORT/SUMMARY commit не выдаётся за измеренный source SHA.

**Решение: не merge; оставить канонический R2 baseline для этого раунда.** Пересравнение с будущим main/комбинации с H11 — не часть этого исследования.
