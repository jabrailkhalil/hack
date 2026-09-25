# H07 — разная динамика тяги и торможения

## Решение: исследовательский отрицательный результат, НЕ готов к merge

Гипотеза **отвергнута для зарегистрированной сетки и выбранного train-кандидата**. После выбора только на train замороженный `T10_B05` дал clean gain **0.0534%**, недостаточный против требуемых 2%, и **ухудшил fault RMSE на 0.6708%** при допустимых 0.5%. Требование минимум 5% fault gain тоже не выполнено. Основные причины исходного v6 gate: `insufficient_gain`, `aggregate_regression`.

Это не доказательство бесполезности любых асимметричных моделей. Проверены ровно шесть заранее заданных пар постоянных времени на train и один выбранный кандидат на повторно используемом validation. Другие параметры после validation не подбирались. Независимый final test не открывался и не пересчитывался. Default не переключён, merge/auto-merge не выполнялись.

## Фиксация источников и порядок эксперимента

| Объект | Commit / идентификатор |
|---|---|
| Общий baseline первого раунда, adaptive_v5 | `984fdf2fc4faf05325249215d6b8541c0e68209a` |
| Протокол до экспериментов | `7cc779db16be262aed5788067a2bca3b9e6614bb` |
| Измеренные алгоритм, тесты и runner | `ca96f620274ba24c82e1258e953bfb7bd1b40fe4` |
| Freeze выбранного кандидата ДО validation | `1e00925e75a7e5aa488578cfa853f336a2a5dde3` |
| Полные train/validation результаты | `55132ffc416485194be53c4d0b906d9dbc540d55` |
| Исследовательский run / attempt | `36175112902 / 1` |
| Отдельный обычный CI исходников | `36175112880` |

[Протокол](../../research/H07/PROTOCOL.md). Рабочая ветка: `research/parallel-H07`. Результаты записаны только в новую `checkpoint/H07-36175112902-1` и каталог `reports/research_H07/runs/36175112902/1`. Исходный main, чужие ветки, опубликованные отчёты v3/v5/v6 и исторические FREEZE/PROMOTION не менялись.

[Freeze](https://github.com/jabrailkhalil/hack/tree/1e00925e75a7e5aa488578cfa853f336a2a5dde3/reports/research_H07/runs/36175112902/1/train) содержит выбранный полный config, SHA256 кода/runner/evaluator/протокола/split и обучающих результатов. Validation начат в `2026-09-25T18:43:36.318462+00:00`, после успешного отдельного commit и push freeze. Runner до открытия validation проверяет соответствие выбранного JSON этому git-коммиту и сохранённым хешам.

За время параллельной работы main продвинулся: при подготовке отчёта его ref был `efc473e415795d64770ef9dfa4f1bc417078da32`. H07 не перебазировалась и не выдаёт сравнение с закреплённым baseline за сравнение с новым main.

## Алгоритмическое изменение

В `Config` добавлены `traction_tau_s` и `braking_tau_s`. Нулевое значение каждого независимо наследует прежнюю `actuator_tau_s`, сохраняя численное поведение исходных профилей. Новые значения проверяются на конечность и неотрицательность. Положительное значение включает отдельную реакцию для соответствующего режима.

После существующей валидации controller-команды выбирается постоянная времени: `u > command_deadband` — тяга; `u < -command_deadband` — торможение; внутри deadband и при отсутствующей, устаревшей, недопустимой или будущей команде — исходная постоянная. Режим зависит от знака команды, а не скорости: торможение задним ходом использует тормозную постоянную.

```python
alpha = 1.0 - math.exp(-dt / self.actuator_tau(u))
self.drive_a += alpha * (target - self.drive_a)
```

Сохраняется один прежний `drive_a`; смена режима его не обнуляет. Других состояний, очередей, ожидания будущих samples, входов GNSS/IMU или runtime-зависимостей NumPy/SciPy не добавлено. Gate, reacquisition, stop logic, disturbance-адаптация 0.5 с, физические gain, масштаб колёс и весь node/timeline/route не менялись. Существующие YAML/JSON профили оставлены побайтно прежними. Выбранный H07 включается только отдельным frozen `selected.yaml`, не стандартным запуском.

Изучены `reports/research_v3/REPORT.md`, `reports/research_v5/REPORT.md`, `reports/research_v6/REPORT.md`. Учтены отказы gain_only, слишком быстрой disturbance-адаптации, увеличенного process noise, projection и decay: нельзя считать train loss или clean gain достаточным доказательством устойчивости при отказах.

## Train: ограниченная идентификация

Использованы только 64 bag исходного train; 60 дали **87 453** выбранные точки. `Store.load(..., 'train')` декодировал только три vehicle-топика. Обращений к development и final test не было. Неизменный `training_set()` сохраняет прежние quality masks, seed, ограничение 1500 точек на bag и offline Savitzky–Golay производную согласованных колёс. Центрированная производная существует только в train-target, не в runtime.

Все коэффициенты, кроме двух постоянных времени из фиксированной сетки, заморожены. Критерий выбора: минимальная group/mode-weighted soft_l1 сумма с `f_scale=0.1`, как зарегистрировано до экспериментов. Это обучающий критерий ускорения, **не RMSE одометрии по независимому эталону**. В offline fitting используется прежняя дискретизация 0.1 с и wheel velocity, а не полный runtime observer с disturbance; это ограничение идентификации.

Базовая `tau0 = 0.3927619145850434` с.

| Вариант | Тяга / tau0 | Торможение / tau0 | Train soft_l1 cost | Weighted acceleration RMSE |
|---|---:|---:|---:|---:|
| adaptive_v5, контроль | 1 | 1 | 731.491476 | 0.301978746 |
| T05_B10 | 0.5 | 1 | 748.536389 | 0.302949407 |
| **T10_B05, выбран** | **1** | **0.5** | **741.555042** | **0.303051396** |
| T20_B10 | 2 | 1 | 748.459107 | 0.302663390 |
| T10_B20 | 1 | 2 | 754.500110 | 0.302969987 |
| T05_B20 | 0.5 | 2 | 769.066745 | 0.303690094 |
| T20_B05 | 2 | 0.5 | 757.042376 | 0.303601590 |

**Все шесть вариантов хуже baseline по train objective.** Лучший из них ухудшает cost на 1.3758%. Протокол заранее допускал единственную validation-проверку такого кандидата без заявления train gain. В итоге заморожены `traction_tau_s=0.3927619145850434`, `braking_tau_s=0.1963809572925217`; нейтраль сохраняет `actuator_tau_s=0.3927619145850434`. После freeze параметры не менялись.

## Неизменный paired evaluator и фактический охват

`tools/finalization/evaluate.py`, `tools/research_v3/experiment.py`, `tools/research_v6/compare.py`, split, reference matching, метрики и generator fault-сценариев побайтно совпадают с baseline. H07 runner меняет только набор передаваемых конфигураций; вызывает исходные `validate_bag`, `score`, `replay`, `metrics`, `distance_surrogate`, `summary` и `decide`. Приёмка не переписывалась под результат.

Одинаковые 19 validation-bag / 10 групп; reference есть у 30 bag/receiver-пар в 9 группах. Оба GNSS-приёмника сохранены, четыре bag без reference не считаются нулевой ошибкой. Те же 76 fault-сценариев и 120 сравнений с доступным reference: bias 5 с, dropout 5/10 с, lock 3 с. 20 Гц, alignment delay 0, одинаковые timestamps и маски. Воспроизведение обоих исторических контролей проверило **468 полей с максимальным абсолютным расхождением 0.0**.

Журнал фиксирует 64 train-load и 38 validation-load для 19 уникальных bag: второй validation-load в каждом bag выполняет заранее описанную диагностику переходов, а не повторный подбор кандидата. Измерения test не декодируются. Train/validation журналы и все исходные показатели сохранены, а не только лучшие случаи.

## Агрегированные результаты

Изменение — `(H07 / baseline - 1) * 100%`; для ошибок отрицательное значение лучше.

| Метрика | adaptive_v5 | H07 T10_B05 | Изменение |
|---|---:|---:|---:|
| Clean group-macro RMSE, м/с | 0.117138274167 | 0.117075676373 | −0.053439% |
| Fault-event group-macro RMSE, м/с | 0.538434410852 | 0.542046189066 | **+0.670793%** |
| Pooled clean RMSE, м/с | 0.216723602850 | 0.216688856852 | −0.016032% |
| Scalar span distance RMSE, м | 4.630977808475 | 4.623604144854 | −0.159225% |
| Сопоставленные clean точки | 698891 | 698891 | без потери |
| False stop samples, clean / fault | 18 / 0 | 18 / 0 | без роста |
| Fault-сравнения без recovery | 0 | 0 | без роста |
| Causality errors / resets, clean + fault | 0 / 0 | 0 / 0 | без роста |

Coverage и число сопоставлений совпадают в каждой bag/receiver/scenario-паре. Timeline counters `dropped=66`, `catchups=21` суммарно по clean+fault одинаковы у baseline и H07; они не объявляются нулевыми. Дополнительная заранее установленная проверка pooled≤0.5% и проверка отсутствия новых индивидуальных unrecovered проходят.

Исходные пороги v6: минимум 2% clean gain **или** 5% fault gain; регрессия каждой основной агрегированной метрики ≤0.5%, distance≤1%; per-bag/receiver clean рост≤max(0.005 м/с, 5%); без потери coverage, дополнительных false stops, unrecovered, resets или causality errors. **Кандидат не достигает минимального выигрыша и нарушает fault-ограничение.** Пороги не смягчены; улучшение дистанции не компенсирует отказ.

### Переходы и типы отказов — описательная диагностика

Маска переходов — первые 2 с после изменения режима controller (тяга / нейтраль / торможение), построенная по доступным прошлым stamps; reference matching и вычисление RMSE прежние. Эта дополнительная метрика не участвует в выборе параметров или замене acceptance gates.

| Участки / сценарий | Baseline RMSE | H07 RMSE | Изменение |
|---|---:|---:|---:|
| Переходы режимов | 0.096262343 | 0.096425856 | **+0.169861%** |
| Bias, 5 с | 0.414541580 | 0.414071154 | −0.113481% |
| Dropout, 5 с | 0.559015226 | 0.564413050 | **+0.965595%** |
| Dropout, 10 с | 0.723795502 | 0.728495561 | **+0.649363%** |
| Lock, 3 с | 0.456385335 | 0.461204992 | **+1.056050%** |

Основной интерес H07 — переходы и потеря колёс — не показал выигрыша в этих агрегатах.

## Per-bag сводка

Ниже описательное среднее двух receiver RMSE; fault — среднее доступных receiver/scenario RMSE внутри bag. **Это не замена group-macro основной приёмки.** Полные отдельные master/rover, faults, coverage, distance и recovery находятся в исходном [per_bag.csv](https://github.com/jabrailkhalil/hack/blob/55132ffc416485194be53c4d0b906d9dbc540d55/reports/research_H07/runs/36175112902/1/validation/per_bag.csv), JSON и локальной [сводке CSV](per_bag_summary.csv). «—» означает отсутствие reference, не нулевую ошибку.

| Bag | Clean base | Clean H07 | Fault base | Fault H07 | Distance base | Distance H07 |
|---|---:|---:|---:|---:|---:|---:|
| 30618_0686195f | 0.094311 | 0.094262 | 0.160501 | 0.160501 | 7.552468 | 7.545816 |
| 30618_2255aade | — | — | — | — | — | — |
| 30618_2dbce472 | 0.093861 | 0.093816 | 0.992143 | 0.992143 | 0.708050 | 0.707089 |
| 30618_2f104a1d | 0.049625 | 0.049574 | 0.386847 | 0.396498 | 0.321541 | 0.317786 |
| 30618_437e855c | 0.043146 | 0.043104 | 0.289176 | 0.280357 | 0.547513 | 0.543925 |
| 30618_49fe4c54 | 0.468767 | 0.468738 | 5.380667 | 5.380667 | 1.495664 | 1.492884 |
| 30618_4e1e3181 | — | — | — | — | — | — |
| 30618_68847170 | 0.038503 | 0.038484 | 0.127177 | 0.127177 | 0.510814 | 0.506636 |
| 30618_68d1748a | 0.234489 | 0.234380 | 0.125929 | 0.118301 | 2.186908 | 2.187345 |
| 30618_76e1f9c7 | 0.040773 | 0.040650 | 0.042993 | 0.043004 | 0.493058 | 0.486602 |
| 30618_7bfbb5ed | — | — | — | — | — | — |
| 30618_95c49c30 | — | — | — | — | — | — |
| 30618_b15eafc3 | 0.032751 | 0.032664 | 0.145063 | 0.147561 | 0.349707 | 0.346284 |
| 30618_b8044aa0 | 0.031913 | 0.031821 | 0.335008 | 0.309246 | 0.305043 | 0.303733 |
| 30618_defd0170 | 0.114305 | 0.114314 | 0.106889 | 0.097209 | 6.999488 | 6.994357 |
| 30639_3b3d9eb8 | 0.216188 | 0.215952 | 0.172273 | 0.172273 | 19.691925 | 19.677851 |
| 30639_50956d6e | 0.250266 | 0.250194 | 0.070148 | **0.223475** | 4.735680 | 4.713930 |
| 30639_9f0b519f | 0.038575 | 0.038506 | 0.330028 | 0.313121 | 6.772573 | 6.717438 |
| 30639_d601d28f | 0.109253 | 0.109223 | 0.470411 | 0.457232 | 15.587701 | 15.599102 |

### Существенные регрессии, не скрытые средним

На `30639_50956d6e` dropout 10 с (`110.5..120.5` с) event RMSE master растёт **0.087056790 → 0.457076565 м/с**, rover **0.086758940 → 0.457937781 м/с**: абсолютный рост около 0.37 м/с, относительный +425..428%. При dropout 5 с: master **0.077536285 → 0.237213094**, rover **0.075012589 → 0.236048886**. При lock 3 с: master **0.083810987 → 0.169658724**, rover **0.080561466 → 0.168540872**.

На этих dropout-сценариях recovery замедляется с **0.047966 до 0.197966 с**, при lock — до **0.247966 с**. Невосстановлений нет, но задержка восстановления действительно выросла. Точная физическая причина этой локальной регрессии по сохранённым агрегатам не установлена; не выдаём предположение о связи с disturbance за экспериментально доказанный механизм.

На clean ухудшился только `30618_defd0170` у обоих receiver: максимальный рост RMSE **0.000010725 м/с** (master, +0.00938%), ниже per-bag порога. Средняя по receiver distance немного хуже у `30618_68d1748a` и `30639_d601d28f`; исходные значения сохранены выше. Большое историческое fault RMSE `30618_49fe4c54` не удалено из выборки и не приписано H07: оно одинаково у обоих алгоритмов.

## Фактически выполненные проверки

[Исследовательский workflow](https://github.com/jabrailkhalil/hack/actions/runs/36175112902): `compare` и `candidate-ros-offline` завершились success. Это успех выполнения исследования, **не принятие гипотезы и не зелёный общий CI**.

| Проверка | Фактический результат |
|---|---|
| `tests/test_core.py` | 22/22 PASS |
| `research/H07/test_actuator.py` | 10/10 PASS; локально также повторено |
| Побитовое совпадение отключённого H07 с точным baseline core | 6000 синтетических шагов в составе H07 tests |
| `research/tests` | 30/30 PASS |
| Полный неизменный `tests` | **66 PASS, 4 FAIL из 70** |
| Compile изменённых Python источников | PASS в H07 workflow и локально |
| Пиннинг архива / split / DB, роль train/validation | PASS; журналы сохранены |
| Реальные train + paired validation | завершены, raw evidence сохранены |
| Установленный выбранный профиль, ROS без сети, 2 CPU / 500000000 bytes | PASS: 38 параметров, 120 outputs, 20.000 Гц |
| Дополнительные ROS adapter/fault и CDR checks в том же контейнере | PASS; они используют обычные test-конфигурации, не выдаются за fault benchmark выбранного профиля |

Четыре FAIL исходного набора: `test_active_source_hashes_are_pinned_separately`, `test_current_default_is_the_selected_profile`, `test_rejected_experimental_runtime_is_not_deployed`, `test_only_adaptation_changes_from_main`. Они требуют старые байты/hashes core или точное совпадение прежнего набора полей Config; два новых поля по умолчанию 0 нарушают строгую schema equality. **Тесты не изменены, опубликованные манифесты не переписаны.** Обычный [CI исходников](https://github.com/jabrailkhalil/hack/actions/runs/36175112880) поэтому завершился failure в job `core`; `research-integrity`, `ros-humble`, `offline-limited` прошли. H07 workflow лишь сохраняет полный журнал этих отказов через continue-on-error, а требуемые mechanism/core tests выполняет отдельным обязательным шагом.

В [сохранённом ROS-логе](ros-offline.log) есть `KeyboardInterrupt`/exit -2 при намеренном SIGINT-завершении запущенной ноды после успешного smoke. Это видимый недостаток чистоты завершения; успешные assertions его не скрывают. Smoke проверяет выбранные параметры и публикацию при постоянной скорости, а не real-bag transient accuracy или длительную устойчивость.

Новый полный длительный real-bag ROS latency/RSS benchmark H07 **не выполнен**. Ограниченный контейнерный smoke не доказывает p95/p99 latency, hard real-time или весь runtime контракт. Исторические числа v4/v5 не перенесены на H07.

## Команды и воспроизведение

Фактически выполненные ключевые команды в исходном workflow (Python 3.13.5, NumPy 2.3.5, SciPy 1.17.0; OMP/OPENBLAS по одному потоку):

```bash
python -m pip install -r requirements-research.txt
PYTHONPATH=src/reserve_odometry python -m unittest discover -s tests -p test_core.py -v
PYTHONPATH=src/reserve_odometry python -m unittest discover -s research/H07 -p test_actuator.py -v
PYTHONPATH=src/reserve_odometry python -m unittest discover -s tests -v
python -m unittest discover -s research/tests -v
python -m compileall -q src tools/research_h07 research/H07
python tools/get_dataset.py

H07_RUN=reports/research_H07/runs/36175112902/1
python tools/research_h07/run.py --stage train --output "$H07_RUN/train"
# Затем отдельный git commit + push train freeze, до следующей команды.
python tools/research_h07/run.py --stage validate \
  --frozen "$H07_RUN/train/selected.json" \
  --freeze-commit 1e00925e75a7e5aa488578cfa853f336a2a5dde3 \
  --output "$H07_RUN/validation" --workers 2
```

Полный порядок, tee-логи и docker-команды: [измеренная версия workflow](https://github.com/jabrailkhalil/hack/blob/ca96f620274ba24c82e1258e953bfb7bd1b40fe4/.github/workflows/research-h07.yml). Команда полного `tests` выше **завершается с ошибкой**, это не рецепт игнорировать её в production.

Для повторной оценки уже замороженного кандидата без повторного подбора и без перезаписи результатов:

```bash
git fetch origin checkpoint/H07-36175112902-1
git worktree add --detach ../hack-H07-replay 1e00925e75a7e5aa488578cfa853f336a2a5dde3
cd ../hack-H07-replay
python3.13 -m venv .venv-h07
. .venv-h07/bin/activate
python -m pip install -r requirements-research.txt
python tools/get_dataset.py
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
RUN=reports/research_H07/runs/36175112902/1
OUT="reports/research_H07/replays/$(date -u +%Y%m%dT%H%M%SZ)"
python tools/research_h07/run.py --stage validate \
  --frozen "$RUN/train/selected.json" \
  --freeze-commit 1e00925e75a7e5aa488578cfa853f336a2a5dde3 \
  --output "$OUT" --workers 2
```

Эта последняя последовательность — инструкция воспроизведения, а не заявление о втором уже выполненном real-data прогоне. Для нового train-повтора использовать те же шесть вариантов, новый каталог/собственную checkpoint-ветку и обязательный commit freeze перед validation; не расширять поиск на основании данного validation.

После сборки исходников H07 профиль запускается явно через сохранённый `train/selected.yaml`:

```bash
ros2 launch reserve_odometry odometry.launch.py \
  params_file:="$PWD/reports/research_H07/runs/36175112902/1/train/selected.yaml"
```

Этот файл присутствует в указанном freeze/checkpoint, а не автоматически в чистом checkout исследовательской ветки. Стандартный default остаётся adaptive_v5 с отключёнными новыми полями.

## Артефакты и ограничения

[Все train/validation JSON, CSV и логи, immutable commit](https://github.com/jabrailkhalil/hack/tree/55132ffc416485194be53c4d0b906d9dbc540d55/reports/research_H07/runs/36175112902/1). [Полные исходные validation-результаты](https://github.com/jabrailkhalil/hack/blob/55132ffc416485194be53c4d0b906d9dbc540d55/reports/research_H07/runs/36175112902/1/validation/results.json). [Решение](https://github.com/jabrailkhalil/hack/blob/55132ffc416485194be53c4d0b906d9dbc540d55/reports/research_H07/runs/36175112902/1/validation/decision.json). Train JSON сохраняет все шесть альтернатив и контроль, включая per-bag fitting metrics, а не только победителя.

GitHub artifacts: `H07-36175112902-1` (ID 10882410769, SHA256 `70e250f8add6d790234adbf1f28262bdbe4d70f49eb578e1116b7cdb93ff3c31`) и `H07-ROS-36175112902-1` (ID 10881787267, SHA256 `977bd1ec61e82182b0a6ac59f22f5e9b1c4afa3a4f8d2a49f45f2a12bfb83161`). Оба архива скачаны и их SHA256 дополнительно проверены локально. В отличие от временных artifacts, checkpoint сохраняет raw train/validation evidence в Git.

Ограничения: повторно используемый validation, wheel-only псевдоразметка и common-mode slip; грубая сетка без continuous fitting; только лаг реакции на текущую команду, не отдельный release/hysteresis; offline training approximation не идентифицирует всю связку с disturbance; relative 1D distance, не xyz/ENU; wheel scale 1/3.6 всё ещё требует подтверждения; нет независимого нового final test, сертификации безопасности и длительного H07 latency benchmark.

**Итог: оставить baseline adaptive_v5. H07 T10_B05 — воспроизводимый отрицательный исследовательский результат, не merge-кандидат.**
