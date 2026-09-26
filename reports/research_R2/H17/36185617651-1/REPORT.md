# H17 / R2-v7-fixed — чистое запаздывание команды: REJECTED

**Исследовательский отрицательный результат, не готов к merge.** Замороженный `H17_L050` (L=0.05 с) проверен на всех validation-записях. Clean group-macro RMSE уменьшился лишь на **0.000758842%**, original fault-event RMSE **увеличился на 0.647597619%** при допустимых 0.5%. Два основания отказа: `insufficient_gain` и `aggregate_regression:fault_rmse`. Это отрицательный вывод о проверенном кандидате, не обо всех способах моделирования задержки.

Механизм: **ACTIVE / достаточное покрытие / sanity PASS**. Численная приёмка: **REJECTED**. Единая физическая задержка: **не идентифицирована**. Готовность к merge: **нет**. Ветка `research/round2-H17`; [draft PR #30](https://github.com/jabrailkhalil/hack/pull/30). Main, чужие ветки и опубликованные отчёты не изменены; merge/auto-merge/force-push не выполнялись.

## 1. Точные версии и порядок

| Назначение | SHA |
|---|---|
| Общий baseline R2 | `65bba39ed05c781f3f69a65c02f69931152cbfd9` |
| PLAN до экспериментов | `b8a334980df4ce3494abfeccfdf98db17b1309db` |
| Реализация / измеренный development | `272f81bb2593618c899f5b9b889e564a917daf44` |
| Отдельный freeze / **измеренный validation** | **`ed62dc651937b9bcc49ad2a445c20630883aac1f`** |
| Commit запуска validation workflow, не измеряемый checkout | `5676f9e44bda8e75146cfa0ba13f365354af6443` |
| Development/cost checkpoint | `eaf71d94943cf8d37efc497b531b8edb7315f858` |
| Validation checkpoint | `36b749fe71a033e0ea0b4cf24d1a8e9ab1b90cbf` |

[PLAN](https://github.com/jabrailkhalil/hack/blob/b8a334980df4ce3494abfeccfdf98db17b1309db/research/R2/H17/PLAN.md) опубликован до экспериментов. [FREEZE](https://github.com/jabrailkhalil/hack/blob/ed62dc651937b9bcc49ad2a445c20630883aac1f/research/R2/H17/FREEZE.json) создан после development и до validation; закрепляет L=0.05, полный профиль, код, evaluator, split и development evidence. Все **23 source hashes** development/freeze/validation совпали точно; runtime patch в обоих прогонах побайтно одинаков. После validation алгоритм и параметры не менялись.

Workflow имеет head `5676f9e...`, но checkout явно исполнил `ed62dc651937b9bcc49ad2a445c20630883aac1f`. Это подтверждают `MEASURED_SOURCE_SHA.txt`, `started.json` и YAML workflow. Поздний commit этого отчёта не является новой измеренной реализацией.

На момент открытия PR main уже включал H11/v8 (`e3b0c9c039d2953fbfcda51231263d38ef9f1024`). Он не включён в эксперимент. Старые H01–H10/v6 числа не являются сравнением с R2. Изучены core/guarded readout/Timeline, evaluator, тесты и роли данных, отрицательные v6, H07/#22 и ранее H05/#17, успешные #14/#23, соседний #26/H11. Результаты других R2-агентов для настройки не использовались.

## 2. Минимальный runtime-патч

Добавлен `src/reserve_odometry/reserve_odometry/command_deadtime.py`, класс `CommandDeadtimeObserver(GuardedReadoutObserver)`. Изменён только аргумент `drive_target`: последняя уже полученная команда со stamp ≤ t−L вместо текущей. Ровно три ненулевых варианта: **0.05, 0.10, 0.20 с**. `actuator_tau_s=0.3927619145850434` и все физические коэффициенты фиксированы. В отличие от H07, нет разных tau для тяги/торможения; в отличие от wheel-time гипотез, нет сдвига колёсных измерений.

История ≤0.25 с плюс один predecessor, ≤64 samples. Она видит только команды, реально переданные неизменной Timeline в step, не её скрытую очередь. Промежуточные пакеты не реконструируются. Duplicate/old/future/nonfinite/range/stale команды не дописываются. Если нет допустимого predecessor для t−L — заранее выбранный neutral fallback. Исторический sample не может быть старше `command_timeout_s=0.5` относительно t.

**Исходная текущая команда и её настоящий stamp** продолжают определять `command_stale`, stop/sign/readout guards. Невалидная текущая команда немедленно даёт neutral target; история не скрывает потерю связи и не продлевает timeout. Не меняются core, zero-lock/reacquisition, disturbance adaptation, readout, Timeline, node/launch, единицы и matching. Нет GNSS/IMU, bag/file ID, future samples или fault-oracle в алгоритме. Runtime — только стандартная библиотека; научные зависимости offline.

Off напрямую делегирует canonical v7. Отдельный проверочный объект сравнивает каждый возвращённый Estimate и **все поля canonical состояния**, включая last_estimate; проверяются runtime counters и метрики. Равенство выполнено на всех train/development/validation.

## 3. Baseline и измеритель

Реально исполняется **GuardedReadoutObserver**, `guarded_readout_v7.yaml`, gain=1, holdoff=0.5, inner wheel_time_compensation=0, adaptation_tau=0.5, output20Hz/alignment0. Проверяются фактическая эквивалентность JSON/YAML и source hashes. Сравниваются **опубликованные Estimate.v/s**, а не внутренние observer.v/s. Исторические цифры не подставляются вместо исполнения.

Импортированы без редактирования `evaluate.replay/score/distance_surrogate`, `experiment.match/metrics`, исходное `fault_windows` и `v6.summary/macro`. Старый alias `baseline_v2` нужен только интерфейсу score: здесь он означает v7 и сразу переименовывается в `R2_v7`. `balanced_physics` в этом интерфейсе — точная off-ablation `R2_off`, не старый физический baseline. Старые pins/models/decide не переписаны.

Отдельный R2-checker сохраняет **≥2% clean gain ИЛИ ≥5% original fault gain**; clean/fault/pooled regression ≤0.5%; scalar-span distance ≤1%; clean каждого bag/receiver ≤baseline+max(0.005 м/с,5%baseline). Запрещены новые false stops/individual unrecovered, потери n/coverage, causality errors/unexpected resets. Нулевой baseline имеет предзарегистрированный абсолютный guard 1e−12. Missing reference не равно нулевой ошибке. Extra suites не заменяют original admission.

Distance — reanchored scalar-span RMSE относительно интеграла matched GNSS-speed, **не xyz/ENU и не полный terminal drift**. Два receiver одной записи не считаются независимыми поездками. Bootstrap по соседним ticks не применялся.

## 4. Train и development: все варианты, без validation tuning

Выполнены все **64 train bag**, только три vehicle topic, без train GNSS и fitting. На train проверяются исполнение canonical v7 и off-ablation; это не независимая разметка точности.

Development: **17 bag / 7 групп**, reference в **6 группах / 19 bag-receiver парах**, 394221 matched samples. Настоящая development роль, read-only SQLite, role gate до IO, хеши закреплены. Original suite **56 сценариев / 60 reference-сравнений**, extra **91 / 107**. Все missing reference и открытые топики сохранены.

Предварительное правило выбора: среди ненулевых L, прошедших coverage/safety/regression guards, минимальный clean macro, затем fault macro и меньший L. Минимальный development gain не требовался для одного validation. Поэтому выбор50мс не означает, что он лучше baseline на development.

| Development | Clean RMSE, м/с | Изменение | Original fault RMSE, м/с | Изменение | Distance RMSE, м |
|---|---:|---:|---:|---:|---:|
| R2_v7 | 0.092668142983 | — | 0.237548612056 | — | 5.310295004801 |
| H17_L050 | 0.092694120838 | +0.028033% | 0.235181343098 | −0.996541% | 5.303966076231 |
| H17_L100 | 0.092733328201 | +0.070343% | 0.235457205894 | −0.880412% | 5.297989578899 |
| H17_L200 | 0.092834546068 | +0.179569% | 0.243956538526 | **+2.697522%** | 5.287311828582 |

L=0.05 и0.10 прошли development regression/safety; L=0.20 отвергнут по fault aggregate. Выбран L=0.05 как лучший clean среди допустимых **ненулевых** вариантов; baseline остаётся лучше по clean aggregate. У всех нет новых false stops/unrecovered/coverage loss; 4 уже существовавших original non-recovery сохранены.

Механизм L=0.05 изменял команду на **21611 ticks=1080.55с**; найдено **2835 переходов в6группах**, максимум истории6samples. Все предварительные пороги ≥100 изменённых ticks, ≥20 переходов из≥3групп и≥3reference-групп пройдены. L=0.10/0.20 активны на40430/70690ticks соответственно.

**Группы предпочитают разные L: четыре из шести —0, одна —0.10, одна —0.20.** Ни одна группа не имеет уникального optimum0.05. Это записано в FREEZE до validation: общий физический dead time не идентифицирован. Числа каждой группы доступны в development/decision.json.

Существенные локальные риски development не скрываются: original10с dropout `30639_dce52be4/master` event RMSE0.227959065→0.262778818м/с (+15.274564%); extra low-speed lock `30639_0ab96c59/rover` full-window RMSE1.236920959→1.313259270м/с (+6.171640%). Recovery original10с dropout `30618_0652866c` ухудшился на0.3с у обоих receivers. Numeric per-bag guard относится к clean; extra safety блокирует новые невосстановления/false stops, не меняет gain target задним числом.

## 5. Один frozen validation — REJECTED

**19 bag / 10 групп**, reference в **9 группах / 30 bag-receiver парах**. Четыре bag без reference — `30618_2255aade`, `30618_4e1e3181`, `30618_7bfbb5ed`, `30618_95c49c30` — не получают нулевую ошибку. Original **76 сценариев / 120 reference-сравнений**; extra **133 / 210**. Оба receivers сохранены. Все числа ниже получены новым исполнением baseline и frozen L=0.05.

| Метрика | R2 v7 | H17 L=0.05 | Абсолютная дельта | Изменение ошибки |
|---|---:|---:|---:|---:|
| Clean group-macro RMSE, м/с | 0.114549861317 | 0.114548992064 | −0.000000869253 | **−0.000759%** |
| Original fault-event group-macro RMSE, м/с | 0.538286782601 | 0.541772714987 | +0.003485932386 | **+0.647598%** |
| Pooled clean RMSE, м/с | 0.216406794155 | 0.216419760322 | +0.000012966168 | +0.005992% |
| Scalar-span distance RMSE, м | 4.595480653018 | 4.596884883234 | +0.001404230216 | +0.030557% |
| Clean macro MAE, м/с | 0.047549651404 | 0.047524964069 | −0.000024687335 | −0.051919% |
| Clean macro signed bias, м/с | −0.015975155952 | −0.016019358766 | −0.000044202814 | модуль +0.276697% |
| Clean macro p95, м/с | 0.131696583956 | 0.131676005305 | −0.000020578650 | −0.015626% |
| Macro confirmed recovery, с | 0.226255203389 | 0.225907981167 | −0.000347222222 | −0.153465% |

Matched speed samples **698891→698891**. False stops clean/original/extra **18/0/0→18/0/0**. Original и extra unrecovered **0→0**. Нет новых индивидуальных non-recovery, causality errors или unexpected resets. n/coverage совпадают в каждой паре. Clean RMSE улучшился в20receiver-парах, ухудшился в10; все локальные clean ухудшения в пределах guard. Это не отменяет недостаточный gain и fault aggregate regression.

Recovery локально ухудшился: original lock `30639_9f0b519f/master`,0.049521677→0.149521677с (+0.1с). Две другие original пары улучшились на0.05/0.10с. Extra low-speed lock `30618_68d1748a`, оба receiver +0.05с. Новых невосстановлений нет; все recovery_s сохранены.

### Все validation bag

Описательная средняя clean RMSE по доступным receiver; не замена group-macro. Детальные per-receiver/per-fault метрики находятся в raw CSV.

| Bag | v7, м/с | H17, м/с | Изменение |
|---|---:|---:|---:|
| 30618_0686195f | 0.095399563522 | 0.095409791658 | +0.010721% |
| 30618_2255aade | нет reference | нет reference | — |
| 30618_2dbce472 | 0.088155034084 | 0.088147403922 | −0.008655% |
| 30618_2f104a1d | 0.046442374157 | 0.046420515915 | −0.047065% |
| 30618_437e855c | 0.033074850925 | 0.033017694033 | −0.172811% |
| 30618_49fe4c54 | 0.468360266145 | 0.468360473738 | +0.000044% |
| 30618_4e1e3181 | нет reference | нет reference | — |
| 30618_68847170 | 0.036763786505 | 0.036731443797 | −0.087974% |
| 30618_68d1748a | 0.232164516433 | 0.232334422676 | +0.073184% |
| 30618_76e1f9c7 | 0.030942255665 | 0.030904799707 | −0.121051% |
| 30618_7bfbb5ed | нет reference | нет reference | — |
| 30618_95c49c30 | нет reference | нет reference | — |
| 30618_b15eafc3 | 0.029810630850 | 0.029806970429 | −0.012279% |
| 30618_b8044aa0 | 0.028235714006 | 0.028220285611 | −0.054641% |
| 30618_defd0170 | 0.111743343840 | 0.111727241929 | −0.014410% |
| 30639_3b3d9eb8 | 0.226544685293 | 0.226621638144 | +0.033968% |
| 30639_50956d6e | 0.249342440939 | 0.249343426294 | +0.000395% |
| 30639_9f0b519f | 0.035887705603 | 0.035851758216 | −0.100166% |
| 30639_d601d28f | 0.108812577459 | 0.108829263467 | +0.015335% |

### Существенные локальные регрессии

| Bag/receiver | Режим/метрика | v7→H17 | Изменение |
|---|---|---|---:|
| 30618_68d1748a/master | clean RMSE | 0.146295883→0.146612176м/с | +0.216201% |
| 30639_9f0b519f/rover | clean distance RMSE | 10.480994133→10.515890125м | +0.332945% |
| 30618_2f104a1d/rover | clean distance RMSE | 0.311448984→0.315289421м | +1.233087% |
| 30618_b8044aa0/rover | clean p95 | 0.059735417→0.059905549м/с | +0.284809% |
| 30618_68d1748a/master | clean signed bias | −0.002974901→−0.003080755м/с | модуль +3.558263% |
| 30618_defd0170/master | original dropout110.2–120.2с, event RMSE | 0.153656932→0.199812579м/с | **+30.038116%** |
| 30618_defd0170/master | тот же fault+10с, RMSE | 0.119057654→0.150884830м/с | +26.732574% |
| 30618_defd0170/master | тот же fault+10с, p95 | 0.277286989→0.372013271м/с | +34.161820% |
| 30618_437e855c/master | extra dropout50.85–55.85с после нейтрали, event RMSE | 0.203728895→0.259364662м/с | **+27.308727%** |
| 30618_437e855c/master | тот же fault+10с, RMSE | 0.125835981→0.157202202м/с | +24.926273% |

`event_rmse` ограничена временем самого отказа. RMSE/MAE/bias/p95 fault-row охватывают отказ **плюс10секунд**. Локальная distance +1.233087% не равна превышению агрегированного distance guard1%: агрегат +0.030557%. Полный audit сохраняет все положительные локальные регрессии и recovery deltas, не заменяя исходный decision новыми правилами.

## 6. Активация, переходы, extra suites

В validation L=0.05 меняет выбранную команду на **33918 ticks=1695.9с**, из462424 обработанных step ticks. **4501 переходов в10группах**,9reference-групп. История достигла6samples, а не64. NO_HISTORY39ticks, CURRENT_INVALID1017; исходный command_stale1016 как у baseline. История использует строгий stamp≤t, legacy freshness сохраняет собственную допусковую проверку; её флаг не переписывается.

Первый переход к положительной команде на первом development bag `30618_0652866c`:

| t,с | Текущая u | Delayed u | drive_a v7,м/с² | drive_a H17,м/с² |
|---|---:|---:|---:|---:|
| 14.55 | 0 | 0 | 0.047532878 | 0.053986025 |
| 14.60 | 0.066666667 | 0 | 0.063831287 | 0.047532878 |
| 14.65 | 0.066666667 | 0.066666667 | 0.078181488 | 0.063831287 |
| 14.70 | 0.066666667 | 0.066666667 | 0.090816357 | 0.078181488 |

Реакция target сдвинута на один tick при прежней tau. Это исполнение механизма, не доказательство истинного physical L.

Validation, первые2с после смены режима, group-macro:

| Новый режим | Matched phase samples | RMSE v7 | RMSE H17 | Изменение |
|---|---:|---:|---:|---:|
| Торможение | 61378 | 0.095810581 | 0.095726543 | −0.087713% |
| Нейтраль/выбег | 50852 | 0.113053701 | 0.112992973 | −0.053716% |
| Тяга | 58734 | 0.091942468 | 0.092062359 | +0.130399% |

Phase MAE/bias/p95 сохранены. Anchors/режимы выбираются только по vehicle-сигналам; при близких переходах используется последний режим. Эти окна не независимые поездки.

Original suite по типам:

| Тип | Event RMSE v7 | Event RMSE H17 | Изменение |
|---|---:|---:|---:|
| front bias5с | 0.414421398 | 0.414340974 | −0.019407% |
| both dropout5с | 0.558804079 | 0.562720067 | +0.700780% |
| both dropout10с | 0.723733997 | 0.732167493 | +1.165276% |
| both lock3с | 0.456187656 | 0.457862327 | +0.367101% |

Отдельные extra suites, НЕ вместо original admission:

| Диагностика | Event RMSE v7 | Event RMSE H17 | Изменение |
|---|---:|---:|---:|
| wheel dropout5с после нейтрали | 0.260012925 | 0.252749901 | −2.793332% |
| controller loss1с после нейтрали | 0.057846882 | 0.057856231 | +0.016162% |
| wheel dropout5с после тяги | 0.233009354 | 0.237091866 | +1.752081% |
| controller loss1с после тяги | 0.060132900 | 0.060421201 | +0.479439% |
| wheel dropout5с после торможения | 0.312053277 | 0.279473094 | **−10.440583%** |
| controller loss1с после торможения | 0.053778236 | 0.053737654 | −0.075463% |
| low-speed lock3с | 0.099481300 | 0.103309553 | **+3.848214%** |

Польза в специальном brake-transition сценарии не переносится на основной контракт. H17 остаётся REJECTED.

### Состояние до, во время и после отказа

Original dropout `30618_defd0170`, source window[110.2,120.2)с; скорости ниже опубликованные:

| t,с | disturbance v7/H17,м/с² | v7/H17,м/с | Mode обоих |
|---|---|---|---|
| 110.199985031 | −0.162126256 / −0.157923095 | 2.069490768 / 2.069426679 | MODEL_ONLY |
| 110.249985031 | −0.099273510 / −0.095217383 | 2.118642322 / 2.118674704 | FUSED |
| 111.149985031 | −0.099273510 / −0.095217383 | 2.804582415 / 2.803949837 | MODEL_ONLY |
| 120.199985031 | −0.099273510 / −0.095217383 | 5.795628089 / 5.892866089 | MODEL_ONLY |
| 120.449985031 | −0.118148202 / −0.114867712 | 5.244384845 / 5.243693683 | MODEL_ONLY |
| 121.149985031 | −0.115153333 / −0.114198936 | 4.780002435 / 4.780267771 | MODEL_ONLY |

Инъекция удаляет события по исходным stamps, штатная Timeline/порядок доставки не меняются. Поэтому FUSED tick около начала окна не переименован в MODEL_ONLY. На последнем tick перед началом drive_a0.923613347/0.919795663м/с²; delay меняет накопленную disturbance до/в начале dropout, хотя формула адаптации прежняя. Связь этих различий с последующим ухудшением — описательная интерпретация сохранённой трассы, **не новый причинный эксперимент** и не повод для настройки после validation. Все u/delayed_u/drive_a/internal/published/state traces доступны в raw JSON.

## 7. Стоимость, CI и непроведённый ROS benchmark

Development bag `30618_0652866c`, первые120с, warmup10с, OMP/OPENBLAS=1, одинаковый сбор outputs. Для каждого L —3парыAB/BA, то есть6A+6B, всего36replay. Для выбранного L=0.05 каждый прогон содержит2200 measured post-warmup steps и2400outputs.

| Измерение | Median v7,с | Median H17,с | Median парного изменения | Диапазон |
|---|---:|---:|---:|---:|
| replay CPU | 0.111115389 | 0.127158294 | **+14.135149%** | +11.916…+16.257% |
| replay wall | 0.111121131 | 0.127258964 | +14.149787% | +11.923…+16.257% |
| step CPU | 0.079598609 | 0.094633367 | **+18.327447%** | +15.791…+20.583% |
| step wall | 0.076434638 | 0.091458483 | +19.057166% | +16.436…+21.372% |

Это instrumented offline Python, не latency ноды. Median sum step CPU/2200 ≈36.18→43.02мкс/step. Хеши outputs каждого алгоритма одинаковы во всех6повторах. Peak RSS всего процесса **120303616байт** включает NumPy/SciPy и входные массивы; это не incremental memory истории и не RSS установленной ноды.

| Проверка | Фактический результат |
|---|---|
| Core | 26 tests PASS |
| Timeline | 10 tests PASS |
| Guarded readout | 34 tests PASS |
| H17 mechanism + driver/role/admission | 35 tests PASS:23+12 |
| Существующие research-integrity | 43 tests PASS, exit0 |
| Повтор H17 на frozen checkout | те же35 tests PASS, не новые уникальные тесты |
| Compile/preflight | PASS, конфигурации и23hashes совпали |
| Real64train/17development/19validation | Все завершены; роли/топики записаны |
| Exact off | Каждый Estimate, canonical state, метрики/counters совпали |
| Стандартный source CI | Все4jobs success |

[Research36184586680](https://github.com/jabrailkhalil/hack/actions/runs/36184586680), job108234779230, и [validation36185617651](https://github.com/jabrailkhalil/hack/actions/runs/36185617651), job108238128429, завершены success. Это успешное **исполнение измерений**, не успешная приёмка H17. [СтандартныйCI36184586284](https://github.com/jabrailkhalil/hack/actions/runs/36184586284) имел success у core/research-integrity/offline-limited/ros-humble, но запускал установленный canonical v7, **не включённый H17**. Исторические release-hash проверки не удалялись.

**Свежий installed enabled-H17 ROS benchmark под2CPU/500000000bytes в обоих clock modes не проводился:** accuracy уже отвергнута; задание допускает не выполнять полный benchmark. Нельзя присваивать H17 исторические latency/RSS или feature-off CI. Новый executable/canonical launch для production не создавался.

Offline elapsed train197.071489с, development133.895385с, cost4.988029с, validation133.375797с — время целых этапов, не latency и не hard-real-time гарантия.

## 8. Наука и математические проверки

Consensus: узкий поиск, карточка и abstract Zhang et al.(2022), *Robust Speed Tracking Control for Future Electric Vehicles under Network-Induced Delay and Road Slope Variation*, Sensors22(5),1787, [DOI10.3390/s22051787](https://doi.org/10.3390/s22051787). У издателя прочитаны доступные HTML-разделы модели и ограничений, включая Remark4. Это IMT controller с другими motor/wheel/torque предпосылками; wheel-speed≈vehicle-speed нарушается при slip. Сенсорная схема не перенесена; симулированные CAN1–20мс не обосновывают наши50–200мс.

Scite: фактический вызов вернул месячный лимит25calls, сброс2026-10-01UTC. Карточка/полный текст/citation contexts через Scite не получены. Покупок/изменений прав не было. Mentioning не равно проверке результата.

WolframContext и LanguageEvaluator выполнены. Исполнимый `science/wolfram.wl` и фактический `wolfram_output.txt` сохранены, включая предупреждения сервиса. Идеальная модель:

```
H(s) = K exp(-L s)/(1+tau s)
step(t) = K(1-exp(-(t-L)/tau)) UnitStep(t-L)
|H(iw)| = K/sqrt(1+(tau*w)^2)
phase = -L*w-atan(tau*w)
```

Laplace residual0; actuator pole−1/tau; exp(−dt/tau) строго между0и1; alpha20Hz=.11953366485039196. Проверены единицы dt/tau, фазы и пределы L→0, tau→0. Низкочастотное phase=−(L+tau)w+tau³w³/3 показывает смешение L/tau. Двухчастотный phase Jacobian невырожден при разных положительных частотах в идеальной модели, но не отделяет неизвестный sensor lag/slip.

Это **не доказательство устойчивости полного nonlinear observer** и не идентификация физического L. Переходов достаточно для активации, но разные group optima и отсутствие отдельного actuator reference не позволяют установить общий физический dead time.

## 9. Воспроизведение и включение

Чистая отдельная рабочая копия, Python3.13.5:

```bash
git switch --detach ed62dc651937b9bcc49ad2a445c20630883aac1f
python3.13 -m venv .venv-h17
source .venv-h17/bin/activate
python -m pip install -r requirements-research.txt
python tools/get_dataset.py
export PYTHONPATH=src/reserve_odometry
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
python -m unittest discover -s research/R2/H17/tests -v
python research/R2/H17/driver.py --stage train \
  --output /tmp/H17-repro-train --workers 2
python research/R2/H17/driver.py --stage development \
  --output /tmp/H17-repro-development --workers 2
python research/R2/H17/driver.py --stage cost \
  --output /tmp/H17-repro-cost
python research/R2/H17/driver.py --stage validation \
  --freeze research/R2/H17/FREEZE.json \
  --freeze-commit ed62dc651937b9bcc49ad2a445c20630883aac1f \
  --output /tmp/H17-repro-validation --workers 2
```

Нужны новые output dirs. Validation отказывается работать при несовпадении source hashes или отсутствии FREEZE в реальном commit. Повтор того же freeze — для воспроизводимости, не для выбора удачного результата. В validation исполнялся только L=0.05; другие два там не оценивались. CLI не имеет test-stage.

**Checkout сам по себе не включает H17 в ROS.** Runtime-модуль уже в измеренном commit, повторный git apply не нужен. Driver явно создаёт:

```python
CommandDeadtimeObserver(Config(**profile['config']),
                        readout=ReadoutConfig(**profile['readout']),
                        delay_s=0.05)
```

Canonical `ros2 launch reserve_odometry odometry.launch.py` остаётся v7. Отдельный patch добавляет модуль к baseline, но без подключения factory не переключает executable. Изменение production executable не выполнено: кандидат отвергнут.

Описательный audit сохранённых JSON, без нового replay/подбора:

```bash
python audit.py /path/to/development-artifact /tmp/H17-dev-audit.json
python audit.py /path/to/validation-artifact /tmp/H17-val-audit.json --stage validation
```

## 10. Immutable evidence и ограничения

[Development/train/cost checkpoint](https://github.com/jabrailkhalil/hack/tree/eaf71d94943cf8d37efc497b531b8edb7315f858/reports/research_R2/H17/36184586680-1): per-bagJSON, CSV, access journals, logs, measured source.tar и runtime patch.

[Validation checkpoint](https://github.com/jabrailkhalil/hack/tree/36b749fe71a033e0ea0b4cf24d1a8e9ab1b90cbf/reports/research_R2/H17/36185617651-1): FREEZE, полный results.json, per-bagcheckpoints, CSV, access, команды/логи, source.tar (PLAN/tests/worksheet/код), patch.

[aggregate.csv](https://github.com/jabrailkhalil/hack/blob/36b749fe71a033e0ea0b4cf24d1a8e9ab1b90cbf/reports/research_R2/H17/36185617651-1/validation/aggregate.csv), [всеbag/receiver/faultCSV](https://github.com/jabrailkhalil/hack/blob/36b749fe71a033e0ea0b4cf24d1a8e9ab1b90cbf/reports/research_R2/H17/36185617651-1/validation/per_bag.csv), [decision.json](https://github.com/jabrailkhalil/hack/blob/36b749fe71a033e0ea0b4cf24d1a8e9ab1b90cbf/reports/research_R2/H17/36185617651-1/validation/decision.json).

| Артефакт | SHA256 |
|---|---|
| Development ZIP id10885633452 | `eb75e69310dd8c07844417237023e13fa5428a873db4b0dfd16e048467098ff0` |
| Validation ZIP id10886033773 | `0945c490cab809d5a4527dc7572130716840c51c82bdca232208994ead08cb37` |
| Runtime patch | `1588c194ae950f4e9ba7fec17b2cfa67dbbd59ec5e23240f5a493d2d0733226f` |
| Runtime module | `f3ae15daf9505959e71c466dd4c6810ed962fc758a410e719adfaafc5c1de765` |
| Validation results.json | `c38027b2bc4279ae483781c6f2a58e17c326c748c58ff0da68be81be227d209c` |

Run/attempt каталоги новые; старые отчёты не перезаписаны. Raw bags/секреты/кэши не коммитились. Checkpoints сохраняют evidence независимо от срока Actions artifacts. Поздний audit описывает сохранённые результаты и не меняет frozen driver.

Журналы подтверждают только64train/17development/19validation роли; train без GNSS. Общий закреплённый архив скачан, но final/test measurements не открывались для оценки/подбора и не переоценивались. Стандартные исторические integrity-проверки не являются новым final-test измерением. Повторно используемый validation не независимый final test.

Ограничения: source-time→actuator time не идентифицирован отдельно; масштаб колёс1/3.6 остаётся исходной эмпирической предпосылкой; история видит только команды на unchanged20Hzstep-сетке; относительная1Dодометрия, не xyz; slip/sensor lag смешиваются с delay; extra suites ограничены заранее заданными anchors; enabled ROS/runtime certificate отсутствует; Scite citation-context этап недоступен из-за квоты. **Оставить R2 baseline: H17_L050 не готов к merge.**
