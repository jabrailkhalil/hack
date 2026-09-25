# R2-H14 — INCONCLUSIVE: нет естественного покрытия асинхронной адаптации

**Исследовательский артефакт, не готов к merge.** Статус исследования — **INCONCLUSIVE** по заранее объявленному activation gate. Численный допуск проверенного кандидата **не пройден** (`eligible=false`, `insufficient_gain`): выигрыш 0%. Это не подтверждение полезности и не опровержение всего семейства асинхронной адаптации. На естественных development timestamps механизм не сформировал ни одной доверенной асинхронной пары. Validation не открывался; отдельный validation-freeze не создавался, поскольку допуск к этому этапу отсутствовал. Параметры после результатов не менялись.

## Идентификаторы и границы

| Артефакт | Идентификатор |
|---|---|
| Round | `R2-v7-fixed` |
| Общий baseline | `65bba39ed05c781f3f69a65c02f69931152cbfd9` |
| PLAN до первого эксперимента | `a012d7a7d7596280bcff73c0a85e6bc8cd14bea6` |
| Измеренный алгоритм, driver, tests | `8847307321e9336a9c3a5735ad25d76b635a801b` |
| Ветка исследования | `research/round2-H14` |
| Фактический run / attempt | `36184182027 / 1` |
| Оригинальный checkpoint | `9ea335767b5348158133bcd1984f620c18c624c4` |

[Research run](https://github.com/jabrailkhalil/hack/actions/runs/36184182027) / [неизменяемый оригинальный evidence](https://github.com/jabrailkhalil/hack/tree/9ea335767b5348158133bcd1984f620c18c624c4/reports/research_R2/H14/36184182027-1). Более поздний commit данного отчета копирует исходное дерево evidence и добавляет только отчет/пост-анализ; алгоритм не меняет. Main, чужие ветки, прошлые отчеты и checkpoint не переписаны. Merge, auto-merge и force-push не выполнялись.

Baseline — реальный **GuardedReadoutObserver**, canonical `guarded_readout_v7.yaml` / `odometry.launch.py` / `guarded_odometry_node`. Вычисляются **возвращаемые Estimate.v/s**, не внутренние observer.v/s. Параметры фактически проверены: rate=20 Hz, intentional delay=0 s, readout gain=1 / holdoff=0.5 s, inner wheel_time_compensation=0, adaptation_tau=0.5 s. H11/v8 и изменившийся main не включены. Старые v5/R1 метрики не использованы вместо исполнения R2.

## Реальное изменение алгоритма

`AsyncAdaptationObserver` наследует GuardedReadoutObserver. Минимальный core patch лишь выделяет прежний блок adaptation в переопределяемый метод, сохраняя старую формулу. Отдельный pending-поток содержит максимум один **новый уже ACCEPTED** sample front и rear. При завершении пары заново проверяются возраст, skew, agreement, диапазон, innovation gate и zero-lock. Каждая пара потребляется один раз, ее среднее время строго возрастает. Hard rejection, stale controller, reset и разрыв доверенной истории очищают буфер/derivative history.

После принятия пары вызывается исходная measured_a/EMA-формула с прежними tau и disturbance clipping. Нет второй коррекции скорости или ковариации, нет R/N, проекции wheel speed, новой физики, recovery/stop/readout/Timeline изменений. H13 не реализуется. Память ограничена: два pending samples, фиксированные скаляры/метки и семь saturating diagnostic counters. Только controller/front/rear; никаких GNSS/IMU/bag IDs/fault flags/future samples в Observer. Флаг enabled — конфигурация эксперимента, не oracle-вход.

**Сам checkout не включает H14.** Требуется `git apply research/R2_H14/adaptation-hook.patch`, затем factory `AsyncAdaptationObserver(config, readout=ReadoutConfig(gain=1.0, holdoff_s=0.5), enabled=True)`. Research driver делает именно это после применения patch. Без hook конструктор H14 отказывает, а не молча исполняет baseline. Canonical ROS launch в этой ветке по-прежнему запускает v7; enabled ROS integration/benchmark не заявляется. Отключение H14 делегирует точной исходной формуле.

## Протокол, роли и неизменный измеритель

Проверен **один** априорный кандидат без подбора численных параметров. Train — только первые 180 s первого разрешенного bag `30618_0259fe53`: 7137 событий, 3520 outputs на модель, reference_used=false. Это smoke/invariants, не точность. Train GNSS не читается.

Затем обработаны **все 17 development-bag / 7 исходных групп** настоящей frozen development роли, без выбора хороших записей. Reference доступен в 6 группах / 19 bag-receiver парах. Семь bags не имеют reference; еще в одном отсутствует master. Missing сохраняется как null, не ноль. Исходный vehicle-anchor допускает 56 fault-сценариев и 60 event/receiver сравнений с reference: front bias +5 m/s на 5 s, dropout обоих 5/10 s, zero-lock 3 s. Пропуск неподходящих anchors — прежнее правило, не фильтрация по ошибке H14.

Исполнены неизменные `evaluate.score/replay`, `experiment.match/metrics`, scalar distance, `research_v6.summary` и оригинальное fault placement. Подставляется только factory Observer. Read-only development loader проверяет role/membership **до SQLite IO**, повторяет исходные decoding/scaling/query. Все source timestamps, reference masks, сетка и правила групповой агрегации одинаковы. Оба receivers сохраняются, но не считаются независимыми поездками. Старые pins/evaluator не переписаны: отдельный manifest сравнивает 12 ключевых baseline/evaluator файлов побайтно, а applied core — с baseline+явным patch.

Четыре исполняемых варианта — pristine canonical v7, H14 on, H14 off и v7 с выделенным hook. Baseline не считается поисковым вариантом. На каждом clean/fault replay off и hook дали **точно одинаковые output arrays и runtime counters с независимо загруженным pristine v7**; original score проверяет одинаковое расписание и для H14 on. Пост-аудит 1158 общих top-level receiver metric entries (включая вложенные distance values) и всех runtime dictionaries H14 on/base нашел ноль расхождений. Это проверка сохраненных результатов, не новый прогон.

Access journal: 1 train + 35 development загрузок (17 основное сравнение, 1 cost, 17 отдельная availability-диагностика); никаких validation/test SQLite-загрузок. Штатный downloader распаковал checksum-pinned общий ZIP, но test measurement records загрузчиком не декодировались и final test не пересчитывался. Исторические integrity tests проверяют сохраненные архивы/манифесты, не новые final-test измерения.

## Почему validation остановлен

Предварительный минимум: >=100 натуральных async-пар, >=50 async EMA updates, >=2 development groups с такими updates, >=5 s healthy времени без FUSED.

| Проверка | Фактически | Порог |
|---|---:|---:|
| Доверенные асинхронные пары | **0** | 100 |
| Async adaptation updates | **0** | 50 |
| Группы с async updates | **0** | 2 |
| Healthy время вне FUSED | 5965.2 s | 5 s |

Последняя строка **не компенсирует** первые три. 53.936% healthy времени вне FUSED включает штатные prediction-only ticks, а не только асинхронные корректные колеса. Всего на clean записано 248 SINGLE_WHEEL output ticks, но доверенных async-пар не образовано. H14 обработал 147929 синхронных пар и 93826 обычных derivative/EMA updates; новых async updates также нет во всех исходных fault-окнах. Это не неисполненный класс: его синхронный путь работал, а отдельные диагностические потоки активируют асинхронный.

По PLAN: **INCONCLUSIVE по механизму и отсутствие допуска кандидата**, validation НЕ запускается. Набор не заменяется искусственно сдвинутым ради admission, бюджет не расширяется, пороги не смягчаются. Новый независимый final test отсутствует.

## Результаты на естественном development

| Метрика | v7 baseline | H14 | Абсолютная / относительная дельта |
|---|---:|---:|---:|
| Clean group-macro RMSE, m/s | 0.092668142983 | 0.092668142983 | 0 / 0% |
| Original fault-event group-macro RMSE, m/s | 0.237548612056 | 0.237548612056 | 0 / 0% |
| Pooled clean RMSE, m/s | 0.129305694477 | 0.129305694477 | 0 / 0% |
| Scalar-span distance RMSE, m | 5.310295004801 | 5.310295004801 | 0 / 0% |
| Clean group-macro MAE, m/s | 0.034933352905 | 0.034933352905 | 0 / 0% |
| Clean group-macro signed bias, m/s | +0.006390677420 | +0.006390677420 | 0 / 0% |
| Fault-window group-macro MAE, m/s | 0.153796529331 | 0.153796529331 | 0 / 0% |
| Fault-window group-macro signed bias, m/s | +0.011170307852 | +0.011170307852 | 0 / 0% |
| Recovery group-macro, s (только определенные значения) | 0.724358284875 | 0.724358284875 | 0 / 0% |
| Сопоставленные clean points | 394221 | 394221 | 0 |
| False stops, clean / fault | 0 / 0 | 0 / 0 | 0 |
| Неподтвержденные recovery cases | 4 | 4 | 0 новых |

Четыре прежних unrecovered случая — `30639_e4379d7f/rover`, все четыре original faults; они не скрыты средним recovery. Их причина данным аудитом не устанавливалась. Рост ошибки/дистанции, ухудшение recovery, потеря coverage и новые false stops в сохраненных per-bag результатах **не обнаружены**. Нет causal errors или неожиданных resets.

Общий численный контракт не изменен: >=2% clean gain ИЛИ >=5% original fault gain; clean/fault/pooled regression <=0.5%, distance<=1%, per-bag baseline+max(0.005 m/s,5%), без safety/coverage regression. Проверенный кандидат **не прошел gain criterion**; неактивность целевого режима не дает оснований принимать его как улучшение.

### Все clean bag/receiver RMSE

В каждой численной ячейке **baseline и H14 совпадают**; N/A — отсутствие reference. Полный CSV содержит отдельные строки каждой модели, MAE/bias/distance и все fault/recovery результаты.

| Bag | Master RMSE, m/s: baseline = H14 | Rover RMSE, m/s: baseline = H14 |
|---|---:|---:|
| `30618_0652866c` | 0.035817614 | 0.036396438 |
| `30618_073f08d1` | 0.033482452 | 0.034387956 |
| `30618_117c2d02` | N/A | N/A |
| `30618_1551d0a9` | 0.003942772 | 0.004033947 |
| `30618_27e994fc` | 0.163632545 | 0.159096258 |
| `30618_3e012faf` | N/A | N/A |
| `30618_46e21b9b` | N/A | N/A |
| `30618_5036aa78` | N/A | N/A |
| `30618_74559c73` | N/A | N/A |
| `30618_88548b02` | 0.050336407 | 0.050865299 |
| `30618_bcc9e7a2` | N/A | N/A |
| `30618_e151d6e4` | N/A | N/A |
| `30639_0ab96c59` | 0.018981006 | 0.019389049 |
| `30639_9c362687` | 0.078329692 | 0.162373575 |
| `30639_c31df386` | 0.062531850 | 0.064883261 |
| `30639_dce52be4` | 0.360059012 | 0.103208196 |
| `30639_e4379d7f` | N/A | 0.138142127 |

[Raw results](development/results.json), [per-bag/per-receiver/per-fault CSV](development/per_bag.csv), [aggregate](development/aggregate.csv), [decision](development/decision.json), [access](development/access.json), [per-bag activation/metadata](development/bags/).

### Состояние до/во время/после отказа

Ниже пост-анализ сохраненной трассы первого по имени development bag `30618_0652866c`, исходный dropout [156.9,166.9) s. Это иллюстрация уже полученного результата, не заранее заявленное доказательство причинности и не новая симуляция; обе модели совпадают. Полные traces содержат output/inner v, s, pv, d-before/after, statuses, source stamps и pairing diagnostics.

| t, s | Фаза | Estimate.v, m/s: base = H14 | d после шага, m/s² | Mode |
|---:|---|---:|---:|---|
| 156.856545 | До отказа | 2.013682774 | -0.105824341 | FUSED |
| 157.906545 | Во время | 1.895922190 | -0.105824341 | MODEL_ONLY |
| 166.856545 | Перед концом окна | -0.316781286 | -0.105824341 | MODEL_ONLY |
| 167.406545 | После конца окна | -0.345115764 | -0.105824341 | MODEL_ONLY |

Эта таблица не утверждает, что восстановление завершилось сразу после окна; указаны фактические modes. Отрицательные скорости здесь также присутствуют у baseline, это не улучшение или новая регрессия H14. [Trace данного fault](development/traces/30618_0652866c-fault2.json.gz).

## Отдельные заранее объявленные диагностики

**Искусственная availability-диагностика** на всех 17 development-bag сохраняет исходные source timestamps. Rear availability сдвигается на +0.05 s относительно виртуальной причинной availability envelope; это НЕ восстановление реальных wall-clock arrivals. До подачи сообщения оно недоступно Timeline; код Timeline не меняется. Получено **96048 async pairs / 62507 async updates**. Расписания двух моделей совпали, future-use=0. Это свидетельство активации кода при искусственно созданной фазе, **не естественный accuracy gain**. GNSS-accuracy для этого измененного scheduler не предъявляется. [Результат](development/availability_diagnostic.json).

**Синтетические сценарии**: здоровый synchronous/alternating поток, startup, последующий dropout [8,13), одиночный выброс, alternating zeros, общий lock, low-speed lock. Пример всей 20-секундной симуляции с dropout: RMSE 0.174206899→0.002914605 m/s; healthy alternating: 0.014321470→0.002869413. Это искусственная физическая модель с фиксированным внешним d=0.12 m/s², не запись и не admission. Синхронный сценарий одинаков: 0.001565491 m/s. Во всех восьми сценариях нет новых false stops/future-use. Low-speed synthetic RMSE изменился на +4.9344e-9 m/s; эта малая локальная разница не скрывается. Реальные записи и эти диагнозы не агрегируются. [Raw synthetic results](synthetic/results.json), [полная trace](synthetic/trace.csv).

## Вычислительная стоимость и реально выполненные тесты

Первый development bag, 10 s warmup + следующие 180 s, 3600 измеряемых ticks; 3 AB/BA цикла = 12 отдельных replays, threads=1, одинаковый сбор outputs. Медианы шести повторов каждой модели:

| Показатель | v7 | H14 | Изменение |
|---|---:|---:|---:|
| Wrapped step CPU, microseconds/tick | 36.281952 | 43.913594 | **+21.034%** |
| Replay CPU, microseconds/tick | 54.200901 | 62.345326 | **+15.026%** |
| Replay wall, microseconds/tick | 54.207454 | 62.349743 | **+15.021%** |
| Child process peak RSS, bytes | 94695424 | 94695424 | 0 |

Это существенная стоимость даже при нулевом естественном выигрыше. Step содержит одинаковую измерительную обертку; replay включает Timeline/сбор результата, peak RSS — весь offline Python-процесс с scientific dependencies, не память ROS-ноды. Никакой статистической независимости миллионов ticks не предполагается. [Все повторы и диапазоны](development/cost.json).

Research workflow **завершился success**: 144 original tests, 43 research-integrity, 21 H14 tests и 24 legacy ObserverTests с H14 — PASS. Это разные наборы с пересечениями, не 232 уникальных теста. В H14: 6000 mixed ticks полного off/pristine сравнения Estimate и исходного состояния; 2000 synchronous ticks equivalence; unique consumption, no second v/P update, prefix causality, future/stale/duplicate/reset/gap/range, contaminated pending rejection, bounded memory на 12000 ticks, role denial до SQLite. Synthetic, dataset checksum, train, development, cost, availability и checkpoint завершены. Все логи в этой директории.

[Обычный CI source commit](https://github.com/jabrailkhalil/hack/actions/runs/36184181939) также success: core, research-integrity, ROS Humble и offline-limited. **Эти ROS/offline jobs запускали неизмененный canonical v7, не включенный H14.** Новый installed H14 ROS benchmark под 2 CPU / 500000000 bytes, оба clock modes, **НЕ выполнен**: кандидат не допущен по natural coverage/gain. Offline CPU/RSS и заданная сетка 20 Hz не доказывают publisher→subscriber latency/реальную wall-frequency.

## Литература и математика

Один узкий источник: Jiang et al., IEEE TAES 2017, DOI 10.1109/TAES.2017.2697598, об asynchronous multirate fusion и correlated noise. Consensus дал **metadata+abstract**. Scite дал metadata, но запрос fulltext завершился реальным monthly quota failure; полный текст и citation contexts **не прочитаны**. Покупок/подписок не было. Эти материалы не удостоверяют H14.

Wolfram фактически проверил среднее время affine пары, монотонность, exponential weight composition, scalar EMA и correlated-pair variance; при rho=1 variance среднего остается sigma². Дополнительный unit/clip вызов вернул `{Quantity[1,"Meters"/"Seconds"^2],0.2,True}`. Исполнимые worksheet и фактический вывод, включая предупреждение о symbolic L в первом вызове, сохранены в [science/](science/). Теоретические тождества не доказывают устойчивость всей switched observer или выигрыш на записях; software unique-consumption invariant проверен тестами.

## Воспроизведение

Полный checkout с историей, Python 3.13.5. Первые три команды ниже подготавливают checkout для воспроизведения; в Actions вместо них выполнялся actions/checkout. Остальные основные команды действительно запускались workflow; OUT должен быть новым:

```bash
git fetch origin research/round2-H14
git worktree add --detach ../hack-H14-run 8847307321e9336a9c3a5735ad25d76b635a801b
cd ../hack-H14-run
python -m pip install -r requirements-research.txt
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
PYTHONPATH=src/reserve_odometry python -m unittest discover -s tests -v
python -m unittest discover -s research/tests -v
git apply --check research/R2_H14/adaptation-hook.patch
git apply research/R2_H14/adaptation-hook.patch
PYTHONPATH=src/reserve_odometry python -m unittest discover -s research/R2_H14/tests -v
OUT=$(mktemp -d)
python tools/research_R2_H14/diagnostics.py --output "$OUT/synthetic"
python tools/get_dataset.py
python tools/research_R2_H14/run.py --stage development --output "$OUT/development" --workers 2
```

Полная реально исполненная команда legacy substitution и compileall находится в `.github/workflows/research-r2-h14.yml`; `commands.sh` в delivery ее сохраняет. Эта работа не запускала validation и не создавала authorization freeze. Повторный прогон на тех же данных не превращает их в независимый test.

Artifact ZIP ID `10885147491`, SHA256 `9ed7eaaaf424e75fa5b58e7d239972262ca03d45bece98b3ef73199b5780a772`, скачан и проверен. Runtime patch SHA256 `6449286b1bcafbb28e4c8f9218a0756aa352fc85faf080008ce0ae11efe6364e`: проверено применение к pristine BASE и точное совпадение с исполняемыми исходниками. Source manifest из Actions совпал с локально протестированными файлами без расхождений. Post-run audit только перечитал сохраненные результаты; SQL measurements не открывались заново для анализа/настройки.

## Вывод и ограничения

**INCONCLUSIVE по полезности механизма на естественных асинхронных режимах; проверенный кандидат не прошел admission и не готов к merge.** Натуральных async-пар нет, gain=0%, стоимость step CPU выросла примерно на 21%. Искусственный phase shift и synthetic dropout подтверждают способность кода исполняться, но не дают требуемого доказательства accuracy. Пороги, baseline, алгоритм и параметры не менялись после результата. Общая common-mode ошибка колес по-прежнему неоднозначна. Distance — scalar reanchored surrogate, не XYZ/ENU или полный terminal drift. Локальный DNS был недоступен, но GitHub Actions обеспечил реальные данные/исполнение/запись; недоступность среды не является причиной пропуска validation — причиной стал заранее объявленный coverage gate.
