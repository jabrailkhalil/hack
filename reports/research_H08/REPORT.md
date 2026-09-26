# H08 — отрицательный исследовательский результат

**Вывод: гипотеза отвергнута для единственного проверенного кандидата `h08_exact_midpoint`. Не готов к merge; не заменяет активный профиль.** Более точное интегрирование привода не улучшило реальную одометрию относительно закреплённого `adaptive_v5`: clean RMSE вырос на 0.023021%, fault RMSE — на 0.588397%. Последнее превышает неизменный допуск 0.5%. Требуемых 2% clean gain или 5% fault gain также нет. Небольшое улучшение дистанционной метрики не компенсирует нарушение gates.

## Источники и порядок исследования

| Этап | Commit |
|---|---|
| Общий baseline, профиль adaptive_v5 | `984fdf2fc4faf05325249215d6b8541c0e68209a` |
| Протокол до реализации и экспериментов | `29d768fc527354c57910ea4a8e41ac247cb97b74` |
| Изменённый core и отдельный профиль H08 | `77ebf5d32953309f72ac1a53fff55f33d2faed27` |
| Исходники, использованные в завершённом запуске | `dc7cc320057380cefb9c0035a7335ee793fada23` |
| Freeze кандидата после train и ДО validation | `11501a96f08b67b312fd6c9324792fbee603f227` |
| Сохранённые train/validation результаты | `2832449a61857eb221b026ebe300acc786b8e28f` |
| Сохранённые ROS runtime результаты | `476185ece8954cf300c19e0d6d392fbb7a599b26` |

Ветка изменений: `research/parallel-H08`. Данные сохранены отдельно в `checkpoint/H08-36175598186-1` и `checkpoint/H08-runtime-36175598186-1`. Main, чужие ветки и опубликованные отчёты этим исследованием не изменялись. Merge и auto-merge не выполнялись.

Проверен ровно один численный вариант. Физические/фильтровые параметры не подбирались вообще. После получения validation алгоритм и параметры не менялись. Freeze содержит исходники, профиль, split, evaluator и выбранного кандидата; создан в 2026-09-25 18:49:45 UTC и опубликован отдельным коммитом до открытия validation в runner.

Прочитаны текущий core, v6 REPORT и отрицательные результаты v5/v6. В частности, не повторялись projection/decay и варианты Q/R/скорости адаптации. Уменьшение численной ошибки заранее не считалось доказательством улучшения на реальных записях.

## Что изменено в алгоритме

В baseline конечное состояние инерционного привода уже вычисляется экспоненциально, но вклад в скорость равен `h * drive_end`; сопротивление вычисляется при скорости начала шага. H08 интегрирует привод при удерживаемом target аналитически:

```
drive_end = T + (drive_start - T) * exp(-h / tau)
mean_drive = T + (drive_start - T) * (1 - exp(-h / tau)) / (h / tau)
```

Сначала вычисляется предсказанная середина шага по точному полушаговому интегралу привода и начальному сопротивлению; для полного шага используется сопротивление при этой средней скорости. Для устойчивого расчёта применены `expm1` и ряд при малом аргументе. Это точный интеграл удерживаемого target, **не точное решение всей нелинейной системы**: `drive_target(u, v_start)` остаётся удерживаемым на шаге.

Добавлены dependency-free `numerics_h08.py`, численный путь в core и отдельные `h08_exact_midpoint.yaml/json`. Опция `model.numerical_prediction: 1.0` включает кандидат; значение по умолчанию 0.0 исполняет прежние арифметические операции. `default.yaml` и `adaptive_v5.yaml` не изменены. Параметры физики, tau, adaptation, шумов, gates, recovery, scales, timeline совпадают с baseline.

Сохранены ограничение скорости и ускорения, запрет численной смены знака при торможении/выбеге, адаптация по прежнему конечному drive, обработка stop, причинность и 20 Гц без дополнительного ожидания. Дистанция по-прежнему интегрируется существующей трапецией после коррекции скорости. Новых очередей/истории и GNSS/IMU-входов в runtime нет.

## Методика и фактически обработанные данные

**Train:** 64 разрешённых bag, 1 366 299 выходных отсчётов на каждый из двух методов. Loader читал только controller/front/rear. Для всех bag проверены одинаковые shape/timestamps, конечность, причинность и отсутствие дополнительных resets. GNSS reference на train не открывался, поэтому train-дельты скорости/дистанции между методами не названы ошибкой относительно истины. Тюнинга не было.

**Validation:** все 19 исходных bag, 10 групп, reference в 9 группах; 30 bag/receiver-пар с reference. Оба GNSS-приёмника использованы только измерителем, никогда алгоритмом. Четыре bag без reference (`30618_2255aade`, `30618_4e1e3181`, `30618_7bfbb5ed`, `30618_95c49c30`) не заменены нулевой ошибкой.

Baseline, H08 и контрольный v4 прогнаны одним неизменным `tools/finalization/evaluate.py`. Не менялись `tools/research_v3/experiment.py`, `tools/research_v6/compare.py`, reference matching, маски, метрики, пороги и split. Git blob-аудит приведён в [AUDIT.json](AUDIT.json). Разница с протоколом отсутствует; дополнительный явный pooled guard <=0.5% только дополняет, а не смягчает исходный v6 decide.

Fault construction буквально соответствует v6: одинаковый anchor на каждом bag, bias front 5 с, dropout обоих колёс 5/10 с, lock обоих колёс 3 с, одинаковые pre/post-окна. Выполнено 76 сценариев, 120 сравнений с доступным reference. Runtime schedules и reference-маски baseline/candidate одинаковы. Baseline воспроизводит опубликованный v5 по **468 числовым полям с max absolute delta = 0.0**.

Final-test bag payloads не открывались, final-test evaluation не запускался. Исторические показатели final test не использованы для выбора или сравнения H08. Общие release-integrity unit-тесты проверяют сохранённый архив/метаданные старого релиза; это не новый прогон final test.

## Основные результаты относительно adaptive_v5

Положительное изменение ошибки означает ухудшение.

| Метрика | Baseline | H08 | Изменение |
|---|---:|---:|---:|
| Clean group-macro RMSE скорости, м/с | 0.117138274167 | 0.117165240053 | +0.023021% |
| Fault-event group-macro RMSE, м/с | 0.538434410852 | 0.541602543761 | **+0.588397% — FAIL** |
| Pooled RMSE скорости, м/с | 0.216723602850 | 0.216738207745 | +0.006739% |
| Scalar span group-macro RMSE дистанции, м | 4.630977808475 | 4.630800398265 | -0.003831% |
| Сопоставленные точки скорости | 698891 | 698891 | без потери |
| False stop samples, clean | 18 | 18 | без роста |
| False stop samples, fault | 0 | 0 | без роста |
| Fault-сравнения без recovery | 0 | 0 | без роста |
| Ошибки причинности / resets в validation replay | 0 / 0 | 0 / 0 | без роста |

Отказ v6 gate: `aggregate_regression`, `insufficient_gain`. Pooled guard пройден. Per-bag/per-receiver clean guard `max(0.005 м/с, 5%)` нигде не нарушен. Дистанция — переякоренная скалярная ошибка относительно интеграла GNSS-speed на непрерывных reference-отрезках; это не xyz/ENU точность и не полный терминальный дрейф.

## Существенные локальные регрессии и ограничения

| Bag / receiver | Сценарий | Baseline RMSE, м/с | H08 RMSE, м/с | Изменение |
|---|---|---:|---:|---:|
| 30618_68d1748a / master | lock 3 с | 0.077277556 | 0.087183702 | +12.8189% |
| 30618_68d1748a / rover | lock 3 с | 0.081512155 | 0.091003809 | +11.6445% |
| 30618_defd0170 / master | dropout 10 с | 0.154096383 | 0.170187967 | +10.4425% |
| 30618_defd0170 / rover | dropout 10 с | 0.154270699 | 0.170150008 | +10.2931% |
| 30618_68d1748a / master | dropout 10 с | 0.228631764 | 0.245529512 | +7.3908% |
| 30639_d601d28f / master | dropout 10 с | 1.020722638 | 1.037767372 | +1.6699% |

Последняя строка — максимальная абсолютная fault-регрессия: +0.017044734 м/с. Максимальная clean-регрессия: `30618_68d1748a/master`, 0.147618205 → 0.147897754 м/с (+0.189373%, +0.000279550 м/с), в пределах clean guard. Из 30 clean-пар 24 численно ухудшились и 6 улучшились; из 120 fault-пар — 78 ухудшились и 42 улучшились. Это описание измерений, не оценка статистической значимости.

В `30639_9f0b519f/master`, lock 3 с, recovery вырос с 0.049522 до 0.149522 с (+0.1 с). В `30618_49fe4c54/master`, bias 5 с, recovery уменьшился с 0.205104 до 0.005104 с. Остальные доступные recovery совпадают; невосстановлений нет.

Несмотря на небольшое агрегированное улучшение дистанции, её наибольшая абсолютная локальная регрессия: `30639_3b3d9eb8/rover`, 26.522054181 → 26.532647239 м (+0.010593058 м, +0.039941%). Все bag/receiver metrics, включая улучшения, ухудшения, n/coverage/MAE/bias/p95/recovery и отсутствие reference, сохранены в raw JSON и CSV, а не только выбранные строки этой таблицы.

Активный quadratic drag почти нулевой. Коэффициенты физики исторически оценивались с прежней дискретной моделью, а disturbance адаптируется по конечному drive. Поэтому лучшая квадратура сама по себе не гарантирует лучшую одометрию. Это возможное объяснение результата, не отдельно доказанный причинный механизм; параметры под это объяснение на validation не перенастраивались.

## Вычислительная стоимость и ROS

Train microbenchmark: первые 60 с `30618_0259fe53`, одинаковые inputs, 1120 выходов на replay, чередование порядка двух методов; первая пара — warmup, затем пять измеренных пар.

| Медиана на выход | Baseline | H08 | Изменение |
|---|---:|---:|---:|
| CPU, мкс | 34.237121 | 36.335080 | +6.1277% |
| Wall, мкс | 34.240235 | 36.338678 | +6.1286% |

Это Python replay вместе с Timeline и сбором выходов, не чистое время функции predict и не ROS latency. Короткий benchmark не даёт универсальной оценки overhead на другом CPU.

Отдельно фактически выполнены offline ROS Humble сборка, installed H08 smoke и четыре 60-секундных прогона неизменного `ros_benchmark.py` на development bag `30618_0652866c` при 1x receipt-order playback. Контейнер: 2 CPU, 500000000 байт памяти, `--network none`. Для candidate benchmark временно подставлялся отдельный H08 YAML в disposable working copy; default восстановлен, в git не менялся.

| Профиль / clock | Source Hz | Outputs | p95 end-to-end, мс | Max end-to-end, мс | Peak RSS, MB (10^6 B) |
|---|---:|---:|---:|---:|---:|
| Baseline / input_stamp | 20.000 | 1198 | 64.761769 | 120.566811 | 84.877312 |
| H08 / input_stamp | 20.000 | 1198 | 64.335006 | 120.566895 | 84.692992 |
| Baseline / ros_clock | 20.000 | 1196 | 61.293604 | 66.310613 | 84.758528 |
| H08 / ros_clock | 20.000 | 1196 | 57.300459 | 65.191403 | 85.032960 |

Wall rates соответственно 20.029990, 20.029932, 20.002757 и 19.999637 Гц. Все четыре измеренных latency/correctness/causality/rate/RSS gates пройдены: p95 <=100 мс, max <=250 мс, RSS <500 MB, ошибок причинности и correctness нет. p95 вычисляется после первых 10 с; maximum включает начало. Для input_stamp остаются 114 uncredited inputs, для ros_clock — 118, одинаково у baseline/H08; им не присваивается нулевая задержка.

Это короткая проверка одного development bag, не полный bag, не доказательство отсутствия утечек на длительном интервале и не hard-real-time гарантия. Отличия latency между единичными прогонами не объявляются статистически подтверждённым ускорением H08. Installed smoke подтвердил 37 параметров H08, 120 выходов, 20.000 Гц и отсутствие GNSS/IMU подписок.

## Фактически выполненные проверки и честный статус CI

Завершённый исследовательский workflow: [36175598186](https://github.com/jabrailkhalil/hack/actions/runs/36175598186). Успешный статус job означает завершение измерений, **не прохождение accuracy gate**.

9 H08 unit-тестов пройдены; один из них повторяет все 20 исходных observer-сценариев с включённым кандидатом. Проверены точный held-drive интеграл, сходимость midpoint, ограничения, будущие samples, ограниченное состояние, dt=0/невалидные параметры. Opt-out совпал с baseline по всем выходным полям на 4000 тестовых ticks. Compileall выполнен. Локально дополнительно проверено обратное/прямое применение runtime-части патча до точного baseline blob и обратно.

**Общий неизменённый suite: 70 тестов, 66 passed, 4 failures. Общий CI не зелёный.** Не пройдены два сравнения core с историческими release bytes/hashes и два равенства старой схемы Config/YAML, не включающей новый opt-in параметр. Эти tests и опубликованные PROMOTION/FREEZE файлы не переписаны. `preflight.py` сохраняет четыре failures и разрешает только исследовательское измерение при точном совпадении этих четырёх failure IDs, 70 запущенных тестах и отсутствии любых иных failures/errors/skips; это не отмена promotion gates.

Первый [run 36175133676](https://github.com/jabrailkhalil/hack/actions/runs/36175133676) остановился именно на этом suite, до train/validation/runtime. Это инфраструктурное исправление задокументировано в `research/H08/EXECUTION_NOTES.md`; численный алгоритм между попытками не менялся.

В [обычном CI 36175597849](https://github.com/jabrailkhalil/hack/actions/runs/36175597849) для measured source commit: core FAIL; research-integrity, ros-humble и offline-limited PASS. Обычные ROS jobs проверяют прежние default/adaptive профили; включённый H08 отдельно проверен исследовательским runtime job.

## Воспроизведение accuracy и train cost

Из репозитория с доступной историей, Python 3.13.5 и исходным dataset:

```bash
git checkout dc7cc320057380cefb9c0035a7335ee793fada23
python3.13 -m venv .venv-h08
.venv-h08/bin/python -m pip install -r requirements-research.txt
.venv-h08/bin/python tools/get_dataset.py
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
PY=.venv-h08/bin/python
OUT=$(mktemp -d /tmp/h08-replay.XXXXXX)
PYTHONPATH=src/reserve_odometry "$PY" research/H08/preflight.py --output "$OUT/preflight.json"
PYTHONPATH=src/reserve_odometry "$PY" -m unittest discover -s research/H08/tests -v
"$PY" -m compileall -q src research/H08
"$PY" research/H08/run.py --stage development --output "$OUT/development"
"$PY" research/H08/run.py --stage freeze --development "$OUT/development" --freeze "$OUT/FROZEN.json"
"$PY" research/H08/run.py --stage validation --freeze "$OUT/FROZEN.json" --output "$OUT/validation" --workers 2
```

Нормальная команда `PYTHONPATH=src/reserve_odometry python3 -m unittest discover -s tests -v` возвращает failure, как описано выше. `apply.py` повторно запускать не требуется: measured commit уже содержит готовый runtime-патч. Для baseline используйте adaptive_v5, для кандидата — h08_exact_midpoint. Runner отказывается перезаписывать output/freeze.

Фактически выполненные runtime-команды полностью сохранены в [.github/workflows/h08.yml](../../.github/workflows/h08.yml) и runtime.log: `docker build -t h08-runtime -f Dockerfile.environment .`, затем `docker run --network none --cpus 2 --memory 500000000 ...`, sequential colcon build, `tests/ros_calibrated_smoke.py --params-file .../h08_exact_midpoint.yaml --expected-json .../h08_exact_midpoint.json`, четыре вызова `tools/finalization/ros_benchmark.py --seconds 60 --clock-mode input_stamp|ros_clock --output ...` с точным порядком профилей из RUNTIME_PLAN. Пороги benchmark не изменялись.

## Исходные результаты

Все ссылки ниже закреплены на commit, а не на изменяемом main:

- [Train/validation каталог, журналы доступа, freeze и логи](https://github.com/jabrailkhalil/hack/tree/2832449a61857eb221b026ebe300acc786b8e28f/reports/research_H08/runs/36175598186-1).
- [Полный raw results.json](https://github.com/jabrailkhalil/hack/blob/2832449a61857eb221b026ebe300acc786b8e28f/reports/research_H08/runs/36175598186-1/validation/results.json), [per_bag.csv](https://github.com/jabrailkhalil/hack/blob/2832449a61857eb221b026ebe300acc786b8e28f/reports/research_H08/runs/36175598186-1/validation/per_bag.csv), [decision.json](https://github.com/jabrailkhalil/hack/blob/2832449a61857eb221b026ebe300acc786b8e28f/reports/research_H08/runs/36175598186-1/validation/decision.json).
- [ROS JSON, trace/resources CSV, node.log и execution.json](https://github.com/jabrailkhalil/hack/tree/476185ece8954cf300c19e0d6d392fbb7a599b26/reports/research_H08/runtime/36175598186-1).
- [Source/patch/test artifacts](https://github.com/jabrailkhalil/hack/actions/runs/36175598186/artifacts/10881617661), [measurement artifact](https://github.com/jabrailkhalil/hack/actions/runs/36175598186/artifacts/10881772995), [runtime artifact](https://github.com/jabrailkhalil/hack/actions/runs/36175598186/artifacts/10881628520).

## Границы вывода

Это повторно использованный validation, не независимый final test. Отвергнут именно один заранее зафиксированный вариант H08, а не все возможные численные методы. Независимого подтверждения улучшения нет; по текущему протоколу улучшение отсутствует и нарушен fault guard.

К моменту оформления main уже находился на другом SHA (`efc473e415795d64770ef9dfa4f1bc417078da32` при чтении ref). Результаты этого раунда относятся **только** к согласованному baseline `984fdf2...`; ветка не перебазирована, новый main не использован вместо общего baseline и утверждений о сравнении с ним нет.
