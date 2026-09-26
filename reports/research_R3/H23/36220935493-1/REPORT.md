# R3-H23 — REJECTED на development

**Исследовательский артефакт, не готов к merge.** Единственный кандидат `H23_B_outage_5s_v1` реализован и активен, но original fault-event group-macro RMSE вырос **на 2.603593%**, low-speed lock event RMSE — **на 1.803096%**. Оба превышают соответствующий предел 0.5%; требуемого 2% clean / 5% original fault gain нет. Validation **не открывался**, FREEZE не создавался. Пороги не менялись.

```json
{
  "mechanism_status": "ACTIVE",
  "coverage_status": "SUFFICIENT",
  "scientific_verdict": "REJECTED",
  "accuracy_contract_passed": false,
  "runtime_verified": false,
  "ready_to_merge": false,
  "validation_evaluated": false,
  "freeze_sha": null,
  "enabled_ros": "NOT_RUN_AFTER_REJECTION"
}
```

Это отрицательный результат конкретного варианта, не опровержение любого outage-only применения иной физики.

## Идентичность

| Назначение | SHA |
|---|---|
| Baseline R3, canonical v8 | `e3b0c9c039d2953fbfcda51231263d38ef9f1024` |
| Успешная baseline-only диагностика | `f81958cd8d494709000e5a2414d4c7807c370908` |
| PLAN до реализации и сравнения | `ff1e8cb71e816019a90b8b1e7a3fdec90a7a8e74` |
| **Измеренные алгоритм, runner, tests, READY** | **`39536cfe973bbdde5f9b4491f4c7e20d247caed0`** |
| Компактный checkpoint результата | `71bfff01606406e465e49158862157b39c477764` |
| Freeze | Не создан: development gate не пройден |

Ветка `research/R3-H23` создана от согласованного SHA. Baseline — полный `GuardedReadoutObserver`, `champion_v8.yaml`: 20 Hz, delay 0, readout gain 1 / holdoff 0.5, adaptation tau 0.5, wheel-time compensation 0, common-mode quarantine 1.5. Сравниваются возвращаемые `Estimate.v/s`. Alias `baseline_v2` в JSON означает **этот v8**, `balanced_physics` — H23.

[Основной run 36220935493/1](https://github.com/jabrailkhalil/hack/actions/runs/36220935493) завершён success 26.09.2026: это успешное исполнение отрицательного эксперимента. Данный REPORT — поздний отдельный report commit, а не новый алгоритм; его SHA указан в PR. Присланный `hack-main-2(1).zip` сопоставлен с закреплённым baseline: **301 файл совпал побайтно**, различий/пропусков среди проверенных нет. `.db3` в архиве нет; реальные данные исполнялись в Actions.

## Предварительная проверка основания

[Preflight 36220190631/1](https://github.com/jabrailkhalil/hack/actions/runs/36220190631) исполнил только v8 на всех 17 development-bag: 73 clean/original replay, 7 групп. B-rollout и validation не выполнялись. На естественных gaps: 439 потенциально затрагиваемых ticks / 212 коротких фрагментов в 7 группах, 435 ticks допускают offset. В original fault-окнах: 4892 ticks /44 фрагмента в 6 группах, все offset допустимы. Baseline RMSE на этих диагностических eligible-масках: 0.0770744844 clean и 0.2929503810 м/с fault. Это не критерии отбора или доказательство полезного вмешательства.

Максимальный clean |d_offset|=0.6471226281 превышает limit 0.6: fallback нужен. Первый preflight 36219993218 остановился на `KeyError: mae` у записи без reference. Исправлена только проверка присутствия/равенства optional-полей, не scorer или маска; журнал сохранён, повтор получил новый run ID.

Полный fingerprint baseline clean/original metrics и runtime в основном исследовании **точно совпал** с независимым preflight:
`bb02a7fb46bdc2a01b3cd106ba3f9b1cd2c5f8e507c01e22a80d533867b19d2d`.

## Реальное изменение алгоритма

Canonical v8 продолжает работать без обратной связи от H23. Дополнительно существует один model-only state `(v_B, drive_B, d_B)`, не второй wheel filter. До первого outage полный здоровый Estimate совпадает с v8. Последний доверенный момент — stamp нового `ACCEPTED` wheel sample, не callback или повтор held.

Вход: более `max_age_s=0.25` без доверенной коррекции, `MODEL_ONLY`, валидная команда, допустимые missing/old/zero-lock статусы, отсутствие quarantine, модельная скорость выше stop threshold. При ambiguity и недоверенных свежих аномалиях вход запрещён. На старте `v_B=v8.inner.v`, `drive_B=v8.inner.drive_a`, `a0=drive_A-resistance_A(v0)+d_A`, `d_B=a0-drive_B+resistance_B(v0)`. Начальное net acceleration совпадает. При недопустимом d_B или насыщенном a0 остаётся v8; offset не подрезается до удобного значения. Далее B повторяет исходный drive-before-Euler predictor с текущими доступными командами и фиксированным d_B; обучения по испорченным колёсам нет.

Ровно опубликованная B взята из `af5ee198617e5ecb262e78c529cea3581927557b`, `reports/research_R2/H16/H16-36184448864-1/train/B.json`. Полный B сверён с `train/results.json → models.B`. Blob `10d4a161f740b2835a5f395f1dcf7b52a49c06b8`, SHA256 `75e6624d3b9737109bd72c81d9cf26e61d2915d758549424beab6e4ba75f3bbc`. Семь коэффициентов отдельно в `research/R3/H23/H16_B.json`. Выбора A/B и нового train-fit нет; это не новый train-прогон H23.

Горизонт **5 с** — максимальный train-horizon H16. Повторный запуск без нового trusted update запрещён. Выходная поправка ограничена `max_accel*max_age=0.75 м/с`, active slew — `max_accel=3 м/с²`. Единственное release-правило после восстановления/abort: движение к нулю со скоростью `reacquire_step/0.1=1.5 м/с²`. STOPPED и запрет смены знака приоритетны.

`delta_s += 0.5*(delta_v_previous+delta_v_current)*dt`; `s_output=s_v8+delta_s`. **При recovery delta_s не обнуляется.** Только explicit reset начинает новую координатную историю. Выходная a согласована с delta_v; variance envelopes не подаются в v8 и не являются калиброванными CI. Runtime не получает GNSS/IMU, bag ID, injection labels или future samples и не требует новых тяжёлых библиотек.

## Методика и данные

Один prospective development, все **17 bag /7 групп**. Clean reference есть в 6 группах /19 bag-receiver парах; **394221** сопоставленная точка. Семь bag без reference сохранены missing. Два receiver одной записи не считаются независимыми поездками.

Неизменны `evaluate.score/replay`, `ex.match/metrics`, `distance_surrogate`, `guarded.fault_windows`, `v6.summary`; меняется только factory/role adapter. После скачивания artifact дополнительно проверены **57 baseline-файлов и 15 исследовательских файлов**, все хеши совпали.

| Набор | Replay cases | Сравнения с reference |
|---|---:|---:|
| Clean полные записи | 17 | 19 |
| Original bias5/dropout5/dropout10/lock3 | 56 | 60 |
| Те же инъекции на полном bag без crop/reset | 56 | 60 |
| Существующий low-speed lock3/5 selector | 26 | 34 |
| Существующий H11 common +5 м/с, 0.7/1.2 с | 28 | 30 |
| Dropout5, затем ложная общая +2 м/с пара на 1 с | 14 | 15 |

Дополнительные suites не заменяют original gain. Full-faulted-bag distance имеет отдельный предзарегистрированный aggregate veto 1%; delta_s остаётся до конца bag. Original crop и full replay имеют разные собственные начальные состояния, но внутри каждого сравнения baseline и candidate получают одинаковые входы/сетки.

Распакованы только индивидуальные development DB. Access journal содержит только development. Final/test и validation DB не распаковывались/не открывались; нового train-fit нет. После REJECTED шаги FREEZE и validation получили **skipped**, не неизвестный результат.

## Основные результаты development

Положительное изменение означает рост ошибки.

| Показатель | v8 | H23 | Δ |
|---|---:|---:|---:|
| Clean macro RMSE, м/с | 0.092668142983 | 0.092668200225 | +0.000061772% |
| Original fault-event macro RMSE, м/с | 0.237548612056 | 0.243733410460 | **+2.603593%** |
| Pooled clean RMSE, м/с | 0.129305694477 | 0.129305731214 | +0.000028411% |
| Clean scalar-span distance, м | 5.310295004801 | 5.310299050673 | +0.000076189% |
| Matched clean samples | 394221 | 394221 | 0 |
| False stops clean/original | 0/0 | 0/0 | 0 |
| Original unrecovered | 4 | 4 | Нет новых индивидуальных случаев |
| Full-faulted-bag distance, м | 6.269376947281 | 6.317935063601 | **+0.774529%** |

Clean MAE 0.034933352905→0.034933377624 м/с; signed bias 0.006390677420→0.006390704770. Fault+recovery MAE 0.153796529331→0.155589161232; signed bias 0.011170307852→0.028188548648. Recovery group-macro 0.724358284875→0.736858284875 с. Fault MAE/bias используют штатную fault+recovery маску, не event-only.

Машинные veto: **`insufficient_gain`, `aggregate_regression:fault_rmse`, `low_speed:event_regression`**. Clean per-bag gate, coverage, timestamps, causal/reset и individual-unrecovered проверки пройдены, но не компенсируют отсутствие gain и нарушение safety допуска.

| Отдельный набор | Event macro v8 → H23, м/с | Δ | Unrecovered v8/H23 |
|---|---:|---:|---:|
| Low-speed lock | 0.368545673306 → 0.375190906389 | **+1.803096%** | 6/6 |
| Abrupt common-mode | 0.100632272301 → 0.100632272301 | 0% | 2/2 |
| Dropout + ложное recovery | 0.837255157328 → 0.832938865546 | −0.515529% | 1/1 |

False stops в дополнительных suites 0/0; новых individual unrecovered нет. Существующие baseline failures не скрыты. Неизменность H11 suite не доказывает абсолютной защиты от произвольной common-mode ошибки.

## Существенные регрессии и группы

Original event RMSE хуже в **15/60**, low-speed — **27/34**. Шесть original recovery медленнее на 0.1 с. Clean RMSE хуже в 6/19, но максимум всего 4.62518e-7 м/с, в допуске. Full-fault distance хуже в **29/60**.

| Случай | Baseline → H23 | Изменение |
|---|---:|---:|
| 30618_27e994fc/rover, dropout5 | 0.093577275 → 0.310728432 м/с | +0.217151157 м/с; +232.055% |
| 30618_27e994fc/master, dropout5 | 0.089482105 → 0.301821398 м/с | +237.298% |
| 30618_88548b02/master, dropout5 | 0.091524940 → 0.194113036 м/с | +112.088% |
| 30618_0652866c/rover, low-speed lock5 | 0.179493696 → 0.241319767 м/с | +34.445% |
| 30618_27e994fc/rover, false recovery | 0.875029063 → 0.941166071 м/с | +7.558% |
| 30639_9c362687/rover, full-bag dropout10 distance | 19.581277723 → 20.065790513 м | +0.484512790 м; +2.474% |

Original разрез: bias5 **0%**, dropout5 **+5.210461%**, dropout10 **+3.539884%**, lock3 **−1.953980%**. Улучшение lock не заменяет общий gate.

| Исходная группа | Original event RMSE v8 | H23 |
|---|---:|---:|
| 70bb14d1c90f301f | 0.245582235 | 0.230625956 |
| 711abb923942f9fe | 0.125038907 | **0.181644373** |
| 8269991eafa82c45 | 0.419757752 | 0.373378383 |
| a0c46036cc19092a | 0.230681884 | **0.270260798** |
| a8a4c11ebcc1dde2 | 0.166682281 | 0.162757542 |

`2cd82bc27dbad052` имеет только clean reference, `664cca45aeb0db23` не имеет reference. Пропуски не заменены нулями. Все clean/distance/group/receiver/fault поля сохранены в `development/bags/*.json` artifact; производные CSV в анализ-пакете сохраняют missingness.

### Наблюдаемая трасса, не новый подбор

В `30618_27e994fc`, original dropout [190.1,195.1] с, rollout стартует причинно около 190.300 с. B d_offset −0.035101130 при d_v8=0.008713891 м/с². На t=193.000 delta_v=+0.205924971 м/с: ошибки к внешнему rover reference v8 +0.042333550, H23 +0.248258521. На t=195.000 delta_v=+0.433767428: ошибки +0.243693544 и +0.677460972 м/с.

После release delta_v=0, но delta_s **остаётся +0.976950495 м** в cropped replay. В отдельном полном bag после восстановления — около **+1.001276 м**, к концу +1.001299 м с учётом естественных gaps. Скрытого стирания остатка нет. Cropped/full числа не смешиваются: warmup различен. Это post-hoc описание сохранённых трасс, не доказательство единственной причины и не донастройка.

## Активация и проверки

Clean+original: **238 starts**, **3386 active ticks**, **3215 changed outputs** с |delta_v|>1e-6 в **6 исходных группах**, 33 смены класса команды на active ticks. Minimum 10 starts /100 changed /3 groups выполнен. Counts не независимые поездки.

Clean: 179 starts, но только123 changed outputs. Original:59 starts/3092 changed. Abrupt common:7 кратких starts и **0 changed outputs** — совпадение метрик там не выдаётся за улучшение H23. Два clean offset fallback реально сработали.

Actions: **156 legacy +43 research-integrity +21 H23 tests PASS**, compileall PASS. После получения artifact локально повторены21/21 H23 tests,0.447с. Проверены continuity, horizon, bounded release/persistent delta_s, guards/zero-lock/quarantine, future/duplicates/prefix/reset, no wheel training, same-physics limit, healthy/off equality, fixed-size state.

Реальные проверки: **197/197 exact schedules**, **197/197 all-inner-state**, **169/169 feature-off fingerprints/counters**. В28 common cases отдельный off replay не выполнялся, но schedule/inner проверены. Всего **1,674,237 потактовых сравнений ВСЕХ inner fields**, включая canonical last_estimate. Максимальная ошибка независимой trapezoid identity **4.490852134608758e-13 м**. Causal/reset ошибок нет.

Extra state — фиксированные slots/scalars и один rollout, без растущих историй. Offline shadow observer/collector не входят в runtime candidate.

## Вычислительная стоимость

Development bag `30618_0652866c`; отдельный warmup отброшен, четыре пары **AB/BA/AB/BA**, OMP/OpenBLAS threads=1, одинаковые collectors. Фазовые маски взяты по H23, ticks одинаковые у обоих. Timer overhead включён одинаково.

| Медиана | v8 | H23 | Δ |
|---|---:|---:|---:|
| Natural DORMANT step CPU, мкс,29282 ticks | 33.099271 | 39.016994 | **+17.878709%** |
| ACTIVE step CPU, мкс,2721 engineered-outage ticks | 23.309475 | 40.709053 | **+74.645945%** |
| Natural replay CPU, с,29207 outputs | 1.436027762 | 1.598118330 | **+11.287426%** |
| Natural replay wall, с | 1.436170679 | 1.598243765 | **+11.285085%** |

Step stream содержит29287 ticks с pre-initialization; official replay —29207 outputs. На естественном потоке только5 ACTIVE ticks, недостаточно для уверенной active cost: использован заранее объявленный engineered-outage поток, не новый accuracy benchmark. Нельзя сравнивать разные фазы как одну workload.

Offline timing не ROS latency/RSS. **Installed ENABLED H23 ROS в двух clock modes, offline2CPU/500000000B: NOT_RUN_AFTER_REJECTION.** Ordinary CI36220935498 имеет4 successful jobs, но canonical launch не включает H23; эти runtime результаты не приписываются кандидату.

## Источники и ограничения

Прочитаны заданные H16 и обе H18 работы: их числа относятся к R2/v7, не R3/v8. Farina/Piroddi DOI10.1002/acs.1203:metadata/abstract, не fulltext; основание multi-step loss, не доказательство H23. Известные quota stops Consensus/Scite не обходились; новых вызовов к ограниченным сервисам нет. См. `research/R3/H23/SOURCES.md`.

Фактический Wolfram worksheet/output проверяет acceleration continuity, нулевой outage-предел, локальный O(dt²) first-step delta, trapezoid identity и ненулевую площадь release. Предпосылки: конечность, отсутствие saturation/sign reversal в локальном выводе. Не доказаны глобальная nonlinear switched stability, calibrated uncertainty или real-data accuracy.

B обучалась со своей warmup-динамикой, здесь стартует из v8 с offset: прежний выигрыш не обязан переноситься. Arbitrary common-mode error неоднозначна. Distance — штатный переякоренный scalar speed-integral surrogate, не XYZ/ENU/полный terminal drift. Независимого final-test доказательства нет; R3 validation не открывался. После development параметры не менялись.

## Воспроизведение

Из существующего клона, новый output:

```bash
set -euo pipefail
git fetch origin research/R3-H23
git worktree add --detach ../hack-H23-reproduce 39536cfe973bbdde5f9b4491f4c7e20d247caed0
cd ../hack-H23-reproduce
python3.13 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-research.txt
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
export GITHUB_SHA=39536cfe973bbdde5f9b4491f4c7e20d247caed0
OUT="$(mktemp -d /tmp/H23-reproduce-XXXXXX)"
PYTHONPATH=src/reserve_odometry python -m unittest discover -s tests -v
python -m unittest discover -s research/tests -v
python research/R3/H23/test_h23.py
python research/R3/H23/prepare_data.py --roles development --journal "$OUT/extraction.json"
python research/R3/H23/run.py --stage development --output "$OUT/development"
python research/R3/H23/cost.py --output "$OUT/cost"
# FREEZE / validation НЕ запускать после REJECTED.
```

Checkout содержит исследовательский модуль, но **не переключает canonical launch**. Factory: `OutagePhysicsObserver(config_v8, config_B, readout=ReadoutConfig(gain=1,holdoff_s=.5), enabled=True)`. Минимальный standalone patch добавляет модуль/B JSON в research/R3/H23; git apply проверен на чистом baseline. Patch SHA256 `5dd96d8e80f6fc0d5a5da791abf22fb3d38143a7c810638944bc723f961e5745`; module SHA256 `085136febe1e66f4a2ce160678b875387cfe0cc7beec7e6e418c93c50bfce85f` совпадает с измеренным.

[Компактный checkpoint, SUMMARY и полный SHA256 manifest](https://github.com/jabrailkhalil/hack/tree/71bfff01606406e465e49158862157b39c477764/reports/research_R3/H23/36220935493-1). Raw per-bag JSON, compressed traces, access/extraction, source/PLAN/READY, tests/cost: artifact **R3-H23-36220935493-1**, ID**10899318401**, ZIP SHA256 **a37b9a2d8e468ea60a3b8a494d8db90aee32254a4eca0bc92f4d33c9d1273eca**, retention30дней до26.10.2026. ZIP дополнительно проверен по digest. В Git нет сырых bags или больших trace-дубликатов; производные CSV и saved-results analyzer передаются отдельно без нового replay.

**H23_B_outage_5s_v1 не продвигать.** Main, чужие ветки, прежние отчёты/релизы и dataset не изменены. Merge/auto-merge не выполнялись.
