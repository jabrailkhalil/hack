# R4-H40 — REJECTED на development

**Исследовательский отрицательный результат, не готов к merge.** Единственный вариант H40_implicit_coulomb реализован и измерен. Причина отказа — `insufficient_gain`: clean RMSE уменьшается на 0.0411836%, original fault RMSE на 0.4918357%, меньше требуемых 2% / 5%. Остальные зарегистрированные численные ограничения выдержаны, но это не основание продвижения. Validation и final-test payload не открывались. Алгоритм и параметры после измерений не менялись.

## 1. Идентичность исходников, исполнение и публикация

Baseline R4: `e3b0c9c039d2953fbfcda51231263d38ef9f1024`, tree `eae49a504bc59b5c9b408445150bef32e111956f`. Весь пользовательский ZIP проверен встроенным stdlib verifier: 301 файл, все пути/байты/executable bits, не только несколько ключевых файлов. SHA256 ZIP `a8e0bfa033e0a02c460c30b02f34a5c64ece85b05003512941387d3cf1f319a2`. Полный SOURCE_RECEIPT находится в переданном evidence; remote commit->tree отдельно проверен GitHub read. Архив не содержит .git и DB.

PLAN опубликован ДО foundation и candidate accuracy: `fe660c212020f7a99cc45d1598da4041a2ac92e3`. Ветка `research/R4-H40` создана от pinned baseline после проверки точного ID. Main, чужие ветки, старые отчёты, historical guards не менялись; merge/force-push/auto-merge нет.

**Фактически измеренный SHA — ЛОКАЛЬНЫЙ Git commit `b8343382bb4c5757e135d24837cf1b8f7dab7925`.** Его родитель — честный локальный snapshot `2ce1894b4e688c4d5f273a36c4971096a5d801de`, чей tree совпадает с remote baseline. Это НЕ история удалённого e3b0c9c и не pretend remote commit. Оба локальных коммита полностью сохранены в `R4-H40-local-source.bundle`; commit кандидата сделан до его accuracy replay.

**Опубликованный эквивалент программного кода — remote `1708f2a21d8a5addade48a3be664943ce385e61c`.** У восьми файлов PLAN/pins/loader/diagnostic/factory/runner/tests Git blob SHA совпали с локальным измеренным исходником. Шесть вспомогательных файлов полного receipt/foundation/math остаются в bundle/evidence. Не заявляется равенство полных local/remote trees: ancestry, служебный workflow и расположение evidence различаются. Baseline canonical src везде неизменён.

Компактный численный checkpoint: `690180d042d03071c521d9162b2de8fe21ee41bd`, ветка `checkpoint/R4-H40-local-b8343382-20260926`. Он содержит код, METRICS.json и все clean receiver-сравнения; полные 237 paired cases находятся в evidence ZIP, не выдаются за целиком загруженные в GitHub. Отчётный commit — отдельный от измеренного. Поле report_sha в финальном SUMMARY задаётся после создания этого коммита.

## 2. Основание и один кандидат

Предположение: гладкое tanh-сопротивление стремится к нулю при v->0 и может удерживать model-only creep. До candidate зафиксирован potential gate: 0<|v_prev|<=0.5 м/с, baseline mode MODEL_ONLY, разница двух прогнозов из одного pre-state >=1e-4 м/с; >=100 тактов, >=3 группы по >=20 тактов, >=5 source-секунд. Это диагностика потенциального воздействия, не доказательство ошибки относительно истины.

На всех 17 development bags / 7 группах, только vehicle topics: 319835 тактов; 8233 near-zero MODEL_ONLY; 7213 potential ticks, 360.65 суммарных секунд, 6271 короткий contiguous episode, максимальная разница прогноза 0.002629144539 м/с. Все 7 групп прошли минимум20. **7187 потенциальных тактов — обычные duplicate-only prediction ticks; только26 — missing/rejected-wheel.** Поэтому естественное outage-покрытие слабое. 3802 held-zero proxy ticks не являются независимой разметкой остановки. Диагностический baseline и отдельный canonical observer дали одинаковые массивы и counters на всех17 bags.

Никакого fitting: один вариант, старое r0=rolling_force/mass, прежний drive update, прежняя формула обучения disturbance и её smooth resistance сохранены. Quadratic drag берётся явно по старой скорости. Перед ограничениями:

```text
A = drive_a + disturbance - quadratic_drag * v_prev * abs(v_prev) / mass
v_free = v_prev + dt*A
v_prox = sign(v_free) * max(abs(v_free) - dt*r0, 0)
```

Вычисление ускорения piecewise избегает `(v_prox-v_prev)/dt` с катастрофическим вычитанием при tiny dt. Сохранены max acceleration/speed и исходный sign guard. В частной копии core заменена только prediction-формула; в частной копии readout восстановление pre-correction acceleration использует тот же helper. Readout gain/holdoff/recurrence, covariance, wheel raw checks, stop history/dwell, zero-lock, H11 quarantine, recovery, Timeline и default не менялись. Это НЕ H09: PR24 прочитан как отрицательный результат изменения stop-history; его патч не перенесён.

`factory.candidate(True)` реально включает `CoulombObserver`; `candidate(False)` сохраняет точную старую арифметику. Модельная v=0 не объявляет STOPPED. Интеграл core плюс readout correction согласован с возвращаемой скоростью; нет заднего переякоривания. В runtime только controller/front/rear, один дополнительный boolean, stdlib; NumPy/SciPy нужны лишь offline. Checkout или hook-patch сам по себе не включает H40 в штатной ROS node.

## 3. Данные и неизменный измеритель

Локальный downloader завершился DNS-ошибкой. Авторизованный data-only Actions run [36230771664](https://github.com/jabrailkhalil/hack/actions/runs/36230771664) завершился success и выгрузил только17 development DB. SHA256 organizer ZIP проверен в Actions, все17 DB SHA и role membership повторно проверены локально. Artifact10902413604: SHA256 `f3cf71908c68c341684012a5df3ec579698a0979e7dd36a1041b70b5f017600b`, retention до 2026-09-27 08:46:33 UTC. Train/validation/test DB не распаковывались и не читались. Accuracy выполнялась ЛОКАЛЬНО, не в этом Actions run.

Baseline — полный GuardedReadoutObserver / champion_v8.yaml: gain1/holdoff.5, adaptation_tau.5, quarantine1.5, inner wheel_time_compensation0, 20 Hz/delay0. Реально считаются возвращаемые Estimate.v/s. Неизменны evaluate.replay/score, matching, reference masks, original fault placement, v6 summary/decide. Технические legacy aliases v4/v5/baseline_v2 внутри scorer обозначают настоящий v8, а не старые модели; исходные численные функции не переписаны.

Все17 bags/7 исходных групп: clean reference в6 группах/19 receiver-парах, 394221 matched samples;15 missing receiver-пар сохраняются N/A. Original56 сценариев/60 receiver comparisons; отдельно low-speed26/34 и H11 common28/30. Для КАЖДОЙ из110 инъекций дополнительно выполнен полный faulted-bag replay baseline/candidate, а исходное cropped scoring сохранено отдельно. Итого237 paired cases:17 clean+110 cropped+110 full. Два receivers не независимые поездки.

Baseline clean/fault/pooled/distance/samples точно воспроизвёл все5 ожидаемых fingerprints. Source/schedule/mask hashes сохранены. Два пакетных вызова оборвались по тайм-аутам45/200s; завершённые bags сохранены, незавершённые повторены тем же source без подбора. RESUME.json фиксирует continuation; ни один готовый bag не перезаписан. Это инфраструктурное продолжение, не новые варианты. Один процент в GitHub CSV исправлен отдельным commit как опечатка переноса; raw local результаты и решения не менялись.

## 4. Измеренные результаты development

Минус в delta ошибки означает улучшение. Значения без округления — [METRICS.json](METRICS.json), все clean pairs включая missing — [clean_comparison.csv](clean_comparison.csv).

| Основная метрика | v8 | H40 | Delta ошибки |
|---|---:|---:|---:|
| Clean group-macro RMSE, м/с | 0.092668142983 | 0.092629978890 | -0.0411836% |
| Original fault-event macro RMSE, м/с | 0.237548612056 | 0.236380263074 | -0.4918357% |
| Pooled clean RMSE, м/с | 0.129305694477 | 0.129294631608 | -0.0085556% |
| Scalar-span distance RMSE, м | 5.310295004801 | 5.293085461540 | -0.3240789% |
| Clean macro MAE, м/с | 0.034933352905 | 0.034897201675 | уменьшение |
| Clean macro p95, м/с | 0.090092790092 | 0.089999440497 | уменьшение |
| Clean signed macro bias, м/с | +0.006390677420 | +0.006293970259 | ближе к нулю |
| Original fault+recovery macro MAE, м/с | 0.153796529331 | 0.152830802625 | уменьшение |
| Original fault+recovery signed bias, м/с | +0.011170307852 | +0.012058897628 | дальше от нуля |

**GAIN FAIL:** недостаточно >=2% clean ИЛИ >=5% original fault. Все остальные запрограммированные пороги выдержаны, но общая accuracy_contract_passed=false. Нельзя продвигать по distance gain или малому fault gain вместо исходного контракта.

| Дополнительная проверка | v8 | H40 | Delta |
|---|---:|---:|---:|
| Low-speed event RMSE, м/с | 0.368545673306 | 0.368545990861 | +0.0000862% |
| H11 common-mode event RMSE, м/с | 0.100632272301 | 0.100632272601 | +0.000000298% |
| Slow-roll proxy RMSE, м/с | 0.062544834324 | 0.062821539282 | **+0.442411%** |
| Start proxy RMSE, м/с | 0.063568913489 | 0.063799642672 | **+0.362959%** |
| Braking proxy RMSE, м/с | 0.142724591270 | 0.142727344055 | +0.001929% |
| Coast proxy RMSE, м/с | 0.088885523903 | 0.088773943906 | -0.125532% |

Slow-roll/start masks выбраны до измерения из baseline vehicle signals; reference только оценивает ошибку на маске. В обоих случаях6 групп,9534/10477 receiver-samples. Start здесь означает низкоскоростную тягу, НЕ отдельное измерение задержки первого движения. Независимых stop/start labels нет.

### Разрез исходных групп

| Group | Clean delta | Original fault delta |
|---|---:|---:|
| 8269991eafa82c45 | -0.137954% | -1.391693% |
| 664cca45aeb0db23 | N/A | N/A |
| 711abb923942f9fe | -0.038996% | практически0 |
| 2cd82bc27dbad052 | -0.646323% | N/A |
| a8a4c11ebcc1dde2 | **+0.002352%** | практически0 |
| 70bb14d1c90f301f | -0.015479% | практически0 |
| a0c46036cc19092a | -0.006940% | -0.0000033% |

Основной fault-выигрыш сосредоточен в одной группе, не воспроизводится широко по поездкам. Нет bootstrap коррелированных ticks и заявления статистической значимости. Полные абсолютные per-group показатели есть в переданном CSV/evidence.

### Локальные регрессии, recovery и нулевая скорость

Clean:13 пар лучше,4 хуже,2 равны. Original event:15 лучше,23 хуже,22 равны. Worst clean RMSE `30618_27e994fc/rover`:0.159096258010->0.159102285643 м/с (+0.0037887%). Worst original event `30618_073f08d1/rover`, dropout10s:1.656541483389->1.656555718555 м/с (+0.0008593%). Это небольшие, но реальные ухудшения.

Новых individual unrecovered нет: original4->4, low-speed6->6, common2->2. Original recovery4 receiver-cases быстрее,52 без изменения,4 старых None; замедлений нет. У `30618_0652866c` dropout10s оба receiver recovery1.256544646->0.006544646s (-1.25s). У `30618_27e994fc/rover` bias5s/dropout5s -0.05s. Два receiver одного bag не два независимых события.

False STOPPED при reference>1:0->0. Clean low-speed STOPPED proxy238->238. **Нулевая опубликованная v при reference0.07..0.5:259->269**, то есть10 дополнительных receiver-samples в3 bags/4receiver-парах. Это не дополнительные STOPPED-флаги, но нежелательное подавление движения по данному прокси. Этот счётчик сохранён как диагностика; задним числом новый admission-порог не добавлялся. Нельзя писать «низкоскоростные свойства не ухудшились».

## 5. Полная дистанция и остаток после восстановления

| Full-faulted-bag scalar distance macro RMSE, м | v8 | H40 | Delta |
|---|---:|---:|---:|
| Original suite | 6.269376947281 | 6.246846724160 | -0.359369% |
| Low-speed suite | 6.938977341728 | 6.920511767841 | -0.266114% |
| Common-mode suite | 6.357699297648 | 6.336576471424 | -0.332240% |

Агрегаты лучше, но локальная полная дистанция `30618_073f08d1/master`, low lock3s:0.225081726125->0.227521780579m (**+1.084075%**). Порог1% задан для aggregate, не переопределялся per-case. На clean `30639_0ab96c59/master` distance0.110114683798->0.113446736082m (+3.026% примерно); меньшая speed RMSE не означает лучшую distance во всех bags.

Наибольший |delta_s конца bag|: original dropout10s `30618_0652866c`: +0.623796747m. На выходе fault +0.315539333m, через10s +0.718002713m, в момент baseline confirmed recovery +0.712805236m. **Это candidate-minus-baseline, не ground-truth позиционная ошибка.** Остаток не обнулён ради результата. Соответствующая full-span error master уменьшилась0.426354646->0.383323004m. Все signed residuals по237 cases/raw full cases доступны в evidence; позиции reference не используются алгоритмом.

В80/110 full-faulted cases baseline |d|>=r0 на старте отказа. Это модельный load proxy, не независимое измерение нагрузки. Неоднозначность нагрузок и ground-truth остановки остаётся. Scalar span metric использует прежний интеграл GNSS-speed и reanchored scoring spans, не независимую XY/ENU траекторию и не перепривязку состояния H40.

## 6. Sanity, аудит и ресурсы

Локально до данных пройдены156 baseline unit +43integrity; после реализации25 H40 tests и compileall. После измерений те же156+43+25 повторно PASS. Не складываем повторения в число уникальных тестов. Включённые tests:10k независимых soft-threshold oracle случаев; energy только zero-force/zero-quadratic toy, обе стороны, below/above r0, tiny dt; sign/bounds, zero-model-not-STOPPED, dwell, slow roll/start/brake, low-speed lock и H11; prefix/duplicate/stale/future/reset; fixed state; интеграл опубликованной v и точное совпадение acceleration helper core/readout.

Feature-off точен по всем исходным полям состояния и Estimate на395043 ticks17clean+110cropped. Baseline массивы всех17bags совпали с независимой foundation. Во всех237 paired cases causal errors/resets/drop=0, catchups до2 на case одинаковы у обоих. Выходная сетка и matching counts идентичны. 13108 near-zero same-state changed predictions по7группам и35405 материально изменённых outputs (>1e-9) подтверждают активность механизма; не только вызов функции.

Аудит после результата:301/301baseline bytes,14/14research source hashes, точный пересчёт summaries/decisions, full patch apply/check и14/14файлов после применения. Candidate-source commit до accuracy; никаких новых вариантов по результатам. Первый `git bundle create` с rawSHA не сформировал bundle; исправлено на HEAD, bundle verify PASS. Это упаковка, не изменение эксперимента.

Wolfram реально вызван дважды. Первое energy-неравенство осталось unsimplified (не названо доказанным); отдельный case split затем дал True для положительного sliding, отрицательного sliding, sticking и покрытия всех случаев. No reversal/rest-threshold/continuity/zero-step checks подтверждены в toy assumptions. Abbreviated worksheet и фактические outputs сохранены в source bundle/evidence. Это не full nonlinear stability proof. Внешняя публикация не выдумывалась; Consensus/Scite после известных quota stops не дёргались.

Стоимость на одном development-bag: warmup1 пара +6AB/BA, threads1, одинаковые collectors. Медианный paired overhead: **step CPU+6.874166%, replay CPU+4.949410%, wall+4.940343%**. Медианы step26.5673->28.3908мкс; replay CPU1.183978->1.243195s. Это offline Python cost, не установленная ROS latency/RSS.

**Enabled installed ROS, оба clock modes,2CPU/500000000bytes: NOT_RUN_AFTER_REJECTION.** Стандартный feature-off CI не присваивается кандидату; новый независимый final test отсутствует. Validation не расходован, freeze=N/A из-за отказа development. Состояние исследования завершено отрицательным выводом, а не блокировкой данных или публикации.

## 7. Evidence и воспроизведение

В GitHub сохранены читаемые необходимые программы/PLAN/pins/tests, этот отчёт, METRICS и clean CSV. Пользователю отдельно передан **полный immutable measurement package `R4-H40-evidence.zip`**:3828057bytes, SHA256 `44e5552cdcaf8b52ab033ce7c38b789b7bd91d58498296142b3aa288853ba661`. Это attachment ответа, не фиктивный Actions artifact. Внутри все per-bag/per-fault JSON, access/hash manifests, foundation, derived per-group/per-receiver/full-distance/recovery CSV, COST, logs, точные14sourcefiles, полный source.bundle и patch. Сырые DB и секреты не включены. Срок хранения attachment определяется средой чата; отдельного GitHub retention для него не заявляем.

`R4-H40-local-source.bundle`:SHA256 `c164b18bc50c4fc26f0dacd0d1c0927073183b302652a8af92c2a648b523d838`.
`R4-H40-research.patch`:SHA256 `a6c8a7ed138783faffac454c146ecbcbd09fcb47908df699f1dc4c795fafebe2`.
Полный per-bag CSV:SHA256 `b5855c625e86944c738e658e8ee00b6743f4ad92dd6e6cffe1aac37d5680da6e`.
Full-faulted-distance CSV:SHA256 `a5172210bef238f9de84bafb12dd7e76e8caf8c4f917bd748a0ffb65d16a6686`.

Из полного remote checkout опубликованного программного эквивалента:

```bash
git checkout 1708f2a21d8a5addade48a3be664943ce385e61c
python -m pip install -r requirements-research.txt
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
export H40_SOURCE_SHA=$(git rev-parse HEAD)
PYTHONPATH=src/reserve_odometry python -m unittest discover -s tests -v
python -m unittest discover -s research/tests -v
python -m unittest discover -s research/R4/H40/tests -v
python research/R4/H40/stage_data.py --stage development --journal /tmp/H40-stage-new.json
python research/R4/H40/diagnose.py --output /tmp/H40-foundation-new --workers 2
python research/R4/H40/run.py --stage development --foundation /tmp/H40-foundation-new/FOUNDATION.json --output /tmp/H40-results-new --workers 2
python research/R4/H40/run.py --stage summarize --foundation /tmp/H40-foundation-new/FOUNDATION.json --output /tmp/H40-results-new
python research/R4/H40/run.py --stage cost --foundation /tmp/H40-foundation-new/FOUNDATION.json --output /tmp/H40-results-new
```

Для точного оригинального локального Git SHA сначала `git clone R4-H40-local-source.bundle work`, затем checkout b8343382bb4c5757e135d24837cf1b8f7dab7925. Этот SHA не следует искать как коммит remote main. Программные файлы remote эквивалента совпадают, но список вспомогательных файлов в новом source manifest другой; не выдавать его за оригинальный14-file manifest. Все output dirs должны быть новыми; completed bag checkpoints не перезаписывать. При инфраструктурном прерывании продолжить только отсутствующие индексы через --begin/--end либо приложенный continuation helper. Validation/test stages в driver отсутствуют.

**Итог:** конкретный единственный H40 отвергнут по insufficient_gain. Небольшой средний выигрыш не компенсирует недостаточную величину улучшения, ухудшение slow-roll/start прокси и неустановленную переносимость на реальные нагрузки. Не для merge.
