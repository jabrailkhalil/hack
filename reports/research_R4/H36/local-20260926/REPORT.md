# R4-H36 — REJECTED: силы с отдельной нагрузкой train-окна

**Исследовательский отрицательный результат, не готов к merge.** Единственный selectable кандидат улучшил original fault-event group-macro RMSE development на **18,624356%**, но ухудшил основную дистанционную метрику на **1,872475%** при допуске 1%. Ранее check-группы train уже дали **+15,659557%** profiled loss при допуске +0,5%. Оба veto сохранены. Validation и final test не открывались; validation FREEZE не создавался.

Это результат конкретной зарегистрированной условной калибровки, не опровержение всего семейства nuisance-load identification. Нагрузка не объявляется измеренным уклоном, массой или истинным disturbance. Весь runtime остаётся прежним canonical v8; меняются только три глобальных физических коэффициента отдельного YAML. Подробный локальный отчёт, raw JSON/CSV, NPZ, логи и bundle приложены к ответу; ниже опубликованы метод, ключевые результаты и воспроизведение.

## 1. Исходники, роли и версии

Baseline **e3b0c9c039d2953fbfcda51231263d38ef9f1024**, tree **eae49a504bc59b5c9b408445150bef32e111956f**. Пользовательский ZIP полностью проверен встроенным stdlib verifier: **301 исходный файл**, все bytes, пути и executable bits; 352 файла __MACOSX исключены. ZIP SHA256 **a8e0bfa033e0a02c460c30b02f34a5c64ece85b05003512941387d3cf1f319a2**, 3831196 байт. Это полный tree match, не совпадение нескольких ключевых файлов. В ZIP нет .git или .db3. Полный SOURCE_RECEIPT находится в пакете.

Реальный класс `reserve_odometry.guarded_readout.GuardedReadoutObserver`, профиль `src/reserve_odometry/config/champion_v8.yaml`; опубликованные Estimate.v/s, 20 Гц, delay0, readout gain1/holdoff.5, adaptation.5, time_compensation0, quarantine1.5. Config defaults не использованы вместо профиля. Actual module path/class/config/readout записаны в started.json. Все 301 исходный файл проверены повторно перед стадиями и после результата.

| Назначение | SHA |
|---|---|
| PLAN, опубликован до measurement IO | a7e3436adbb7cfc614d8ea367205103cac8c786c |
| Уточнение до IO: low-speed predicate и clipping | 64d421436bd5645193ca925308f1ca397408142a |
| Самостоятельный локальный snapshot исходного tree | 44f205c54d43f50fe7f821faaf632989e67f4e40 |
| Локальный исполненный foundation source | 657ad3f1c011213f31f075c8209095ffec4a19ca |
| Локальный исполненный fit source | 8a10093a59c9b1d2ffdbe2105521ace4855a873a |
| Локальный исполненный development source | 62b26b5541872d16754cc4bfd707f95c294579ca |
| Поздняя публикация тех же алгоритмических bytes и YAML | 4bd4908821e55e08195f08bd88eb7cfab17dc3c7 |

**Локальные commits не выданы за remote baseline ancestry.** Их история сохраняется в приложенном git bundle. GitHub-ветка создана отдельно от настоящего remote baseline. PLAN опубликован до измерений; код сначала исполнялся из локальных git-снимков, затем опубликован. Это не задним числом заявленная публикация измеренного source.

Foundation started **26.09.2026 08:49:49 UTC**, fit **08:51:08 UTC**, development **08:56:59 UTC**. После результатов не было повторного fitting, новых стартов или подбора соседних параметров. Прочитаны H16 PR34/report, H22 PR40 и поздний checkpoint `R3-H22-result-36220679399-1/SUMMARY.json`, H24 PR45. Ранний IN_PROGRESS H22 не принят за его окончательный результат: поздний checkpoint уже REJECTED. H36 не повторяет integrated-error penalty, monotone map или outage-only применение другой физики.

## 2. Механизм и фиксированный бюджет

Только F=eta*gear*torque/(radius*mass), P=power/mass, B=brake_force/mass. При фиксированных mass/radius/gear/eta F однозначно соответствует torque/mass. Bounds F [.05,5], P [1,100], B [.05,5]. Rolling, drag, actuator tau, command exponent, wheel scale, R/gates, disturbance adaptation, zero-lock, quarantine, readout и Timeline остаются прежними. Default не переключён.

На каждом окне — 5 с causal actuator warmup и 5 с оцениваемого пути, десять неперекрывающихся .5-секундных velocity increments. В offline loss физика получает наблюдаемый causal held-wheel speed path: **это явно teacher-forced conditional identification, не recursive open-loop fit H16**. Drive начинает прогрев с нуля за 5 с до anchor, видит только прошлые u/v. На development применяется настоящий closed-loop v8, включая model-only интервалы.

```text
e_wj(theta) = physical_increment_wj(theta) - wheel_increment_wj
r_wj = (e_wj + 0.5*b_w) / (sqrt(2)*wheel_sigma)
L_w = mean_j 2*(sqrt(1+r_wj^2)-1)
b_w in [-0.6,+0.6] m/s^2
```

b профилируется через монотонный root sum(r/sqrt(1+r*r))=0 с bounds, 60 bisection iterations. Нет prior/regularization для искусственного восстановления rank. Равные веса групп, затем представленных initial phases, окон и bins. **b не экспортируется в runtime**, не хранится по bag ID и не определяется по validation.

Старый drive-before-Euler шаг .05 с сохранён. Физическое ускорение при b=0 ограничивается прежними ±3 м/с², b*duration добавляется после этого в условный loss. Invariance справедлива для аддитивной модели с interior b и без physical saturation, не для произвольной clipped рекурсии. Endpoints сырые held wheel means, без нового smoothing/age projection. Корреляция соседних increment errors остаётся ограничением; GLS не вводился.

Все 64 train bags открыты штатным Store только по vehicle topics. Группы сортируются SHA256('R4-H36:'+group): 20 fitting /7 check, membership сохранён до DB IO. Anchors 10,15,20,... с; 10-секундный warmup+window требует fresh inputs, abs(front-rear)<=.15 м/с, pair skew<=.1 с, mean speed .5..35 м/с. На .5-секундных endpoints должны продвинуться обе wheel stamps. До четырёх окон каждого initial phase на bag: сначала максимальный command range, затем ранний anchor; никакой selection по GNSS/ошибке кандидата.

**700 окон:** 532 fitting в17 из20 групп, 168 check в7 группах. 698 окон с command range>=.1. Все initial phases представлены в минимум16 fitting-группах и7 check-группах. Отсутствующие окна сохранены в inventory.

Перед fit из Jacobian каждого окна удалена constant-load компонента, без использования bounds b для создания rank. Производные нормированы на baseline theta и sigma, finite difference1e-4*theta0. Заранее требовались rank3, condition<=10000, min RMS singular>=.001, поддержка каждого параметра минимум в3 группах и phase/window coverage.

| Foundation | Fitting | Check |
|---|---:|---:|
| Projected rank |3|3|
| Condition |1.698973|1.753517|
| Min RMS singular |.422398|.404603|
| Группы поддержки F/P/B |16/16/17|7/7/7|

Post-fit rank также прошёл. Это локальная идентифицируемость условной модели на данном возбуждении, не доказательство no-slip.

Ровно **один profiled fit и один b=0 control**, control не selectable. Один старт theta0, TRF/2-point, max_nfev80, tolerances1e-8. Profiled nfev14/njev14/**56 actual calls**, control11/11/**44 calls**. Оба ftol-success, без попадания глобальных коэффициентов на bounds. Calls включают numerical Jacobian; последующие описательные вычисления метрик не являются дополнительным fitting.

| Один и тот же profiled objective | Baseline | Candidate |
|---|---:|---:|
| Fitting |.321105125024|.269936900210|
| Check |.177588139339|.205397654970|

Fitting **−15.935038%**, check **+15.659557%**: check gate .5% FAIL. Raw check increment RMSE .105146→.124285 м/с, signed increment bias .000801→.054620 м/с. Candidate profiled cost нельзя сравнивать с control unprofiled cost как одну метрику. Все raw/profiled costs и group/phase breakdown обеих реализаций сохранены в train/results.json.

| Глобальный коэффициент | Baseline | Profiled | b=0 control |
|---|---:|---:|---:|
| F, м/с² |1.188434318103|1.443138477619|1.111741274878|
| P, м²/с³ |7.021838337152|8.539592014957|7.084173603328|
| B, м/с² |1.139220235088|.779723369905|.788792885701|

F +21.431909%, P +21.614762%, B −31.556397%. На fitting 14 profiled b достигли bounds, на check1. Это не измерения настоящей нагрузки. Check FAIL уже запрещает validation, но PLAN разрешает диагностический development фиксированного кандидата без снятия veto.

## 3. Development: реально выполненное парное сравнение

**17 bags/7 групп**, clean reference в6 группах/19 bag-receiver парах, **394221** matched points. Семь bags без clean reference — null/N/A. **56 original fault scenarios/60 comparisons** с reference; дополнительно26 low-speed/34 comparisons и28 common-mode/30 comparisons. Два receiver одной поездки не считаются независимыми поездками.

Подставлена только фабрика полного v8 и глобальная Config. Не менялись guarded.compare/predict/fault_windows, evaluate.replay/distance_surrogate, experiment.match/metrics, v6.summary, h11.common_fault_windows/compare_common. Low-speed — точный PR13/H24 predicate, включая u>=0; словесный пропуск в PLAN исправлен опубликованным ДО IO уточнением. Original anchors/warmup/crops, timestamps/masks/reference/aggregation одинаковы.

На каждом из17 clean bags отдельно созданный baseline и feature-off совпали по published arrays/counters. Заново измеренные baseline fingerprints всех5 полей имеют **delta0**, не скопированы из старого отчёта. Для всех56 original инъекций дополнительно измерены полные faulted bags без crop для трёх конфигураций.

| Development metric | v8 | Profiled | Δ | b=0 control | Δ |
|---|---:|---:|---:|---:|---:|
| Clean macro RMSE, м/с |.092668143|.092489881|−.192366%|.092519509|−.160394%|
| Original fault-event macro RMSE, м/с |.237548612|.193306713|**−18.624356%**|.241870226|+1.819255%|
| Pooled clean RMSE, м/с |.129305694|.128871898|−.335481%|.129024029|−.217829%|
| Scalar-span distance macro RMSE, м |5.310295005|5.409728932|**+1.872475%**|5.335704346|+.478492%|
| False stops clean/original |0/0|0/0|без роста|0/0|без роста|
| Original unrecovered |4|4|те же случаи|4|те же случаи|

Допустимая distance при1%: **5.363397955 м**; candidate5.409728932, абсолютная регрессия **.099433927 м**. Причины отказа: **aggregate_regression:distance_rmse**, **check_profiled_objective_regression**. Пороги не смягчались. У nonselectable control также original fault/low-speed/gain FAIL.

Нет loss coverage/schedule, новых individual unrecovered/false stops, causal/reset нарушений или clean per-bag превышения baseline+max(.005,5%). Candidate **ACTIVE:219424** изменённых published v ticks/7 групп; control219156. Это счётчики, не независимые испытания.

Low-speed event macro .368545673→.312414379 (**−15.230485%**), common-mode .100632272→.084769887 (**−15.762722%**). Low-speed unrecovered6→2: четыре receiver/scenario-сравнения восстанавливаются на одном bag30639_0ab96c59. Common unrecovered2→2, REACQUIRING ticks16→7, false stops0. Это не абсолютная защита от общего slip; дополнительные gains не заменяют distance gate.

## 4. Существенные регрессии и интегральный риск

Clean RMSE хуже в**6/19**, original fault RMSE в**33/60** сравнений. Две из пяти original fault-reference групп хуже при хорошем агрегате. Low-speed хуже8/34, common-mode16/30. Полные metrics, MAE/p95/signed bias/recovery/group slices приложены.

Худший original dropout10s: **30639_9c362687/rover .258670139→.715098345 м/с**, master .257095610→.711998712. 30639_dce52be4/master .227959065→.532606671. Low-speed30618_073f08d1/master lock5s .182886696→.330669554.

Clean distance хуже7/19. 30639_c31df386/rover **28.322408035→28.917946524 м**, +.595538489. Clean signed macro bias .006390677→.007506952 м/с; original fault+10s recovery-window bias **.011170308→.062473270 м/с**, несмотря на MAE .153796529→.128779209.

Original recovery на одинаковых56 случаях: mean .822233743→.754376600с, **семь медленнее**, максимум+.5с на30618_0652866c/dropout10s у обоих receiver:1.256544646→1.756544646. Low-speed missing меняется6→2: на одинаковых28 ранее восстановленных случаях mean .344549354→.342763639с. Четыре новых подтверждённых recovery имеют3.85/5.85с; новый общий mean .906с нельзя объявлять замедлением прежних случаев.

Full-faulted-bag distance — отдельная описательная проверка, не подмена original admission:

| Инъекция | Baseline scalar span macro, м | Candidate, м |
|---|---:|---:|
| Bias5s |6.368333907|6.502380213|
| Dropout5s |6.146293122|6.390320323|
| Dropout10s |6.332766496|**7.180289421**|
| Lock3s |6.230114265|6.384497095|

При dropout10s полный distance aggregate **+13.383139%**. На30618_073f08d1 candidate−baseline s через10с после outage **20.883858м**, к концу bag **21.594596м**. Это **дельта алгоритмов, не ошибка относительно истинной координаты**; она включает всю различающуюся историю, не является изолированной causal ablation коэффициента. s после recovery не стиралась и не переякоривалась к reference. Хороший cropped event RMSE не защищает полный интеграл.

## 5. Проверки, математика, стоимость и CI

Локально Python3.13.5/NumPy2.3.5/SciPy1.17.0, OPENBLAS/OMP1. **156 historical runtime +43 integrity +22 различных H36 tests PASS**. H36:14 foundation/profiling и8 дополнительных, включая обе фактически включённые калибровки. Повторные прогоны одних tests не посчитаны новыми tests. Compile PASS.

Проверены soft-L1/KKT/bounds, quadratic projection, invariance к constant offset в допустимой модели, changing-load failure, no-excitation rank failure, causal warmup, exact off state/Estimate, prefix/future/duplicates/reset, finite/bounded state, zero-lock/quarantine/true stop, role-before-IO, schedule и missing reference. Runtime-полей не добавлено: тот же класс v8.

Wolfram действительно исполнил worksheet: b*=−h'e/(h'h), I−hh'/(h'h), null load column, b*→b*+c при constant shift и soft-L1 second derivative **2*h²*sigma/((e+b*h)²+sigma²)^(3/2)**. Константный регрессор после проекции исчезает. Worksheet/output сохранены в research/R4/H36/math. Предварительный semantic context не дал полезных результатов и не использован. Публикация для элементарного profiling не выдумана; известные quota stops Consensus/Scite не обходились. Аналитика не доказывает no-slip или устойчивость всей nonlinear switched системы.

Foundation wall8.723с; полный local development с full-faulted replay и off/direct проверками60.695с. После результата выполнено ABBA×3 (**12replays**): один real development bag,10с warmup/60с измеряемого source-time, одинаковые collectors/threads/clocks. Median CPU step p95 **15.955→15.434мкс**, post-warmup replay CPU **.024651→.023785с**. Это описательный offline timing прежнего кода, **не ROS latency или доказательство гарантированного ускорения**. RSS в JSON — whole offline Python со scientific libraries/data, не node RSS. Скрипт cost.py и raw timing входят в пакет.

Попытка remote fixed-development reproduction **без нового fitting**: source **c9103bdc9e20ff95f88576c2d6baca47f7aeb6e7**, [run36231946468](https://github.com/jabrailkhalil/hack/actions/runs/36231946468), job108376631558. API: **completed/failure, steps=null**, log **404 BlobNotFound**, artifacts **[]**. Доступный endpoint annotations отклонён400. Причина failure **не установлена**, billing/quota не выданы за проверенный факт. Удалённые tests/replay/artifacts не засчитаны; retry не выполнялся. Обычный CI source36231946402 также failure, зелёный CI не заявляется.

Локальное исследование завершено, но cross-environment reproduction отсутствует. **Fresh installed enabled ROS в обоих clock modes, 2CPU/500000000bytes, end-to-end latency/node RSS — NOT_RUN_AFTER_REJECTION.** Validation/final test не запускались по протоколу; не подменяются remote CI или синтетикой.

## 6. Данные и сохранённые исходные результаты

Локальные DB взяты из ранее авторизованного Actions artifact10885260111/run36182706411, H16-pinned-permitted-inputs.zip. SHA256 **b119efdbd3e37dd7adeeef131e6d4ff8db34c61b5ad82a3b9d66303a5caeac19** проверен заново. Использованы DB bytes, не R2 source. Все64 train/17 development DB совпали с R4 split hashes. Validation/test DB в этой копии отсутствуют. Train SQL — толькоvehicle; development GNSS — исключительно scorer. Исходный dataset archive fingerprint записан в provenance; нового успешного скачивания организаторского ZIP этой сессией не заявляется.

Пакет ответа сохраняет raw foundation/train/development JSON, per-bag/per-receiver/per-fault CSV, groups/windows, compressed NPZ diagnostics/traces, access, логи, full SOURCE_RECEIPT, source/config manifest, patch и local git bundle. Raw DB/cache/secrets не публикуются. GitHub содержит читаемый source, профиль, PLAN, эту компактную версию отчёта и per-bag summary. **Remote Actions artifact H36 отсутствует; retention ему не придумывается.** Полный локальный отчёт содержит дополнительные операционные подробности.

```text
train/results.json       9c72066ededc0703ed1aec2bc018af66ecb5a25ff68fe7c28a1ad8e6198fe5f1
development/results.json b959371bc67d6557af23ba5a0a8b8663cae3310b2dcf93c3a5efd26f7154384a
profiled.yaml            2a5db48c2f3c23efe7faab40e74451a721ba706c1c5d2d8e8f451e3f059de205
```

[clean_per_bag.csv](clean_per_bag.csv) усредняет available receivers внутри bag только для чтения, не меняет primary group-macro. Пустые клетки — N/A. Полные receiver/fault rows в пакете.

## 7. Команды

Реально выполнено на предварительно проверенных локальных inputs:

```bash
PYTHONPATH=src/reserve_odometry python -m unittest discover -s tests -v
python -m unittest discover -s research/tests -v
python -m unittest discover -s research/R4/H36 -p 'test_*.py' -v
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
R=reports/research_R4/H36/local-20260926
python research/R4/H36/foundation.py --data-root dataset/data --output "$R/foundation"
python research/R4/H36/fit.py --foundation "$R/foundation" --output "$R/train"
python research/R4/H36/develop.py --data-root dataset/data \
  --train "$R/train/results.json" --output "$R/development" --workers 2
python research/R4/H36/cost.py --data-root dataset/data \
  --train "$R/train/results.json" --output "$R/cost"
```

H36_SOURCE_SHA задавался соответствующим local commit перед каждой стадией. Поздний posthoc только читает saved JSON; одна первоначальная shell-сортировка recovery с одинаковыми tuple delta упала на сравнении dict, затем исправлена в posthoc, без нового fit/replay или изменения raw metrics. Краткая неподдержанная interactive container invocation не исполнила команду; реальное вычисление выполнено обычным локальным процессом до завершения.

Повтор фиксированных чисел, **без fitting**:

```bash
git fetch origin research/R4-H36
git worktree add --detach ../hack-R4-H36 4bd4908821e55e08195f08bd88eb7cfab17dc3c7
cd ../hack-R4-H36
python3.13 -m venv .venv-research
. .venv-research/bin/activate
python -m pip install -r requirements-research.txt
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
python research/R4/H36/repeat.py receipt
OUT="$(mktemp -d /tmp/R4-H36-repeat-XXXXXX)"
python research/R4/H36/repeat.py fixture --path "$OUT/frozen"
python research/R4/H36/repeat.py prepare --path "$OUT/input"
python research/R4/H36/develop.py --data-root "$OUT/input/data" \
  --train "$OUT/frozen/models.json" --output "$OUT/development" --workers 2
python research/R4/H36/repeat.py verify --path "$OUT/development/results.json"
```

Требуется полный Git checkout с baseline ancestor. repeat.py не вызывает fit и не имеет validation CLI; извлекаются только17 development DB с hash checks. Generated fixture/YAML сопоставлены с исходным train JSON — exact equality. Git receipt подтверждает original tracked bytes, не повторную проверку пользовательского ZIP. Remote execution рецепта не подтверждено.

Явное включение после обычной ROS-сборки/source (**инструкция, не выполненный benchmark**):

```bash
ros2 launch reserve_odometry odometry.launch.py \
  params_file:="$PWD/research/R4/H36/variants/profiled.yaml"
```

Checkout/launch без этого YAML оставляет canonical v8. Patch не является рекомендацией к deployment. Wheel pseudotarget может содержать общий slip и timing errors; b может поглощать ошибку сил. Distance остаётся scalar reanchored surrogate, не xyz/ENU и не истинный terminal drift. Нет independent statistical guarantee. Main/чужие ветки этим исследованием не изменялись; merge/auto-merge не выполнялись.
