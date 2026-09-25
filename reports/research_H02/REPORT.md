# H02: неопределённость возраста и рассинхронизации — отрицательный результат

## Решение

**Проверенный кандидат `H02_timing_05` отклонён: `insufficient_gain`. Не готов к merge.** На реальных validation-записях clean group-macro RMSE улучшился только на 0.106579%, а fault-event group-macro RMSE ухудшился на 0.088055%. Ни требуемого clean gain ≥2%, ни fault gain ≥5% нет. Пороги допустимых регрессий не нарушены, но это не заменяет минимальный выигрыш.

Это отрицательный результат одного заранее выбранного механизма и коэффициента, не доказательство невозможности всего семейства R(age, skew, confidence). Параметры и алгоритм после validation не менялись. Baseline `adaptive_v5` сохранён; merge/auto-merge не выполнялись.

## Происхождение результата

| Объект | Идентификатор |
|---|---|
| Общий baseline | `984fdf2fc4faf05325249215d6b8541c0e68209a` |
| Профиль baseline | `src/reserve_odometry/config/adaptive_v5.yaml` |
| Рабочая ветка | `research/parallel-H02` |
| Предварительный протокол | `0dc1476089884ebf89da7671e3fb155a056549bc` |
| Реально исполненный source commit | `49b659b6f55469cbf37b8ce597a414d32997c7ec` |
| Freeze commit ДО validation | `c248e425a40a40408b255d0b9a8afea3b45456ff` |
| Итоговый checkpoint commit | `aa04d249896ea66f793029c22b356a0cbf782a9a` |
| GitHub Actions run / attempt | `36174637237 / 1` |
| Job | `108202148790`, завершён success |
| Draft PR | [#15](https://github.com/jabrailkhalil/hack/pull/15) |

[Реальный прогон](https://github.com/jabrailkhalil/hack/actions/runs/36174637237) выполнялся в GitHub Actions, Ubuntu 22.04, Python 3.13.5, NumPy 2.3.5, SciPy 1.17.0; OPENBLAS_NUM_THREADS=1, OMP_NUM_THREADS=1, два validation workers. Измеренное время validation runner — 49.751641084 с; это offline compute, не ROS latency или время движения.

Freeze создан **25 сентября 2026, 18:39:24.619906 UTC** и сохранён отдельным коммитом до открытия validation. Train завершён в 18:39:23.534160 UTC. Итоговый results.json создан в 18:40:17.087816 UTC. Коммит этого отчёта добавляет только evidence; он не подменяет измеренный source commit.

## Механизм: один вариант, без настройки на validation

Сначала изучены отрицательные результаты `reports/research_v6/REPORT.md` и `reports/research_v5/REPORT.md`. Перенос измерений в v6 улучшал clean, но нарушал fault-регрессию; увеличение process noise в v5 также могло ухудшать fault и добавлять ложные остановки. H02 не переносит измерения, не меняет Q и не ослабляет gate.

[Протокол](../../research/H02/PLAN.md) зафиксирован до экспериментов. Ровно один кандидат: `timing_accel_fraction=0.5`, выбран априорно, без подбора по записям. Для принятого набора колёс:

```
A = max(max(0, now - sample.t) for accepted samples)
S = abs(front.t - rear.t) if both accepted else 0
sigma_a = 0.5 * max_accel_mps2
R = [sigma_wheel² + sigma_a² * (A² + S²/4)]
    * confidence_factor * residual_factor
```

`confidence_factor=1` для двух принятых согласованных колёс, иначе 4; `residual_factor=max(1, abs(z-predicted)/(3*sigma_wheel))`. Эти множители остаются исходными из baseline. **Нет деления R на число колёс.** Согласованность пары не означает независимость ошибок. Измерения, их арифметическое среднее z и stamps не изменяются. Добавка R — консервативная эвристика, не статистически откалиброванная covariance.

[Реальный патч core.py](../../research/H02/algorithm.patch) применяется к изолированной копии через [build_candidate.py](../../research/H02/build_candidate.py). Именно полученный core выполнялся на реальных записях. Активный runtime/default не заменён исследовательским кодом. При default `timing_accel_fraction=0` поведение baseline сохраняется; candidate profile включает 0.5. Дополнительных сохраняемых состояний нет.

Bootstrap, gate, stop, recovery, disturbance adaptation и временная логика непосредственно не редактируются. Изменение веса, однако, меняет состояние/covariance и может косвенно изменить следующие gate/adaptation/stop решения; это не обещание идентичного поведения.

## Данные и неизменный evaluator

Train: 64 записи, воспроизведены первые не более 180 секунд каждой; 406293 входных события, 208014 выходных ticks на модель. Store.load(train) открывает только `/vehicle/driver_position_cmd`, `/vehicle/front_bogie_velocity`, `/vehicle/rear_bogie_velocity`. GNSS-reference на train не читается, proxy-точность по самим колёсам не выдаётся за независимую оценку. Выполнены проверки расписания, причинности и disabled-baseline, а не обучение коэффициентов.

Validation: **19 bag, 10 групп; reference имеется в 9 группах и 30 bag/receiver-парах.** Все четыре записи без reference сохранены как missing, не как нулевая ошибка: `30618_2255aade`, `30618_4e1e3181`, `30618_7bfbb5ed`, `30618_95c49c30`. Оба GNSS-приёмника master/rover используются только evaluator, не алгоритмом.

Реально выполнены **76 fault-сценариев, 120 сравнений с reference**. Не менялись исходные v6 anchor, входные окна, bias 5 с, dropout 5/10 с, lock 3 с, reference masks и recovery definition. Возраст и рассинхронизация проверены такими, какими они встречаются в исходном replay; дополнительные искусственные delay/skew sweeps в этом раунде не добавлялись.

[Runner](../../research/H02/run.py) вызывает исходный `tools/research_v6/compare.py::validate_bag`, исходные score/replay/match/metrics/distance и summary/decide. Подмена ограничена factory алгоритма и конфигурациями. Pristine baseline исполняется исходным классом Observer; кандидат — отдельно сгенерированным классом. Третья модель v4 служит точному воспроизведению опубликованных baseline, не альтернативой знаменателю H02: всё решение относится к v5.

Все защищённые исходники, runtime, конфигурации, split и evaluator проверены против точного baseline через git show и SHA256. **468 опубликованных числовых полей v4/v5 воспроизведены точно: maximum absolute delta = 0.0.** Расписания совпадают, rate=20 Hz, alignment_delay=0. Реальных test-payloads загрузчик не открывал и final test не оценивался. Загрузчик архива штатно распаковывает исходный датасет целиком; это не означает использования его test-измерений при разработке или оценке.

## Агрегированные результаты

Изменение ошибки = 100 × (candidate / baseline − 1); отрицательное значение означает улучшение.

| Метрика | Baseline adaptive_v5 | H02_timing_05 | Изменение |
|---|---:|---:|---:|
| Clean group-macro RMSE, м/с | 0.11713827416709652 | 0.11701342891137327 | −0.106579% |
| Fault-event group-macro RMSE, м/с | 0.5384344108523412 | 0.5389085306222027 | **+0.088055%** |
| Pooled clean RMSE, м/с | 0.2167236028496654 | 0.2167221593263994 | −0.000666% |
| Scalar span distance group-macro RMSE, м | 4.63097780847452 | 4.593252344986985 | −0.814633% |
| Сопоставленные clean points | 698891 | 698891 | одинаково |
| False-stop samples, clean | 18 | 18 | одинаково |
| False-stop samples, fault | 0 | 0 | одинаково |
| Fault comparisons без recovery | 0 | 0 | одинаково |
| Causal errors, clean / fault | 0 / 0 | 0 / 0 | одинаково |
| Resets, clean / fault | 0 / 0 | 0 / 0 | одинаково |

Distance — переякоренная скалярная ошибка на непрерывных GNSS-speed отрезках, не XYZ/ENU и не полный terminal drift. Её улучшение не заменяет clean/fault критерий приёмки.

## Регрессии не скрыты за агрегированием

Из 30 bag/receiver clean-сравнений 17 улучшились, **13 ухудшились**. Ни одно не превышает исходный clean per-bag gate baseline + max(0.005 м/с, 5%). Из 120 fault-event сравнений 38 улучшились, **82 ухудшились**. Distance ухудшилась в 6 из 30 bag/receiver-пар.

| Локальный случай | Baseline | Candidate | Изменение |
|---|---:|---:|---:|
| Clean, 30618_49fe4c54 / master | 0.0376523507 м/с | 0.0387883161 м/с | +0.0011359654 м/с; +3.016984% |
| Clean, 30639_3b3d9eb8 / master | 0.2157022100 м/с | 0.2161225606 м/с | +0.0004203506 м/с; +0.194875% |
| Clean, 30639_3b3d9eb8 / rover | 0.2166731171 м/с | 0.2170778940 м/с | +0.0004047769 м/с; +0.186815% |
| Bias 5 с, 30639_d601d28f / master | 0.2025928177 м/с | 0.2130056770 м/с | +0.0104128593 м/с; +5.139797% |
| Bias 5 с, 30639_d601d28f / rover | 0.2021534395 м/с | 0.2125465623 м/с | +0.0103931228 м/с; +5.141205% |
| Bias 5 с, 30639_9f0b519f / rover | 0.0496301614 м/с | 0.0530976836 м/с | +6.986723%, наибольшая относительная fault-регрессия |
| Dropout 10 с, 30618_68847170 / rover | 0.2798836734 м/с | 0.2876667477 м/с | +0.0077830743 м/с; +2.780825% |
| Distance, 30618_49fe4c54 / master | 0.4875662852 м | 0.5179371302 м | +0.0303708450 м; +6.229070% |

Дополнительно восстановление замедлилось в трёх сравнениях одной записи `30639_d601d28f`: dropout 10 с / rover 0.342441→0.642441 с; lock 3 с / rover 0.192441→0.492441 с; dropout 10 с / master 0.542441→0.742441 с. Невосстановлений не добавилось, но отсутствие роста их количества не означает неизменную скорость восстановления.

Перечисленные локальные fault/distance проценты не подменяют агрегированные ограничения: в исходном контракте per-bag порог задан для clean speed, а distance 1% — для агрегата. Новые удобные пороги не вводились. Полные значения всех случаев, включая остальные ухудшения, доступны в per_bag.csv и исходных bag JSON.

## Проверка неизменных критериев

| Критерий | Результат |
|---|---|
| Clean gain ≥2% ИЛИ fault gain ≥5% | **FAIL**: 0.106579% / −0.088055% |
| Clean / fault aggregate regression ≤0.5% | PASS |
| Pooled RMSE regression ≤0.5% | PASS |
| Distance aggregate regression ≤1% | PASS |
| Clean per-bag/receiver regression ≤max(0.005 м/с, 5%) | PASS |
| Идентичные n/coverage по каждому сравнению | PASS |
| Нет дополнительных false stops / unrecovered | PASS |
| Нет causal errors / resets / изменения расписания | PASS |
| Реальный ROS benchmark включённого H02 под 2 CPU / 500 MB | **НЕ ВЫПОЛНЕН** |

Порог pooled RMSE явно добавлен в wrapper как заранее предусмотренное требование пользователя: исходная decide v6 сама его не проверяла. Измеритель метрики не менялся и порог не смягчался. Автоматическая причина отклонения — только `insufficient_gain`. Невыполненный ROS benchmark дополнительно запрещает объявлять runtime-кандидат готовым к эксплуатации; он не нужен для вывода об уже проваленном accuracy gate.

## Фактически выполненные проверки

В успешном исследовательском job пройдены **70 baseline unit tests, 13 H02 structural/unit tests, 30 research-integrity tests**, compileall, SHA256 архива/каждого открытого bag, train replay всех 64 записей и полный указанный validation/fault replay. H02 tests включают формулу R, возраст/skew, confidence, отсутствие R/N, неиспользование future/stale/duplicate samples, влияние только принятых колёс, 6000 шагов точного совпадения disabled с pristine baseline и 10000 шагов проверки неизменного размера состояния.

На реальном train replay disabled также точно совпал с baseline, включая runtime counters; candidate сохранил schedule и причинность. Эти train/unit проверки не выдаются за улучшение точности.

Локальный git clone/ls-remote был недоступен из-за DNS `Could not resolve host: github.com`. GitHub connector обеспечил чтение/запись, а GitHub Actions — реальные данные и исполнение. Это ограничение локальной среды не помешало validation. Локальные 13 H02 tests также прошли против core, проверенного по Git blob SHA. Частота 20 Hz здесь подтверждена расписанием offline replay; **publisher/subscriber p95/p99 latency, wall-clock frequency, RSS и CPU включённого кандидата не измерены**. Проверки старого/default ROS не приписываются H02.

## Воспроизведение

```bash
git checkout 49b659b6f55469cbf37b8ce597a414d32997c7ec
python -m pip install -r requirements-research.txt
python tools/get_dataset.py
PYTHONPATH=src/reserve_odometry python -m unittest discover -s tests -v
python research/H02/test_h02.py
python -m unittest discover -s research/tests -v
python -m compileall -q research/H02
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
OUT=/tmp/h02-fresh-run
python research/H02/run.py --stage train --output "$OUT"
python research/H02/run.py --stage freeze --output "$OUT"
# Сохранить FREEZE.json неизменным до открытия validation.
# В измеренном workflow выполнен отдельный checkpoint commit c248e425... .
python research/H02/run.py --stage validation --output "$OUT" --workers 2
```

Runner отказывается перезаписывать output и изменять source/config после freeze. Повтор — проверка воспроизводимости, а не новая независимая выборка и не разрешение подбирать параметры на validation. Автоматический workflow записывает run_id/run_attempt и работает только в своей research/checkpoint-ветке.

## Исходные артефакты и ограничения вывода

[FREEZE](runs/36174637237-1/experiment/FREEZE.json), [train](runs/36174637237-1/experiment/train.json), [исходный results.json](runs/36174637237-1/experiment/validation/results.json), [decision.json](runs/36174637237-1/experiment/validation/decision.json), [aggregate.csv](runs/36174637237-1/experiment/validation/aggregate.csv), [per_bag.csv](runs/36174637237-1/experiment/validation/per_bag.csv), [bag checkpoints](runs/36174637237-1/experiment/validation/bags/), [access](runs/36174637237-1/experiment/validation/access.json), [исполненный candidate core](runs/36174637237-1/experiment/candidate_core.py), [candidate YAML](runs/36174637237-1/experiment/candidate.yaml).

Эти файлы перенесены из checkpoint-дерева без пересчёта и без merge. Полный ZIP артефакт **H02-36174637237-1**, id **10882275766**, содержит также полные `.log` файлы: gitignore исключил их из checkpoint, но Actions upload сохранил. ZIP скачан и проверен: **182966 байт**, SHA256 `5552a4a0ebb920f32b5667fb1fe0bb3e68352c16f177906a1999922840ffde57`. Срок хранения Actions artifact — до 25 октября 2026; JSON/CSV остаются в Git. Отдельные локальные скачиваемые копии ZIP/patch/CSV предоставлены в ответе.

Ключевые SHA256:

- Исходный core: `780ca4796d86b4fa4e8c8679abfb73f58f23e003d4ee644ba964ffdeac9f0bfc`.
- Исполненный candidate core: `07ab2334f447c4b4a0412f570cae601f40953b7994e798503ecdbcbffcacc2aa`.
- evaluate.py: `f6a19a1727274ca88e1fe1a9fb76d31dbc8ce4e9bbabf669c488f053d76caec7`.
- v6 compare.py: `70276a0a633cd443d44af870fde73649519be2aaf55944c2a4473c82d7b241b5`.
- FREEZE.json: `d5e08db5d4dd1178c62030b57356eaff4676c321c0458a4135de2d364965e720`.

Validation использовался в прошлых раундах и не является независимым final test. Единственный коэффициент выбран априорно; другие варианты этой гипотезы не проверялись. R не устраняет ненаблюдаемую common-mode ошибку пары. Для одиночного принятого колеса S=0; отдельная межтиковая память рассинхронизации не добавлена. Единицы колёс 1/3.6 и относительная скалярная одометрия наследуют ограничения baseline.

К моменту создания PR main уже был `efc473e415795d64770ef9dfa4f1bc417078da32`, на пять коммитов впереди baseline. H02 сравнивался только с общим закреплённым SHA, без смешивания раундов. Превосходство над изменившимся main не заявляется. Для этого отклонённого кандидата повторный подбор или попытка продвижения не выполнялись.
