# R3-H24 — REJECTED: монотонная статическая карта команды

**Исследовательский отрицательный результат, не готов к merge.** Оба заранее объявленных варианта отвергнуты на development. При λ=0.1 clean gain составляет только 0.063622% вместо требуемых 2%, original fault RMSE ухудшился на 0.289510%. При λ=1 original fault RMSE вырос на 6.237717% при допуске 0.5%; нарушен также предварительный coast-veto. Validation и final test не запускались; FREEZE для validation не создавался. После результатов карты и параметры не изменялись.

Это завершение ранее начатой работы в той же ветке, не новый эксперимент и не присвоение чужой ветки. Существование и происхождение research/R3-H24 проверены до продолжения; второго PR или ветки с суффиксом не создаётся.

## Статусы и идентификаторы

```json
{"mechanism_status":"IMPLEMENTED_AND_ACTIVE","coverage_status":"PASS","scientific_verdict":"REJECTED","accuracy_contract_passed":false,"runtime_verified":false,"ready_to_merge":false}
```

| Что | SHA / значение |
|---|---|
| Round / ветка | R3-v8-fixed / research/R3-H24 |
| Единый baseline | e3b0c9c039d2953fbfcda51231263d38ef9f1024 |
| Preflight source | 23bd3bc06496dc9deea5b50a4ee8498737ec4c29 |
| PLAN до fitting | 2e45d40b65fad761824ace50f123e6632d9e46ec |
| Измеренный алгоритм, tests, fitting/development driver | 6b3a11a68b83ee7b680b3b283f4800726c7b84cd |
| Отдельное уточнение steady-cost, без refit | 5a694cc01762a6cd9c78932e3eace4084074afb3 |
| Validation freeze | N/A — кандидат не допущен |
| Поздний отчёт | commit, содержащий этот REPORT/SUMMARY; указан отдельно в PR |

PLAN опубликован 26.09.2026 в 05:17:03 UTC, до fitting. SHA256 PLAN: `2fc808115ac39306fdfaae7f2aaf89e8dba9bae7941621c3e83c3d7b6da8bb08`. Реальный baseline — GuardedReadoutObserver с champion_v8.yaml и canonical guarded_odometry_node. Проверяются возвращаемые Estimate.v/s, 20 Hz, delay=0, gain=1, holdoff=0.5, adaptation_tau=0.5, wheel_time_compensation=0, common_mode_quarantine=1.5. Остальная физика взята из точного профиля, не Config defaults. Движущийся main не подмешивался.

## Механизм и границы патча

Новый `src/reserve_odometry/reserve_odometry/command_map.py` заменяет только статическое q=x^gamma, где x=clip((abs(u)-deadband)/(1-deadband),0,1). Пять узлов x=(0,.25,.5,.75,1); q(0)=0, q(1)=1. Три внутренних значения обучаются отдельно для тяги и торможения. Между узлами линейная интерполяция. Вне диапазона — фиксированные endpoints. Feature-off делегирует исходному drive_target и вычисляет исходную степень, а не табличное приближение.

Force/power saturation, actuator_tau, сопротивление, disturbance adaptation, covariance, raw/model/stop/recovery gates, v8 zero-lock/quarantine, readout и Timeline унаследованы без изменения. Runtime получает только controller/front/rear; нет GNSS/IMU, bag ID, fault-kind/duration или будущих samples. Дополнительная память — две неизменяемые тройки и конфигурация; нет новой истории/очереди или научных runtime-зависимостей.

Canonical launch не переключён: один checkout сам по себе не включает карту. Fitting/development создают CommandMapObserver с точными model/readout параметрами и CommandMap(enabled=True). Отдельного установленного enabled ROS-adapter эта работа не выпускала.

| Узел x | Исходная степень, обе стороны | λ=.1 тяга | λ=.1 тормоз | λ=1 тяга | λ=1 тормоз |
|---|---:|---:|---:|---:|---:|
| 0.25 | 0.485826645 | 0.502250803 | 0.415534759 | 0.487339041 | 0.479572236 |
| 0.5 | 0.697012657 | 0.701656602 | 0.492390861 | 0.697182643 | 0.645865846 |
| 0.75 | 0.860872823 | 0.870663566 | 0.775516324 | 0.861460908 | 0.848185635 |

SHA256 исполненного модуля: `87d14028429883b24b2b5fdc4ea110966639ce2cb1a4614e61491faaa8b2c073`. SHA256 полных fitted JSON: λ=.1 — `80fd5462fa739dd9556ac1673c6145a47575b44b99553ad0f5a69fde7b3c5324`; λ=1 — `4d46695bb8b1605d4ff9c446c586614edf62709ec76e0da66767363b86b21b54`. Компактные копии без per_window в checkpoint имеют иной файловый хеш; это не изменение узлов.

## Основание, train и ограниченный fitting

До большого патча выполнен preflight всех 64 train bags из 27 исходных групп. Правило разделения по SHA256 группы закреплено заранее: 20 fitting / 7 check групп. Шесть внутренних узлов прошли структурный coverage gate: каждый представлен минимум в 17 fitting и 6 check группах, с 6–7 различными амплитудами. Для каждого узла требовались hat-basis>=.1 не менее 5 секунд в >=3 fitting / >=2 check группах, >=2 амплитуды, >=20 секунд суммарно. Матрица амплитуд имеет ранг 3 на каждой стороне. Это не статистическая независимость ticks и не доказательство физической идентифицируемости.

На FUSED train-данных колёсно-производный acceleration residual при тяге x<.25 имел отрицательное среднее во всех 24 представленных группах (macro −0.1095195 м/с²); для x в [.5,.75) — положительное в 22/23 группах (+0.0604750). Это основание проверить форму карты, но residual может содержать возраст измерений, actuator history, slip и ошибку disturbance. Причина model mismatch этим не изолирована.

Выбраны 205 детерминированных окон с прошлым 5-секундным warmup и последующим command-only прогнозом: 154 fitting в 18 группах, 51 check в 6 группах. Остальные группы не исключены из split: в них не оказалось подходящих окон. Горизонты .5/2 с, scales .2/.5 м/с, одинаковый безразмерный robust loss с group balancing. Будущие колёса — только offline псевдоцель; команды подаются последовательно на своих тактах, а не заранее в начальное состояние. Train GNSS не читался.

Ровно один bounded scipy least_squares/TRF fit на λ=.1 и на λ=1, max_nfev=80, без restarts. Monotone параметризация: q1=a; q2=a+(1−a)b; q3=q2+(1−q2)c, a,b,c∈[0,1]. Penalty=λ·mean(((q−q_prior)/.25)^2); H22 penalty/H17 delays не вводились. λ=.1 завершился с nfev=23, njev=14, 107 фактическими вызовами objective, включая finite differences; λ=1 — 6/6/42. Обе оптимизации success. Локальный data-only Jacobian без penalty имеет ранг 6, singular values 13.9188, 7.0414, 5.3791, 3.7266, 1.6216, 1.6124; это локальная чувствительность, не глобальная идентифицируемость.

| Check pseudo-RMSE, group-balanced, м/с | Baseline .5/2 с | λ=.1 .5/2 с | λ=1 .5/2 с |
|---|---:|---:|---:|
| all | 0.112353/0.533344 | 0.110130/0.496071 | 0.111657/0.520347 |
| traction | 0.051537/0.169935 | 0.050381/0.158356 | 0.050162/0.156937 |
| braking | 0.157160/0.770358 | 0.150679/0.701891 | 0.154578/0.745410 |
| coast | 0.071597/0.306510 | 0.094002/0.398812 | 0.086088/0.367587 |

Более низкая общая proxy loss не равна выигрышу одометрии: у λ=.1 check-coast на 2 с ухудшился .306510→.398812 м/с. Диагностические braking-числа .166012/.815428 в PLAN — pooled по check-окнам; приведённые здесь .157160/.770358 используют заранее описанный group-balanced fitting summary. Предсказания baseline между preflight и fitting совпали точно (max abs delta=0), метрика отбора development не менялась.

## Неизменный evaluator и реальный development

Исполнены все 17 исходных development bags / 7 групп. Reference доступен в 6 группах / 19 bag-receiver парах; 7 bags без обоих receivers и ещё один без master сохранены как missing. 394221 сопоставленная точка. На 14 bags исходное vehicle-only anchor правило допускает 56 original fault-сценариев / 60 сравнений с reference в 5 группах: front bias +5 м/с на 5 с, both dropout 5/10 с, both lock 3 с. Missing не считается нулевой ошибкой.

Без изменений вызываются evaluate.score/replay, matching/metrics/distance и v6 group aggregation; original anchors взяты из исходного guarded runner. Добавлены только factory и role-checked read-only development loader. Baseline с прямой factory независимо повторён official scorer на каждом из 17 clean bags: все общие metrics/runtime совпали. Feature-off сравнивает весь исходный observer state и Estimate на каждом такте; расписание baseline/candidate проверяется для всех suites. Post-run audit воспроизвёл decision (85 leaves) и 3011 metric leaves baseline/off плюс все runtime-словари.

При возобновлении 47 защищённых baseline/evaluator/profile файлов пользовательского архива совпали с исходным манифестом; также сверены 5 candidate pins и 26 файлов evidence manifest. ZIP сам не заменяет git ancestry. Исследование продолжено в существующей собственной ветке без refit/нового accuracy-run.

## Основные метрики

Минус в изменении ошибки означает улучшение.

| Метрика | Baseline v8 | λ=.1 | Δ, % | λ=1 | Δ, % |
|---|---:|---:|---:|---:|---:|
| Clean group-macro RMSE, м/с | 0.092668143 | 0.092609186 | -0.063622 | 0.092677760 | +0.010378 |
| Original fault-event RMSE, м/с | 0.237548612 | 0.238236338 | +0.289510 | 0.252366221 | +6.237717 |
| Pooled clean RMSE, м/с | 0.129305694 | 0.129227299 | -0.060628 | 0.129353888 | +0.037271 |
| Scalar span distance RMSE, м | 5.310295005 | 5.268492511 | -0.787197 | 5.258744660 | -0.970762 |

Matched clean points 394221 у всех; false-stop samples clean/original — 0/0; original unrecovered — 4 у всех. Ни одного нового индивидуального невосстановления, causal error, unexpected reset или coverage loss. Четыре baseline unrecovered — 30639_e4379d7f/rover во всех четырёх original faults; они не скрыты средним recovery.

| Дополнительная метрика | Baseline | λ=.1 | λ=1 |
|---|---:|---:|---:|
| Clean group-macro MAE, м/с | 0.034933353 | 0.034977942 | 0.035019782 |
| Clean signed bias, м/с | 0.006390677 | 0.006434649 | 0.006163721 |
| Fault+recovery window MAE, м/с | 0.153796529 | 0.141614451 | 0.148059556 |
| Fault+recovery window signed bias, м/с | 0.011170308 | 0.069427240 | 0.042753243 |
| Recovery group-macro, с; только определённые | 0.724358285 | 0.619670785 | 0.625920785 |

Coverage целевого изменения PASS у обоих: target меняется на 185548/185546 тактах в 7 группах; published v — на 218162/218058 тактах, с изменениями в 6 reference-bearing группах. Условия >=100 изменённых target/output ticks и >=3 соответствующих групп выполнены. Это не неактивный механизм, как в H14.

## Почему оба кандидата отвергнуты

Предварительный R3 admission требует >=2% clean gain ИЛИ >=5% ORIGINAL fault gain, aggregate clean/fault/pooled regression<=.5%, distance<=1%, clean per-bag<=baseline+max(.005 м/с,5%), без потери masks/coverage, новых false stops/individual unrecovered/causality/reset. Дополнительно: traction/braking/coast phase-regression<=.5%; две v8 safety suites event-macro regression<=.5% без новых safety failures.

λ=.1: `insufficient_gain`. λ=1: `insufficient_gain`, `aggregate_regression:fault_rmse`, `side_phase_regression:coast`. Clean phase изменения: traction −0.402671%/−0.418971%; braking −0.254675%/+0.045956%; coast **+0.452372%/+0.519827%** для λ=.1/1 соответственно. Последнее превышает .5% только у λ=1. Пороги не пересматривались; selected=null. Выигрыш дистанции или отдельной fault suite не заменяет обязательный gain.

## Существенные локальные и режимные регрессии

Clean RMSE вырос в 7/19 пар у каждого варианта, но per-bag gate не нарушен. Худшее абсолютное ухудшение λ=.1: 30639_9c362687/master, .078329692→.079009622 м/с (+.000679930). Original event RMSE ухудшился в 35/60 сравнений λ=.1 и 31/60 λ=1.

| Сценарий | Baseline, м/с | λ=.1 | λ=1 |
|---|---:|---:|---:|
| 30639_dce52be4/master, original dropout 10 с | 0.227959065 | **0.757391180 (+232.249%)** | **0.657894528 (+188.602%)** |
| 30618_0652866c/master, original lock 3 с | 0.046097060 | **0.214747210 (+365.859%)** | **0.201202732 (+336.476%)** |

Локальная дистанция может ухудшаться при хорошем агрегате: 30639_0ab96c59/master .110114684→.123007592 м (+11.709%) для λ=.1 и →.124828628 м (+13.362%) для λ=1. Дистанция выросла в 6/19 и 10/19 пар соответственно. Recovery замедлилось в 4/56 и 3/56 определённых original comparisons, максимум +.15 с (30618_0652866c/master, lock), хотя group-macro recovery улучшился.

В заранее заданной дополнительной диагностике dropout 5 с начинается через .5 с после первого допустимого перехода команды. Это 41 событие / 49 reference comparisons, НЕ original admission. По отдельным фазам:

| Dropout после перехода | Baseline event RMSE | λ=.1, Δ | λ=1, Δ |
|---|---:|---:|---:|
| traction | 0.354071148 | 0.361514501 (+2.102%) | 0.368739554 (+4.143%) |
| braking | 0.305678864 | 0.498100059 (+62.949%) | 0.451342540 (+47.653%) |
| coast | 0.254718794 | 0.279888385 (+9.881%) | 0.271400681 (+6.549%) |

Таким образом, особенно заметна регрессия после торможения **+62.949% / +47.653%**. Она не замаскирована улучшением обычной тяги. Нельзя объявлять причиной конкретный d или узел карты без отдельной причинной абляции; такая абляция после результата не подбиралась.

Все positive-delta строки clean/fault/distance/MAE/recovery сохранены в delivery/REGRESSIONS.csv (419 строк); полные, включая улучшения и missing, — в original results.json.gz. Малая таблица per_bag.csv содержит только clean, не все faults. State traces первого development bag до/внутри/после original dropout10 и трёх command transitions лежат сжато в основном artifact, не коммитятся повторно.

## Обязательные v8 safety suites

| Отдельная suite | Events / reference comparisons | Baseline event RMSE | λ=.1 | λ=1 |
|---|---:|---:|---:|---:|
| Low-speed lock 3/5 с | 26 / 34 | 0.368545673 | 0.358985552 (−2.594%) | 0.360768101 (−2.110%) |
| Abrupt common-mode +5 м/с, .7/1.2 с | 28 / 30 | 0.100632272 | 0.085376094 (−15.160%) | 0.095796628 (−4.805%) |

Применены прежние anchors/окна к development: low-speed predicate исходного PR13; common suite исходного H11. Обе event-macro safety проверки проходят, но не дают admission вместо original gain. False stops=0 у всех. Baseline/candidates одинаково имеют 6 unrecovered low-speed, 2 common-mode и 5 transition comparisons. В AUDIT они перечислены индивидуально. Их наличие не доказывает безопасность и не оправдывает новые failures. Новых individual failures нет.

## Стоимость и реально выполненные проверки

Отдельный cost-only run не менял карты. Первый development bag, 10 с прогрева и следующие 3600 тактов (~180 с), одинаковые collectors, threads=1. Три AB/BA цикла на карту: 6 baseline + 6 candidate replay на уровень, всего 24. Медианы:

| Карта | Step CPU, baseline→candidate, мкс/такт | Δ | Replay CPU, baseline→candidate, мкс/такт | Δ |
|---|---:|---:|---:|---:|
| λ=.1 | 32.398643→32.911685 | +1.584% | 48.887624→49.494444 | +1.241% |
| λ=1 | 32.646056→33.278056 | +1.936% | 49.332469→50.108862 | +1.574% |

Replay wall: +1.253%/+1.621%. Process peak RSS=124719104 байта во всех повторениях: это общий high-water offline-процесса, а не независимый RSS каждой модели/ROS-ноды. Диапазоны отдельных повторов перекрываются; малая цена — описательный замер, не статистически доказанная разница.

В первоначальном development/cost.json step исключал прогрев, а replay включал. Этот исходный файл сохранён. Отдельный source5a694cc/run36221231030 измерил правильный единый steady-интервал и проверил прежние source/fit hashes; fitting/accuracy/validation не повторял. Здесь показаны только исправленные steady-цифры.

Preflight run36220067112, fit/development run36220877255 и cost run36221231030: jobs завершены success, результаты скачаны и сверены. Основной research run: 156 исходных tests, 43 research-integrity, 26 H24/driver tests, затем по 19 mechanism tests с каждой фактически fitted enabled картой — PASS; compileall PASS. Наборы повторяются, их суммы не выдаются за уникальные тесты. Проверены monotonicity, continuity, endpoints, deadband/sign/reverse brake, torque/power crossover, true stop/zero-lock/quarantine, feature-off equality на 6000 тактах, causal prefix, repeated/future/stale/reset/gap, finite bounds и согласованная дистанция. При возобновлении локально повторены 26 H24/driver tests: PASS.

Enabled installed ROS replay в двух clock modes, offline 2 CPU/500000000 bytes, end-to-end latency/RSS/GetParameters/import hashes: **NOT_RUN_AFTER_REJECTION**. Canonical feature-off CI не сертифицирует H24. Offline 20 Hz grid и микросекунды step не являются wall-clock latency guarantee. runtime_verified=false, ready_to_merge=false.

## Научное основание и ограничения

Перед fitting сохранено чтение H07/PR22 (тяга/торможение response), R2-H17/PR30 (command deadtime, source ed62dc6, report d1e3517) и R2-H16-A/PR34 (multihorizon physics, source9b382e3, report476ffef). Их числа не использованы вместо R3 baseline. H24 меняет статическую нелинейность, не временную реакцию или другие коэффициенты.

Источник мотивации: Han, de Callafon (2011), Closed-loop Identification of Hammerstein Systems Using Iterative Instrumental Variables, DOI10.3182/20110828-6-IT-1002.01589. Уровень чтения — publisher search-record/abstract; прямой publisher HTML вернул403, full paper не прочитан. H24 не реализует его instrumental-variable estimator и не переносит результат servo-эксперимента на трамвай. Известные Consensus/Scite monthly quota stops не обходились повторными запросами, покупки не выполнялись. Фактический Wolfram worksheet/output сохранён в research/R3_H24/science: slopes/bounds/continuity/endpoints, rank одного notch против нескольких, единицы и crossover. Дополнительные midpoint bounds из worksheet в fitting не применялись. Эти тождества не доказывают устойчивость переключаемого observer, физическую идентифицируемость или точность.

Access: 64 vehicle-only train loads, 17 основных development loads + 1 original-cost + 1 steady-cost load; validation/test SQLite loads отсутствуют. Downloader распаковывает общий dataset ZIP, однако test payload records не декодировались SQL-загрузчиком и не использовались в fitting/оценке. Псевдоцель колёс не ground truth. Повторно используемый development и исторически переиспользованный validation не независимый final test. Distance — скалярные переякоренные spans, не xyz/ENU/полный terminal drift. Произвольная общая ошибка колёс остаётся неоднозначной.

## Evidence и воспроизведение

- [Preflight run](https://github.com/jabrailkhalil/hack/actions/runs/36220067112), checkpoint `efb6cd9bb4c0f2134b285c9947e035279a59b4b4`.
- [Два fit и development](https://github.com/jabrailkhalil/hack/actions/runs/36220877255), [компактный checkpoint](https://github.com/jabrailkhalil/hack/tree/90fc7a3b60d5afdcc443aea9cfa01c812aa55703/reports/research_R3/H24/36220877255-1): decision, per_bag clean CSV, per_group, fitted карты и source hashes.
- [Steady-cost run](https://github.com/jabrailkhalil/hack/actions/runs/36221231030), checkpoint `cc029a803cfbb13eb0976948af06fe7ea2bcf0d6`.

Большие NPZ/traces/raw JSON хранятся только в сжатых artifacts; Git содержит компактные данные. Artifact IDs, SHA256 и retention приведены в SUMMARY. Все три ZIP скачаны, их SHA256 совпали; retention заканчивается 26.10.2026. Delivery содержит исходные ZIP без перекодирования, runtime.patch, этот отчёт, SUMMARY, audit_results.py/AUDIT.json и REGRESSIONS.csv. Старые evidence не переписаны.

Полный checkout измеренного commit, Python3.13.5, NumPy2.3.5, SciPy1.17.0. Подготовка checkout ниже — инструкция воспроизведения; в реальном workflow выполнялся actions/checkout. Экспериментальные команды соответствуют выполненным стадиям. Новые output directories обязательны.

```bash
git fetch origin research/R3-H24
git worktree add --detach ../hack-H24-reproduce 6b3a11a68b83ee7b680b3b283f4800726c7b84cd
cd ../hack-H24-reproduce
python -m pip install -r requirements-research.txt
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
PYTHONPATH=src/reserve_odometry python -m unittest discover -s tests -v
python -m unittest discover -s research/tests -v
PYTHONPATH=src/reserve_odometry python -m unittest discover -s research/R3_H24/tests -v
python -m compileall -q src/reserve_odometry tools/research_R3_H24 research/R3_H24
python tools/get_dataset.py
OUT=$(mktemp -d)
python tools/research_R3_H24/preflight.py --output "$OUT/train" --workers 2
python tools/research_R3_H24/fit.py --preflight "$OUT/train" --output "$OUT/fit"
python tools/research_R3_H24/develop.py --fit "$OUT/fit" --output "$OUT/development" --workers 2
```

Для replay без нового fitting распаковать основной исходный artifact и передать его fit/ в develop.py. Для точного steady-cost использовать source5a694cc и `python tools/research_R3_H24/cost_after_warmup.py --fit <распакованный-mapping-artifact>/fit --output <новый-каталог>`; SHA256.json должен оставаться рядом с fit/. Восстановление approval/validation не автоматизировано и не разрешается этим replay.

Пост-аудит не читает bags: `python audit_results.py --repo-root <checkout> --evidence <mapping-artifact> --preflight <preflight-artifact> --cost <cost-artifact> --output <новый-AUDIT.json>`.

**Итог: REJECTED для двух зарегистрированных карт. Механизм реализован и покрыт, но общий accuracy-контракт не пройден. Оставить baseline v8; не merge/auto-merge. Это не опровержение всего семейства монотонных карт.**
