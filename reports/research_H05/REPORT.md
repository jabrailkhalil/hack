# H05 — отрицательный исследовательский результат, не готов к merge

## Решение

**Вариант `H05_ttl2s` отвергнут: требуемое улучшение не достигнуто.** На реальных validation-записях clean group-macro RMSE улучшился на 0.009716%, а fault-event RMSE практически не изменился. Это существенно меньше заранее заданных 2% clean либо 5% fault gain. Регрессионные пороги не нарушены, но само по себе их прохождение не делает вариант улучшением. Общий evaluator оставил `v5_adaptive_05s`.

Это вывод об одном зафиксированном варианте, а не опровержение любых алгоритмов истории надёжности. Дополнительного перебора или корректировки по validation не было. Final test не открывался и не переоценивался. Активный default не заменён.

## Идентичность эксперимента

| Объект | Идентификатор |
|---|---|
| Общий baseline, adaptive_v5 | `984fdf2fc4faf05325249215d6b8541c0e68209a` |
| Ветка исследования | `research/parallel-H05` |
| Предрегистрация до экспериментов | `886fcf547ba1d39440a33590029513e8774adbef` |
| Замороженные patch/config/runner, измеренный commit | `613907b067513c65a36dc8a2cc79ce19858b01b9` |
| GitHub Actions, run / attempt | `36175046669` / `1` |
| Checkpoint branch | `checkpoint/H05-36175046669-1` |
| Неизменный checkpoint commit | `8c337e8d83504c62899350f5ccfe3725bf6d0779` |
| Draft PR | [#17](https://github.com/jabrailkhalil/hack/pull/17) |

Протокол: [PROTOCOL.md](../../research/H05/PROTOCOL.md). Зафиксированные хеши: [FREEZE.json](../../research/H05/FREEZE.json). Реальный патч алгоритма: [H05-reliability.patch](../../research/patches/H05-reliability.patch). Профиль для исследовательской рабочей копии: [profile.yaml](../../research/H05/profile.yaml).

SHA256 патча: `572df469986e85efd97a922cdaceb9c25f1117fd52705dd93de2c36a5bad06f4`.
SHA256 применённого core: `3847b9ffad0fd7fe1d4cf4958b11af5ae0627f62bf74e9d3f94c377328afa9ea`.
SHA256 исходного core: `780ca4796d86b4fa4e8c8679abfb73f58f23e003d4ee644ba964ffdeac9f0bfc`.

На момент открытия PR main уже имел SHA `efc473e415795d64770ef9dfa4f1bc417078da32`. Исследование не меняло main и чужие ветки, не перебазировалось на этот main и не выдаёт результаты за сравнение с ним. При будущем продвижении другого победителя потребуется отдельное сравнение с актуальным main. Merge и auto-merge не выполнялись.

## Что действительно изменяет алгоритм

Для каждого колеса хранятся последние четыре timestamp приписываемых ему аномалий и последний обработанный timestamp. Вклад события линейно уменьшается до нуля за 2 секунды. Надёжность `q=max(0.25, 1/(1+sum(max(0, 1-age/2))))`. Один хороший sample не стирает историю; после двух секунд без новых аномалий полный вес возвращается точно. Это ограниченная история, а не постоянный blacklist.

Свежие уникальные RANGE/RATE_ANOMALY учитываются локально. MODEL_DISAGREEMENT/AMBIGUOUS_PAIR учитываются только при принятом втором колесе в том же tick. Missing/stale, дубликаты, старые/будущие/невалидные samples не накапливают штраф. Общее расхождение обоих колёс с моделью не объявляется двумя идентифицированными отказами.

Меняются взвешенная скорость принятых колёс и прежняя R: `z=sum(q_i*z_i)/sum(q_i)`, `R=R_existing/mean(q_i)` до прежнего residual inflation. Нет дополнительного выигрыша дисперсии от фиктивной независимости двух колёс. При q=1 сохраняется исходная арифметическая ветка. Instantaneous gates, disturbance adaptation, bootstrap, bounded reacquisition, stop logic, Timeline и ROS adapter не изменяются.

Память: две очереди максимум по четыре timestamp и два timestamp дедупликации. Новые внешние runtime-зависимости отсутствуют. Используются только controller/front/rear и их времена. Патч применяется именно в экспериментальном рабочем дереве, как в v6; закоммиченные активные core/default и опубликованные отчёты остаются без изменений. Вариант единственный: окно 2.0 s, минимум 0.25, ёмкость 4 на канал.

Из предыдущих отрицательных результатов учтены fault-регрессии переноса скорости/затухания disturbance в v6 и дополнительные false stops при изменении process noise в v5. Эти механизмы в H05 не воспроизводились.

## Методика и защита сравнения

Runner проверяет идентичность защищённых исходников, split и evaluator относительно общего baseline, а также SHA256 патча, профиля и самого runner из FREEZE. Baseline Observer загружается из точного Git object указанного SHA, а не объявляется эквивалентным новому алгоритму с выключенным флагом. Дополнительный v4 используется только для воспроизведения опубликованного сравнения.

`tools/finalization/evaluate.py`, `tools/research_v3/experiment.py`, `tools/research_v6/compare.py`, exporter и Timeline не редактировались. Исследовательский driver подставляет только реализации Observer и configurations. Используются неизменные replay/score, match/reference masks, fault placement, group aggregation и decide. Отдельно, как записано в протоколе, проверяется pooled RMSE <= baseline*1.005; исходный decide не изменён. Историческая строка scope внутри неизменного decide описывает прежний адаптивный v6-поиск; H05 использовал ровно один заранее выбранный кандидат без подбора по validation.

Перед validation выполнен replay первых трёх заранее названных train-bag: `30618_0259fe53`, `30618_082f1d65`, `30618_095a115b`. Store разрешал только три vehicle-топика, без GNSS train labels. Соответственно это проверки исполнения, расписания и причинности, НЕ оценка абсолютной точности и не подбор параметров. Число выходов для каждой модели: 24562, 404, 26435 соответственно. У всех моделей ноль resets/causal_errors; по одному одинаковому catchup event на запись.

Замороженный кандидат затем один раз проверен на всех 19 validation-bag / 10 группах, оба GNSS receiver сохранены исключительно в offline evaluator. Reference доступен в 9 группах / 30 bag-receiver парах. Четыре записи без reference не заменяются нулевой ошибкой. Выполнены те же 76 fault-сценариев и 120 сравнений с reference: front bias +5 m/s на 5 s, оба dropout 5/10 s, оба lock 3 s. Output 20 Hz, alignment_delay=0; timestamps и reference masks одинаковые для всех моделей.

Пороги не менялись: >=2% clean либо >=5% fault gain; <=0.5% регрессии основных агрегатов, <=1% distance, per-bag/receiver clean <= baseline + max(0.005 m/s, 5%). Нельзя терять coverage, добавлять false stops/unrecovered или нарушения причинности. Сверка опубликованных baseline дала **468 числовых полей, максимальное абсолютное расхождение 0.0**. Это воспроизведение, не независимый final test.

## Измеренные агрегаты

Изменение — `(H05 / v5 - 1) * 100%`; отрицательное значение ошибки лучше.

| Метрика | Baseline v5 | H05_ttl2s | Изменение |
|---|---:|---:|---:|
| Clean group-macro RMSE, m/s | 0.117138274167 | 0.117126893203 | -0.009716% |
| Fault-event group-macro RMSE, m/s | 0.538434410852341 | 0.538434410852170 | практически 0 |
| Pooled clean RMSE, m/s | 0.216723602850 | 0.216712916326 | -0.004931% |
| Scalar span distance RMSE, m | 4.630977808475 | 4.631705620601 | **+0.015716%** |
| Сопоставленные speed samples | 698891 | 698891 | без потери |
| False stops, clean | 18 | 18 | без роста |
| False stops, fault | 0 | 0 | без роста |
| Unrecovered comparisons | 0 | 0 | без роста |

Fault gain около 3.18e-11% — численно ничтожное различие, не практически значимый выигрыш. Максимальная абсолютная разница event RMSE среди пар составляет 7.05e-12 m/s. Все 120 recovery_s совпадают точно. Все n/coverage совпали, causal_errors/resets в clean и fault — ноль. Не выявлено ни одной clean bag/receiver RMSE-регрессии. Единственная причина отказа исходного decide: `insufficient_gain`; дополнительный pooled gate также не нарушен.

Distance здесь — переякоренная скалярная ошибка на непрерывных GNSS-speed отрезках, НЕ xyz/ENU и НЕ полный terminal drift.

## Все validation-bag: clean RMSE

В этой обзорной таблице усредняются доступные master/rover RMSE внутри bag. Это только представление per-bag данных, НЕ замена официального group-macro подсчёта. Исходные метрики каждого receiver, включая faults, остаются в JSON и CSV ниже.

| Bag | v5, m/s | H05, m/s | Изменение |
|---|---:|---:|---:|
| 30618_0686195f | 0.094311205868 | 0.094311205868 | 0% |
| 30618_2255aade | нет reference | нет reference | — |
| 30618_2dbce472 | 0.093861479647 | 0.093861479647 | 0% |
| 30618_2f104a1d | 0.049625371331 | 0.049625371331 | 0% |
| 30618_437e855c | 0.043145801569 | 0.043145801569 | 0% |
| 30618_49fe4c54 | 0.468766866777 | 0.468766866777 | 0% |
| 30618_4e1e3181 | нет reference | нет reference | — |
| 30618_68847170 | 0.038502827848 | 0.038502827848 | 0% |
| 30618_68d1748a | 0.234489408045 | 0.234328837714 | -0.068477% |
| 30618_76e1f9c7 | 0.040772918467 | 0.040772918467 | 0% |
| 30618_7bfbb5ed | нет reference | нет reference | — |
| 30618_95c49c30 | нет reference | нет reference | — |
| 30618_b15eafc3 | 0.032750852155 | 0.032750852155 | 0% |
| 30618_b8044aa0 | 0.031912909614 | 0.031912909614 | 0% |
| 30618_defd0170 | 0.114305223308 | 0.114305223308 | 0% |
| 30639_3b3d9eb8 | 0.216187663518 | 0.216150797466 | -0.017053% |
| 30639_50956d6e | 0.250266479297 | 0.250259058323 | -0.002965% |
| 30639_9f0b519f | 0.038575152205 | 0.038575152205 | 0% |
| 30639_d601d28f | 0.109252544613 | 0.109252544613 | 0% |

Самое заметное улучшение отдельного receiver: `30618_68d1748a/master`, RMSE 0.147618204550 -> 0.147297063888 m/s (-0.217548%). Этого недостаточно для общего gain gate.

## Регрессии, которые нельзя скрыть за RMSE

| Запись / receiver / метрика | v5 -> H05 | Изменение |
|---|---|---:|
| 30639_3b3d9eb8 / rover, clean distance RMSE | 26.522054181 -> 26.541366295 m | +0.072815% |
| 30639_3b3d9eb8 / master, clean distance RMSE | 12.861796436 -> 12.868453610 m | +0.051759% |
| 30618_68d1748a / master, clean MAE | 0.032837114 -> 0.032858900 m/s | +0.066348% |
| 30618_68d1748a / master, clean p95 | 0.089649412 -> 0.089742432 m/s | +0.103761% |
| 30618_2dbce472 / rover, bias, RMSE окна fault + 10 s | 0.049480448 -> 0.049732937 m/s | +0.510280% |
| 30639_d601d28f / rover, lock, RMSE окна fault + 10 s | 0.216742282 -> 0.216998388 m/s | +0.118162% |
| 30618_68847170 / master, bias, p95 окна fault + 10 s | 0.068340634 -> 0.068791117 m/s | +0.659173% |

Указанные post-fault окна отличаются от основной метрики `event_rmse`, которая ограничена временем самого отказа. Локальные проценты выше 0.5% не являются нарушением заранее заданного ограничения на ОСНОВНЫЕ АГРЕГАТЫ, но они показаны явно. Наибольшая абсолютная RMSE-регрессия такого окна — 0.000256107 m/s, а не крупный абсолютный провал.

В пяти изменившихся clean bag/receiver парах немного вырос модуль signed bias; наибольший относительный рост 0.506199% у `30618_68d1748a/master`, с 0.003114919 до 0.003130686 m/s по модулю. В stress window `30618_437e855c/master/lock` signed bias вырос с 0.011133706 до 0.011458634 m/s (+2.918417%; абсолютный рост 0.000324928 m/s). Это диагностические показатели, не новые задним числом критерии выбора.

Дополнительный описательный group-macro аудит clean: MAE -0.002899%, p95 +0.000835%, средний по группам модуль bag/receiver bias +0.010668%. Для полного fault+10s окна group-macro RMSE -0.002853%. Расчёты аудита не заменяют исходные метрики/решение и не использованы для подбора.

## Фактически выполненные проверки

[Исследовательский workflow 36175046669](https://github.com/jabrailkhalil/hack/actions/runs/36175046669), job 108203487092: все шаги success. На runner Python 3.13.5 выполнены: 70 штатных тестов до патча; 22 штатных core-теста и 10 Timeline-тестов после применения патча; 24 специальных H05 mechanism/invariant tests. Штатные тесты сохраняют свои конфигурации, где H05 по умолчанию выключена; включённый вариант проверяется специальными тестами и реальным paired replay. Те же 24 специальных теста дополнительно прошли локально; это не ещё 24 уникальных теста.

Проверены ограниченная память, expiry/deduplication, отсутствие штрафа за future/stale samples, reset, front/rear symmetry, weighted measurement/R, отсутствие мнимой независимости, точное совпадение с исходным baseline при выключенной H05 и на чистом потоке, сохранение reacquisition при общем drift. После тестов успешно выполнены реальные train и validation этапы; сохранены их source/config/evaluator hashes и журналы доступа. Validation evaluator сообщил 31.100 s elapsed; это длительность offline вычисления, НЕ latency ноды.

Git clone из локального контейнера был недоступен из-за DNS; нативный GitHub-коннектор и GitHub Actions были доступны, поэтому чтение/запись репозитория и реальные измерения завершены. Недоступный/не выполненный этап — свежий ROS benchmark именно применённого H05: installed launch, end-to-end latency, RSS и проверка 2 CPU / 500 MB. Успешный CI неизменённого default и исторические v4/v5 измерения не приписываются H05. Отрицательный результат не выдвигается на runtime-приёмку.

## Команды воспроизведения

Из чистого отдельного рабочего дерева, с доступным Python 3.13.5. Ниже те же операции, что реально выполнил workflow; локальные имена venv/output заменяют RUNNER_TEMP. Каталоги результатов должны быть новыми.

```bash
git switch --detach 613907b067513c65a36dc8a2cc79ce19858b01b9
python3.13 -m venv .venv-h05
.venv-h05/bin/python -m pip install -r requirements-research.txt
.venv-h05/bin/python tools/get_dataset.py
PYTHONPATH=src/reserve_odometry .venv-h05/bin/python -m unittest discover -s tests -v
git apply --check research/patches/H05-reliability.patch
git apply research/patches/H05-reliability.patch
PYTHONPATH=src/reserve_odometry .venv-h05/bin/python -m unittest discover -s tests -p test_core.py -v
PYTHONPATH=src/reserve_odometry .venv-h05/bin/python -m unittest discover -s tests -p test_timeline.py -v
PYTHONPATH=src/reserve_odometry .venv-h05/bin/python -m unittest discover -s research/H05/tests -v
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv-h05/bin/python tools/research_h05/run.py --stage train --output /tmp/H05-train-new
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv-h05/bin/python tools/research_h05/run.py --stage validation --train-output /tmp/H05-train-new --output /tmp/H05-validation-new --workers 2
```

Runner запрещает перезапись output, test stage и validation без успешного train-only smoke с теми же source/freeze/evaluator hashes. Коммит с этим отчётом не меняет frozen candidate и не запускает новый H05 validation. Для воспроизведения именно измеренной версии используется SHA 613907b выше.

## Исходные результаты и ограничения

Все данные сохранены отдельно в checkpoint SHA `8c337e8d83504c62899350f5ccfe3725bf6d0779`, папка `reports/research_H05/runs/H05-36175046669-1/`. Это новый checkpoint, не перезапись опубликованных v5/v6 отчётов.

[Все исходные JSON/per-bag checkpoints и логи](https://github.com/jabrailkhalil/hack/tree/8c337e8d83504c62899350f5ccfe3725bf6d0779/reports/research_H05/runs/H05-36175046669-1), [полный results.json](https://github.com/jabrailkhalil/hack/blob/8c337e8d83504c62899350f5ccfe3725bf6d0779/reports/research_H05/runs/H05-36175046669-1/validation/results.json), [aggregate.csv](https://github.com/jabrailkhalil/hack/blob/8c337e8d83504c62899350f5ccfe3725bf6d0779/reports/research_H05/runs/H05-36175046669-1/validation/aggregate.csv), [per_bag.csv](https://github.com/jabrailkhalil/hack/blob/8c337e8d83504c62899350f5ccfe3725bf6d0779/reports/research_H05/runs/H05-36175046669-1/validation/per_bag.csv), [решение неизменного v6 evaluator](https://github.com/jabrailkhalil/hack/blob/8c337e8d83504c62899350f5ccfe3725bf6d0779/reports/research_H05/runs/H05-36175046669-1/validation/decision_v6_unchanged.json), [H05 contract](https://github.com/jabrailkhalil/hack/blob/8c337e8d83504c62899350f5ccfe3725bf6d0779/reports/research_H05/runs/H05-36175046669-1/validation/H05_contract.json).

Actions artifact `H05-36175046669-1`, id 10882246390, SHA256 `f91c8323ed0332b7855d581c3ca9b577740fd63c0d3efd7b9ed16825d634894e`; ZIP скачан и проверен по этому хешу. SHA256 исходного `validation/results.json`: `b3a8dc92ce494fb8e557d860ed6430b5fa33ccdfe100dd9804530e2d7a0dbd19`.

Описательные per-bag/regression сводки воспроизводятся без нового доступа к bags: `python reports/research_H05/audit.py --evidence /path/to/extracted/H05 --output /tmp/H05-audit-new`. Скрипт проверяет хеш исходного results.json и не меняет evaluator/вердикт. Для списка микрорегрессий используется только порог отображения 1e-10, не изменяющий критерии приёмки.

Validation уже использовался ранее: независимого test здесь нет. Стандартные четыре вида отказов не систематически покрывают intermittent/chattering faults, ради которых задумана H05; набор сценариев в этом раунде не расширялся. Совпадение event RMSE и изменения post-fault окна совместимы с тем, что история влияет прежде всего на возврат веса после отказа, а большие штатные сбои уже отсекаются мгновенными gate. Это интерпретация результата, не отдельное доказательство поведения на всех отказах.

У disturbance осталась исходная адаптация по согласованной паре. История может замедлять коррекцию уже исправного канала; это наблюдаемые локальные post-fault регрессии, а не универсальная гарантия полезности. Common-mode ошибка двух колёс остаётся неоднозначной. Результат не является сертификацией безопасности.

**Итог: оставить baseline первого раунда; H05_ttl2s — сохранённый воспроизводимый отрицательный результат, не готов к merge.**
