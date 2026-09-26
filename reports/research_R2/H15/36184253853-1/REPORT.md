# H15 / R2-v7-fixed — REJECTED

**Исследовательский артефакт, не готов к merge.** Проверенный кандидат `h15_l004` уменьшил original fault-event group-macro RMSE на **0.890428%**, но общий контракт требует минимум 5% либо минимум 2% clean gain. Clean практически не изменился. Причина отказа — `insufficient_gain`; остальные численные ограничения и проверенные safety-инварианты пройдены. Это отрицательный результат выбранного кандидата, а не опровержение семейства структурированных поправок.

Механизм действительно активировался на реальных записях. Статус механизма: **покрытие достаточное**. Статус точности: **REJECTED**. Готовность к merge: **нет**. Параметры после validation не менялись.

## 1. Идентификаторы и происхождение

| Объект | Значение |
|---|---|
| Round ID | R2-v7-fixed |
| Фиксированный baseline | `65bba39ed05c781f3f69a65c02f69931152cbfd9` |
| Observer baseline | `GuardedReadoutObserver`, `guarded_readout_v7.yaml` |
| Ветка | `research/round2-H15` |
| PLAN до экспериментов | `3b1c63e6a1536843f866f800f851f357691ff350` |
| **Измеренный source commit** | **`5b9ab8429741c7ccdb5969ee68aeb9402f79150c`** |
| Freeze, опубликованный до validation | `dff80eecff17dd2ef100060f68649908513cf466` |
| Неизменяемый checkpoint исходных результатов | `45fff4e2ab65ce2382f4228158ccf69f50e4394c` |
| Run / attempt | `36184253853 / 1` |
| Выбранный вариант | `h15_l004`, ridge=0.04 |

[Фактический workflow](https://github.com/jabrailkhalil/hack/actions/runs/36184253853) завершён success. Это успешное исполнение исследования, не прохождение accuracy-gate. Исходный workflow head `3cb6c994...` содержал транспорт исходников; job проверил хеш, опубликовал читаемый код отдельным commit `5b9ab842...` и только затем запустил измерения. Именно последний — measured source SHA.

Freeze создан **25.09.2026 20:15:44.358537 UTC**, опубликован отдельным коммитом, validation started — **20:15:46.984592 UTC**. [FROZEN.json](FROZEN.json) содержит код, эффективный профиль, параметры, split/data hashes, хеши development-результатов и решения. [freeze_provenance.json](validation/freeze_provenance.json) связывает выполненный validation с опубликованным freeze. Freeze SHA256: `c5fc0664d866688c37e2af72b7f1b1693527d3ae3f0df5ca79519510a24afd8c`.

Основная ветка, чужие ветки, старые отчёты и исторические release-manifests не изменены. H11/v8 не включён, несмотря на продвижение main. Отчётный коммит добавляет evidence и безопасную ручную инфраструктуру повтора; он не является новым измеренным алгоритмом.

## 2. Изменение алгоритма и отличие от прежних попыток

H04 менял скорость обучения legacy disturbance, H07 — динамику привода, H10 — совместное состояние [v,d], v6 — проекцию/затухание. В H15 эти механизмы не объединяются. Сохраняются legacy d и его learning rule, wheel gates, readout, reacquisition, low-speed/zero-lock guard, физические коэффициенты, единицы, Timeline, частота 20 Гц и искусственная задержка 0.

В здоровом режиме отдельно накапливается ограниченная регрессия:

`y_i = b + gamma*x_i + error_i`, где `x_i=drive_a`, `y_i=measured_a-drive_a+resistance(v)`.

y — та же wheel-derived цель, которая уже вычисляется для legacy d. Это псевдоразметка, не независимая истина. b — nuisance intercept, gamma — относительная поправка к моделируемому приводу; это не идентифицированные физические масса или уклон.

Два заранее заданных варианта: ridge **0.01 / 0.04 (м/с²)²**. Окно не более **2 с / 40 точек**, минимум 6 точек за 0.5 с, Var(drive)>=0.0025, condition нормированного Gram<=1000, fit RMSE<=0.5 м/с², gamma в [-0.25,0.25]. Учитываются только новые FUSED-пары с действительной командой; дополнительные условия: speed>1 м/с, age<=0.20 с, skew<=0.05 с, разность колёс<=0.15 м/с, innovation<=0.6 м/с, |y|<=1.2 м/с². Исходные derivative/rate guards сохраняются.

После исходного gate причинная потеря определяется отсутствием accepted wheels и хотя бы одним статусом, отличным от DUPLICATE_OR_OLD. Обычный prediction-only tick с удерживаемыми дубликатами сам по себе не объявляется отказом. Фиксируются d_loss, drive_loss и обученный gamma, затем:

`d_eff(t)=clip(d_loss+gamma*(drive_a(t)-drive_loss), -disturbance_limit, +disturbance_limit)`.

Первый шаг потери непрерывен по поправке: drive_a=drive_loss. В отказе gamma не обучается; история очищается. Недостаток возбуждения, устаревшая история или плохая обусловленность дают gamma=0 и исходное удержание d. Stale command отменяет gamma для текущей сессии. При accepted wheel возвращается legacy prediction/fusion/adaptation, при reacquisition/stop auxiliary loss очищается. Новых runtime-зависимостей нет; память ограничена deque(40) и скалярными полями.

**Как включается:** tracked core остаётся baseline. В исследовательской рабочей копии применяется [algorithm.patch](source/algorithm.patch), а фабрика создаёт `DriveDependentObserver(..., correction=DriveCorrectionConfig(enabled=True, ridge=0.04))`. Сам checkout, применение патча без выбора нового класса или обычный `ros2 launch` **не активируют H15**. ROS-launch/profile намеренно не продвигаются после отрицательной точности.

SHA256 применённого core: `896ea343ec4198d75dec08fa18429be4b33d40bad4606404c5db0db5ee35ec71`.
SHA256 [модуля](source/drive_disturbance.py): `4c5c461187f8133062953859102b1c34f945cd784e4ea5a77e4d72c3c5adec01`.

## 3. Измеритель, данные и предварительные условия

[PLAN](source/PLAN.md) опубликован до экспериментов. Все границы и оба ridge-значения заданы до development. Train использовался для проверки механизма, не для переопределения этих параметров. Нет скрытого третьего варианта, абляций после validation или настройки по другим R2-агентам.

Driver проверяет реальные class/profile/launch и побайтные baseline-pins. Baseline — независимая копия исходного v7 core+guarded_readout, candidate — новый класс поверх применённого hook-патча. Неизменные `evaluate.score/replay`, matching, reference masks и original fault_windows используются через изолированную фабрику. Group aggregation прежняя; отдельные проверки дополняют недостающий pooled veto и запрет новых индивидуальных unrecovered cases.

**В raw JSON ключ `baseline_v2` — обязательный legacy alias evaluator, но фактически означает канонический R2 v7, НЕ v2/v5.** `balanced_physics` здесь — patched no-hook v7; `off` — выключенный H15. В каждом clean/fault/phase replay массивы outputs и runtime counters этих двух контролей точно равны каноническому v7. Сравниваются опубликованные Estimate.v/s, не внутренние observer.v/s. Unit-проверка дополнительно сравнивает все исходные поля состояния, статусы и Estimate.

| Роль | Реально выполнено | Reference |
|---|---|---|
| Train | Все 64 bag, первые <=180 с; 208014 outputs на модель | Только controller/front/rear; reference_accuracy=null |
| Development | Все 17 полных bag / 7 групп; 56 original faults | 19 clean bag/receiver-пар, 60 fault-пар; reference в 6 группах |
| Phase diagnostics на development | 26 дополнительных dropout-окон: 13 тяга→выбег, 13 выбег→торможение | 15 receiver-сравнений на каждый тип перехода |
| Validation | Все 19 полных bag / 10 групп; 76 original faults | 30 clean и 120 fault-пар; reference в 9 группах |

Настоящая роль development не переименована. Новый read-only loader проверяет membership/checksum до SQL; train/validation используют штатный loader. [Access journals](development/access.json) сохраняют реальные роли и разрешённые topics. Train GNSS закрыт. Архив данных штатно скачан и распакован, но final/test measurement payloads через SQLite не открывались и не пересчитывались. Четыре validation-bag без reference сохранены как missing, не нулевые ошибки. Два GNSS-приёмника не объявляются независимыми поездками.

Original faults: bias одного колеса 5 с, dropout обоих 5/10 с, zero-lock 3 с; прежние anchors и warmup/recovery windows. Отдельная phase suite объявлена до экспериментов: первый подходящий переход каждого типа в каждом development-bag по vehicle-сигналам, dropout с 0.3 с до перехода длительностью 5 с. Эти результаты не заменяют original admission.

## 4. Development: все варианты и честный выбор

| Вариант | Clean RMSE | Original fault RMSE | Fault изменение к v7 |
|---|---:|---:|---:|
| Baseline v7 | 0.092668142983 | 0.237548612056 | — |
| ridge=0.01 | 0.092666861348 | 0.253620736079 | **+6.765825%** |
| ridge=0.04 | 0.092667070193 | 0.245887263428 | **+3.510293%** |

Оба варианта на development хуже по original fault aggregate. Это не скрыто: [decision.json](development/decision.json) сохраняет их отрицательные admission checks. PLAN заранее разрешал однократную validation лучшего из двух вариантов без обязательного development gain, но только после прохождения safety и достаточного покрытия. По этому правилу выбран ridge=0.04: меньшая original fault ошибка, не результат специальной phase suite.

У обоих кандидатов нет новых false stops, потери coverage, причинных ошибок, resets или новых unrecovered cases. Четыре development unrecovered уже есть у baseline; они не исчезли и не увеличились. Для выбранного варианта зарегистрированы **41248 fit-пересчётов в 14 bag**, **2942 effective correction ticks в 11 bag** original+phase. Предварительный минимум: 100 fits / 3 bag и 20 effective ticks / 3 bag. Это коррелированные пересчёты перекрывающихся окон, не тысячи независимых испытаний.

Существенная development-регрессия выбранного кандидата: `30639_dce52be4`, dropout10, master **0.227959065→0.545960641 м/с (+139.50%)**, rover **0.234228605→0.547584340 (+133.78%)**. У меньшего ridge этот же master ещё хуже: 0.666997895 (+192.60%). Локальный fault-порог не добавлялся задним числом; все строки сохранены в [per_bag.csv](development/per_bag.csv).

## 5. Единственный validation выбранного freeze

Плюс в дельте означает рост ошибки. Малые clean/distance изменения показаны без заявления практически значимого выигрыша.

| Метрика | Baseline v7 | H15 ridge=0.04 | Абсолютная дельта | Изменение |
|---|---:|---:|---:|---:|
| Clean group-macro RMSE, м/с | 0.114549861317 | 0.114549861008 | -3.09628e-10 | -0.0000002703% |
| Original fault-event group-macro RMSE, м/с | 0.538286782601 | 0.533493726450 | -0.004793056151 | **-0.890428%** |
| Pooled clean RMSE, м/с | 0.216406794155 | 0.216406793828 | -3.26603e-10 | -0.0000001509% |
| Scalar-span distance RMSE, м | 4.595480653018 | 4.595480579264 | -7.37538e-8 | -0.0000016049% |
| Clean MAE, м/с | 0.047549651404 | 0.047549650907 | -4.96185e-10 | практически без изменения |
| Clean signed bias, м/с | -0.015975155952 | -0.015975156388 | -4.35675e-10 | практически без изменения |
| Fault+recovery MAE, м/с | 0.225316973762 | 0.223786888868 | -0.001530084894 | описательная метрика |
| Fault+recovery signed bias, м/с | -0.065924573423 | -0.065853329397 | +0.000071244026 | описательная метрика |
| Group-macro recovery, с | 0.226255203389 | 0.226602425611 | +0.000347222222 | немного медленнее |
| Matched clean samples | 698891 | 698891 | 0 | без потери |
| False stop samples clean / fault | 18 / 0 | 18 / 0 | 0 | без роста |
| Unrecovered original fault comparisons | 0 | 0 | 0 | без роста |

MAE/bias fault вычислены по штатной маске отказ+10 с recovery; это НЕ event-only MAE. Event-only admission использует соответствующий event_rmse. Distance — переякоренный скалярный speed-integral surrogate, не xyz/ENU и не полный terminal drift.

Контракт не смягчался: >=2% clean ИЛИ >=5% original fault gain; clean/fault/pooled regression<=0.5%; distance<=1%; per-bag/per-receiver clean<=baseline+max(0.005 м/с,5%); одинаковый coverage, отсутствие дополнительных false stops, новых unrecovered, causal errors/resets. **Единственный отказ — insufficient_gain.** Проверенные safety/regression части проходят, но этого недостаточно для CONFIRMED.

Во всех парах coverage/n совпадают. Causal errors/resets=0/0; суммарные исходные dropped/catchups=66/21 у обеих моделей. Это особенности исходного расписания, не новые потери H15. Два clean RMSE немного выросли, максимум +2.80e-9 м/с; per-bag порог не нарушен. Все исходные результаты: [JSON](validation/results.json), [aggregate CSV](validation/aggregate.csv), [per-bag/receiver/fault CSV](validation/per_bag.csv), [решение](validation/decision.json).

### Локальные validation-регрессии и улучшения

Event RMSE вырос в **15 из 120** доступных fault/receiver-сравнений. Самые заметные:

| Bag / receiver / fault | Baseline | H15 | Изменение |
|---|---:|---:|---:|
| 30639_3b3d9eb8 / master / dropout10 | 0.256751522 | 0.339926668 | **+32.40%** |
| 30639_3b3d9eb8 / rover / dropout10 | 0.253463146 | 0.336190830 | **+32.64%** |
| 30639_3b3d9eb8 / master / dropout5 | 0.241803548 | 0.275575223 | +13.97% |
| 30639_3b3d9eb8 / rover / dropout5 | 0.234086509 | 0.267430134 | +14.24% |
| 30618_b15eafc3 / master / dropout10 | 0.147294054 | 0.169626315 | +15.16% |
| 30618_b15eafc3 / rover / dropout10 | 0.149795960 | 0.171879374 | +14.74% |

На `30639_3b3d9eb8` dropout10 recovery стал медленнее: master **0.017672399→0.217672399 с (+0.20)**, rover **0.017672399→0.167672399 с (+0.15)**. Других замедлений больше численного допуска 1e-10 в полученных original validation-строках нет. Невосстановлений нет.

Для баланса: `30618_2f104a1d`, dropout10 улучшился master **0.898060946→0.748241582 (-16.68%)**, rover **0.898990669→0.749223760 (-16.66%)**. Его dropout5 улучшился примерно на25%, lock3 примерно на49%. Локальные выигрыши не заменяют общий порог.

Описательная post-hoc разбивка original validation по типам с прежним group-macro внутри типа: bias5 **0.414421398→0.414421398 (0%)**; dropout5 **0.558804079→0.553908951 (-0.8760%)**; dropout10 **0.723733997→0.715711709 (-1.1085%)**; lock3 **0.456187656→0.449932847 (-1.3711%)**. Новые варианты на этих данных не выбирались.

## 6. Активация, фазы и трассы

На train у выбранного варианта: 56242 trusted points, 28548 fit-пересчётов в59/64 bag, 58 loss-сессий с ненулевым обученным gamma, 18 effective ticks. Параметры на этих результатах не изменялись. Train не даёт независимой accuracy-оценки.

На validation: **65711 fits в19 bag**, **2136 effective ticks** в18 original fault-окнах на6 bag: `30618_2dbce472`, `30618_2f104a1d`, `30618_b15eafc3`, `30618_b8044aa0`, `30639_3b3d9eb8`, `30639_50956d6e`. Неактивность не является причиной отказа.

Предварительно объявленная development phase suite дала полезный локальный сигнал:

| Phase dropout | Baseline RMSE | ridge=.01 | ridge=.04 |
|---|---:|---:|---:|
| Тяга→выбег | 0.305613204 | 0.211469800 (-30.80%) | 0.267728414 (-12.40%) |
| Выбег→торможение | 0.263312796 | 0.218134953 (-17.16%) | 0.243838397 (-7.40%) |

Это только development, отдельная suite, не validation admission и не независимое подтверждение. Более сильный фазовый выигрыш .01 не использовался, чтобы обойти его худший original fault RMSE. Итог по общему контракту остаётся отрицательным.

Пример реально сохранённой трассы: `30639_3b3d9eb8`, original dropout [122,132). На наблюдаемом model-only tick t=122.267672399: d_loss=0.074197215, drive_loss=0.919977512, gamma=0.122085385, condition=42.80545, history=0. К t=131.967672399 drive=0.410157047, gamma остался тем же, d_eff=0.011955588. После восстановления FUSED loss очищен, начато обычное накопление trusted points. В этом случае ошибка увеличилась, несмотря на математически структурированную поправку.

Трассы сохранены в diagnostics.trace каждого fault в JSON, с шагом через два output ticks. Первый наблюдаемый trace tick не обязательно совпадает с точным началом loss. **d_eff записывается для стадии prediction, а d — после возможной adaptation данного шага**: разность этих полей в здоровом FUSED tick не является доказательством включения H15. Активация определяется stats.effective_ticks и frozen loss, а не max_abs_delta смешанных стадий. Причинная декомпозиция локальных регрессий не доказана; post-hoc анализ не выдан за новое испытание.

## 7. Проверки и вычислительная стоимость

Включённый патч реально применён в исследовательском job до тестов и данных. Фактически прошли:

| Проверка | Результат |
|---|---|
| H15 mechanism/driver tests | **28/28 PASS** |
| Исходный core subset | **26/26 PASS** |
| Timeline subset | **10/10 PASS** |
| Полный unit suite после применения патча | **144/144 PASS** |
| Research integrity suite | **43/43 PASS** |
| compileall | PASS |
| Train/development/validation, pinned manifests и disabled equivalence | PASS |

Subset-тесты входят в полный набор и не суммируются как независимые проверки. Проверены выключенная эквивалентность, prefix/future/duplicate/stale, reset, отсутствие NaN, ограниченная история, недостаток возбуждения, loss continuity, clipping, замороженный gamma, recovery и zero-lock. Отдельный synthetic common-mode ramp демонстрирует, что согласованное проскальзывание может попасть в gamma; clipping ограничивает величину, но не распознаёт физическую причину. Синтетика не считается доказательством real-data accuracy.

Все полные журналы лежат рядом с отчётом. Обычный [CI 36184253763](https://github.com/jabrailkhalil/hack/actions/runs/36184253763) имеет четыре success jobs, но относится к непатченному каноническому runtime и НЕ подтверждает включённый H15 в ROS. Исторические hash-checks не удалялись и не исправлялись ради зелёного CI.

Стоимость измерена на одном development `30618_0652866c`, prefix180с, warmup10с, OPENBLAS/OMP=1, шесть пар (3 AB +3 BA) на каждый вариант, одинаковые 3520 outputs. Медианы выбранного варианта, после warmup:

| Измерение, с суммарно за поток | Baseline | H15 .04 | Изменение |
|---|---:|---:|---:|
| step CPU | 0.123544676 | 0.146652419 | **+18.704%** |
| step wall | 0.123730177 | 0.146958051 | +18.773% |
| replay CPU | 0.185017024 | 0.228642159 | +23.579% |
| replay wall | 0.185017314 | 0.228642480 | +23.579% |

[Все повторы](development/cost.json). Replay включает сбор дополнительной candidate-диагностики; его +23.58% нельзя целиком приписывать runtime-алгоритму. Step timers исключают wrapper collector. Этот поток активирует обучение, но не effective loss correction; не измерен худший fault-path. Это offline Python CPU/wall, не publisher→subscriber latency и не RSS. Новый установленный H15 ROS benchmark в обоих clock mode под2CPU/500000000bytes **не выполнялся**, поскольку accuracy-gate отклонён. Исторический benchmark и feature-off CI не подменяют этот отсутствующий этап.

## 8. Источники, Wolfram и пределы выводов

[Источники и фактически прочитанный объём](source/SOURCES.md), [исполняемый worksheet](source/worksheet.wl), [фактический вывод Wolfram](source/wolfram-output.txt).

Consensus использован для узкого поиска; для Vahidi, Stefanopoulou, Peng (2005), DOI `10.1080/00423110412331290446`, прочитаны metadata/abstract, не полный текст. Scite предоставил первые8000 из25903 символов индексированного fulltext Rhode/Gauterin (2013), DOI `10.1109/IVS.2013.6629481`: введение, LS/TLS и ошибки в переменных. Scite citation graph был усечён и содержал mentioning; он не является независимой верификацией H15. Статьи/подписки не покупались, чужие CAN/IMU/GNSS/motor-current входы не перенесены в runtime.

Wolfram реально вывел Gram determinant `n*sxx-sx^2=n^2 Var(x)` и ridge solution `gamma=Cov(x,y)/(Var(x)+lambda)`, нулевой determinant при постоянном drive, подтвердил continuity при d_loss в пределах clip и nonexpansive clip-bound. Для y=b+gamma*x+noise ошибка ridge содержит `(Cov(x,noise)-lambda*gamma)/(Var(x)+lambda)`: correlated wheel-derived noise даёт смещение, которое не исчезает от одного ridge.

Gamma безразмерна, x/y/b имеют единицы ускорения, lambda — ускорение в квадрате. Условие Gram задано после явной SI-нормировки x/(1м/с²). b/gamma не доказывают физическую массу/уклон. Ограниченный d_eff не доказывает асимптотическую устойчивость ошибки скорости при отсутствии колёс; ковариация legacy не дополнена неопределённостью gamma. Формулы при идеальной модели не доказывают улучшение на bag.

Validation многократно использован исторически, не новый независимый final test. Ошибки scale1/3.6, неоднозначность common-mode колёс, fixed physical gauge и ограниченная репрезентативность групп сохраняются. Никаких статистически независимых миллионов ticks или универсального выигрыша не заявляется.

## 9. Воспроизведение и доступность этапов

Локальное скачивание датасета первоначально завершилось DNS-ошибкой; реальные данные успешно получены и проверены в Actions. Первый source-export run36182600585 завершился из-за shallow checkout без baseline tree; исправленный source run36182746408 успешен. Эти инфраструктурные попытки не являются дополнительными кандидатами/validation-прогонами. Основной исследовательский run выполнен один раз.

Воспроизведение в отдельной рабочей копии measured source, без активации H15 в main:

```bash
git fetch origin research/round2-H15 checkpoint/H15-36184253853-1
git worktree add --detach ../hack-H15-replay 5b9ab8429741c7ccdb5969ee68aeb9402f79150c
cd ../hack-H15-replay
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-research.txt
export PYTHONPATH=src/reserve_odometry OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
export H15_MEASURED_SHA=5b9ab8429741c7ccdb5969ee68aeb9402f79150c
python research/R2/H15/apply.py
python -m unittest discover -s research/R2/H15/tests -v
python -m unittest discover -s tests -v
python -m unittest discover -s research/tests -v
python tools/get_dataset.py
OUT="$(mktemp -d /tmp/H15-replay-XXXXXX)"
# Повтор уже выбранного freeze, без нового подбора кандидата.
git show dff80eecff17dd2ef100060f68649908513cf466:reports/research_R2/H15/36184253853-1/FROZEN.json > "$OUT/FROZEN.json"
export H15_FREEZE_COMMIT=dff80eecff17dd2ef100060f68649908513cf466
python research/R2/H15/run.py validation --frozen "$OUT/FROZEN.json" --output "$OUT/validation"
```

Фактически до freeze выполнены также:

```bash
python research/R2/H15/run.py train --output "$OUT/train"
python research/R2/H15/run.py development --output "$OUT/development"
python research/R2/H15/run.py freeze --development "$OUT/development" --output "$OUT/FROZEN.json"
# Затем commit/push freeze перед validation; см. source/executed-workflow.yml.
```

Новые output paths обязательны, runner отказывается перезаписывать результаты. Исторический executed-workflow сохранён побайтно. В поздней отчётной версии повторный workflow становится manual-only и использует уже опубликованные читаемые исходники; удаляются лишь одноразовые H15 transport-файлы. Реализация, параметры, PLAN, raw evidence и старые отчёты не изменяются.

Artifact `R2-H15-evidence-36184253853-1`, ID10885123102, SHA256 `221339991d1ba1f65622df61db1c0a2f410d1595876315393c77019f3990245d`; исходный checkpoint хранит evidence независимо от 30-дневного artifact retention. Raw bags, секреты и кэши не коммитились.

**Итог: полезный сигнал в целевых development-переходах есть, общий требуемый выигрыш не получен. H15 .04 — REJECTED, исследовательский артефакт, не готов к merge.**
