# H12 / R2-v7-fixed — REJECTED

**Исследовательский отрицательный результат, не готов к merge.** Проверенный кандидат `H12_piecewise_integral` активен и проходит nonregression/safety guards, но не даёт требуемых 2% clean gain либо 5% original fault gain. Автоматическая причина — `insufficient_gain`. Параметры и patch после validation не изменялись. Это отклонение одного кандидата, не всего семейства интегральных методов.

## Идентичность и порядок

| Назначение | Значение |
|---|---|
| Общий baseline | `65bba39ed05c781f3f69a65c02f69931152cbfd9` |
| Baseline observer/profile | `GuardedReadoutObserver` / `guarded_readout_v7.yaml` |
| Canonical launch/executable | `odometry.launch.py` / `guarded_odometry_node` |
| Ветка | `research/round2-H12` |
| PLAN до экспериментов | `2ebfd85a1b730a47e99670b7f00d0a99e48bb2fa` |
| Измеренные patch/driver/tests | `c5fe78712c621527f9ccf5f9860db1ee04c54d92` |
| Freeze до validation | `8d39337962bf0cd93a0960a65e3e467fed1d6c56`, 25.09.2026 20:13:39 UTC в FREEZE |
| Immutable checkpoint результата | `d73ab47d96c3b10bbbfc5bf7b67008f38dd2caf9` |
| Run / attempt | `36184024656 / 1` |
| Draft PR | https://github.com/jabrailkhalil/hack/pull/28 |

[Исследовательский запуск](https://github.com/jabrailkhalil/hack/actions/runs/36184024656) завершён success, job `108232971669`. [Freeze](https://github.com/jabrailkhalil/hack/blob/8d39337962bf0cd93a0960a65e3e467fed1d6c56/reports/research_R2/H12/36184024656-1/experiment/FREEZE.json) опубликован отдельным коммитом до единственного validation. [Исходное evidence](https://github.com/jabrailkhalil/hack/tree/d73ab47d96c3b10bbbfc5bf7b67008f38dd2caf9/reports/research_R2/H12/36184024656-1) скопировано в research-ветку без пересчёта и без merge. Commit отчёта не является новой измеренной версией алгоритма.

Baseline фиксирован: readout gain=1, holdoff=0.5, inner wheel_time_compensation=0, adaptation_tau=0.5, 20 Гц, alignment_delay=0. Не использованы moving main, H11/v8 и validation других агентов R2. Main, чужие ветки и исторические отчёты этой работой не изменялись. Merge и auto-merge не выполнялись.

## Реальный алгоритмический патч и включение

[algorithm.patch](algorithm.patch) меняет только `guarded_readout.py`. Вместо `a_model(t) * mean(age)` вычисляется среднее индивидуальных интегралов кусочно-постоянной истории на `[sample.t, output.t]`. Интеграл от средней даты не используется. Сегмент `(old_t,t]` содержит тот pre-correction `a_model`, которым исходный core предсказывал этот шаг: end-step drive, old velocity и old disturbance. Аргументы восстанавливаются тем же порядком операций; соответствие отдельно сверено с фактическим локальным `a_model` внутри core на 450 unit-test ticks. История не объявляется истинным ранее измеренным ускорением.

История ограничена `deque(maxlen=16)` и max_age с пересекающим границу сегментом. При недостатке покрытия хотя бы одного принятого sample весь update возвращается к точной прежней формуле. На постоянном ускорении сохранён порядок floating-point операций baseline. Нет ожидания пары, повторной ассимиляции, новых controller/front/rear входов, GNSS/IMU, ground truth, bag ID и fault oracle в runtime. Core predictor, disturbance, covariance, gates, holdoff и Timeline не меняются; поправка не возвращается во внутренний фильтр. Это не повтор H08.

SHA256 реально исполненного patched readout: `7dcb52ac0a60883a6a2ade90d686523e3c5a02ec622c9877dffc843f04dd3727`. `research/R2/H12/build.py` проверяет baseline hashes, применяет patch к временной копии, проверяет полученный hash и загружает отдельный класс. `run.py` включает его с `ReadoutConfig(integral_age=True)`. Candidate-off выключает только H12, оставляя v7 readout gain=1.

**Обычный checkout и штатный ROS launch H12 не включают.** Программное включение:

```python
import sys
sys.path.insert(0, 'research/R2/H12')
from build import observer
candidate = observer(enabled=True)
# candidate.step(t, command, front, rear) — тот же интерфейс Sample.
```

Для выгрузки патченной копии: `python research/R2/H12/build.py --write /tmp/H12-isolated-new`. Установленная ROS-интеграция отклонённого кандидата не выполнялась.

## Данные, измеритель и разделение ролей

Ни одного коэффициента не подбирали: заранее задан один кандидат. Train: первые ≤180 с всех 64 train-bag, 406293 vehicle events; 208014 non-WAITING outputs и 212494 проверенных ticks. GNSS train не декодировался. Здесь только sanity/identity, не независимая оценка точности.

Development: все 17 bags / 7 групп, reference в 6 группах и 19 bag/receiver-парах; 15 missing receiver-пар сохранены. Original suite: 56 сценариев, 60 reference-сравнений. Validation: все 19 bags / 10 групп, reference в 9 группах и 30 bag/receiver-парах; четыре bags без reference не заменены нулевой ошибкой. Original validation suite: 76 сценариев и 120 reference-сравнений. Оба приёмника сохранены; они не считаются независимыми поездками.

Счётчик использует неизменные `evaluate.score/replay`, matching, distance и `research_guarded.aggregate/fault_windows`. Меняется только observer factory; прозрачная wrapper сохраняет массивы выхода. Legacy имена `baseline_v2/balanced_physics` являются техническими ключами score и переименованы в `main/candidate` после подсчёта; фактически baseline — канонический v7, не v5 и не `Observer(Config())`. Baseline на всех 17+19 clean bags точно воспроизведён независимым каноническим guarded driver; проверены receiver metrics, nested distance и runtime counters (246+310 полей, не утверждение о числе независимых числовых испытаний).

Новый read-only loader проверяет истинную роль из исходного manifest и bag SHA до SQLite IO; сохраняет access journal до загрузки. По train доступны только 3 vehicle-топика, development/validation reference находится только во внешнем evaluator. Final/test не декодировался и не оценивался; штатный общий ZIP данных скачан и распакован `get_dataset.py`. После скачивания artifact независимо проверены freeze, candidate source, train/development results и access hashes. Исторические release hashes/guards не удалены.

## Фактическая активация, до и после freeze

На development: **46862 / 99736 updates = 46.9860%**, 7 групп, 10417 изменений в controller transition windows. До validation пороги ≥1000 / ≥3 группы / ≥100 phase updates были выполнены. Максимальное изменение целевого age increment — **0.012749790137 м/с**. На validation: **55858 / 153594 = 36.3673%**, 10 групп, 11196 phase updates; максимум **0.014152707419 м/с**. Это разница целевого переноса до K/gain, не улучшение ошибки и не максимальная разница опубликованной скорости.

На validation все materially changed clean updates (>1e-9 м/с) относятся к возрасту >50 мс: 46065 в (50,100] мс и 9793 выше 100 мс. Для ≤50 мс изменений такого размера нет. Это согласуется с равенством интеграла и исходного произведения внутри одного predictor segment. До получения данных отсутствие активации не предполагалось доказанным; фактическое покрытие оказалось достаточным.

Максимум сохранявшейся истории в реальном replay — 6 сегментов; synthetic dense-step тест довёл историю до предела 16 и проверил fallback. Fallback clean development — 2, original development faults — 16, transition-dropout — 6; clean validation — 0, original validation faults — 4.

**Ограничение skew:** статистика относится к принятым в конкретном update samples. На development только 2 updates имели accepted skew >25 мс; на validation accepted skew=0. Широкий asynchronous skew проверен unit-тестами, но не получил широкого реального покрытия. Нельзя обобщать результат на произвольные сетевые задержки.

## Validation: абсолютные и относительные изменения

Положительная delta ошибки означает ухудшение.

| Метрика | Baseline v7 | H12 | Абсолютная delta | Относительная delta |
|---|---:|---:|---:|---:|
| Clean group-macro RMSE, м/с | 0.114549861317 | 0.114555761079 | +0.000005899762 | +0.00515039% |
| Original fault-event group-macro RMSE, м/с | 0.538286782601 | 0.538286953531 | +0.000000170930 | +0.00003175% |
| Pooled clean RMSE, м/с | 0.216406794155 | 0.216408908611 | +0.000002114456 | +0.00097707% |
| Scalar-span distance group-macro RMSE, м | 4.595480653018 | 4.596008844658 | +0.000528191640 | +0.01149372% |
| Clean group-macro MAE, м/с | 0.047549651404 | 0.047554920905 | +0.000005269502 | +0.01108210% |
| Clean group-macro p95 absolute error, м/с | 0.131696583956 | 0.131718382152 | +0.000021798197 | +0.01655183% |

Signed bias: **−0.015975155952 → −0.015971229301 м/с**, delta +0.000003926651 м/с (немного ближе к нулю). Mean recovery time: **0.254840173467 с** у обоих; все 120 validation recovery values совпали. Matched clean points **698891 → 698891**; false-stop clean/fault **18/0 → 18/0**; unrecovered **0 → 0**; causal errors и resets **0 → 0**. Все n/coverage совпали по отдельным сравнениям.

Из 30 clean сравнений **23 хуже, 7 лучше**. Из 120 fault-event сравнений **52 хуже, 48 лучше, 20 равны**. Distance: **14 хуже, 16 лучше**. Все исходные значения и missing находятся в `experiment/validation/per_bag.csv`, `results.json` и `bags/*.json`.

| Локальная регрессия | Baseline | H12 | Абсолютная delta | Относительная delta |
|---|---:|---:|---:|---:|
| rmse: 30618_437e855c/master | 0.032729584705 | 0.032772287793 | +0.000042703088 | +0.130472% |
| rmse: 30618_437e855c/rover | 0.033420117145 | 0.033462712009 | +0.000042594863 | +0.127453% |
| event_rmse: 30639_50956d6e/master / bias 5.0 с | 0.033330126278 | 0.033335239739 | +0.000005113462 | +0.015342% |
| event_rmse: 30639_50956d6e/master / lock 3.0 с | 0.083276902875 | 0.083280314023 | +0.000003411148 | +0.004096% |
| distance: 30639_3b3d9eb8/rover | 26.463613736057 | 26.475991495742 | +0.012377759684 | +0.046773% |
| distance: 30639_3b3d9eb8/master | 12.945680526799 | 12.953303851894 | +0.007623325095 | +0.058887% |

Самая большая clean-регрессия — 0.130472%, существенно ниже per-bag guard. Ни одна локальная регрессия не скрыта изменением порога. На development были **4 старых unrecovered** у обоих; в дополнительном transition-dropout — **3 старых unrecovered** у обоих. Нулевые unrecovered выше относятся именно к original validation, не ко всем данным вообще.

## Неизменный контракт и вывод

Clean gain = **−0.0051503874%**, original fault gain = **−0.0000317544%**. Минимум 2% clean ИЛИ 5% fault gain — **FAIL**. Clean/fault/pooled regression ≤0.5%, distance ≤1%, clean bag/receiver guard, coverage, отсутствие новых false stops/unrecovered/causality/reset — **PASS**. Причина `decision.json`: только `insufficient_gain`.

Статус механизма: **активен, внутреннее состояние не меняет; полезность не подтверждена**. Научный verdict проверенного кандидата: **REJECTED**. Merge readiness: **false**. Граница принятия не заменена улучшением отдельной вспомогательной метрики.

## Отдельные диагностики — не критерий продвижения

Controller-transition окна [anchor,anchor+2 s], anchors только по vehicle: development phase RMSE **0.084885201539 → 0.084906956573 м/с (+0.025629%)**; validation **0.088596917111 → 0.088612699743 (+0.017814%)**. Здесь также нет улучшения.

Дополнительные 37 development transition+both-dropout-1s сценариев: fault-event RMSE **0.071506088353 → 0.071505176819 м/с**, всего **0.001275%** улучшения. Recovery mean и 3 unrecovered не изменились. Эта отдельная диагностика не заменяла исходный fault suite.

Сохранены все ticks до/во время/после каждого исходного fault и специальных development faults (`traces/*.csv`): внутренние v/s, drive_a, disturbance, pv, статусы, holdoff и две readout corrections. Post-hoc анализ неизменных validation traces: до отказа max |published Δv|=0.007189848 м/с; внутри fault=0.000728748; после=0.005598543. Внутри fault **8546/8740 ticks (97.7803%)** имеют нулевую readout correction у обоих. Это наблюдение согласуется с сохранёнными guards; не отдельное доказательство причинности или универсальной устойчивости.

## Проверки и стоимость

В исследовательском run реально прошли **144 исходных unit tests, 43 research-integrity tests, 16 H12 tests**, compileall, dataset/bag hashes, полный train/development/validation replay. Дополнительно **1112341 ticks** проверены на побитовую идентичность ВСЕХ полей core state и holdoff; candidate-off совпал по Estimate, статусам и readout state. В это число включены initialization/WAITING ticks. Core identity исключает только published `last_estimate`, который является самим объектом output-only изменения; отдельно проверяется полная off-эквивалентность этого Estimate. Все runtime counters совпали.

H12 tests: individual integrals, constant case, gap/fallback, bounded count/time, 20000 dense ticks, 1600 mixed ticks, prefix future-tail test, stale/future/duplicates, reset, no sign reversal, low-speed zero-lock, distance/a consistency и фактический `a_model` из core. Локально те же 16 tests пройдены; дополнительно 5 независимых loader denial checks остановились до hash/SQLite. Unit tests не выдаются за accuracy.

[Обычный PR CI](https://github.com/jabrailkhalil/hack/actions/runs/36184070283): core, research-integrity, ros-humble и offline-limited — success. Штатная ROS-сборка/запуски НЕ включают изолированный H12; эти jobs не являются его enabled benchmark.

Стоимость на одном и том же development `30618_0652866c`: 10 с warmup, следующие 60 с; по 6 пар AB/BA для step и replay (24 timed runs), одинаковый сбор outputs, threads=1, без дорогого bitwise audit в timed path. Приведены медианы повторов:

| Измерение, мкс/output | Baseline | H12 | Изменение |
|---|---:|---:|---:|
| step CPU | 24.655198 | 28.506216 | +15.6195% |
| step wall | 24.660178 | 28.533954 | +15.7086% |
| replay CPU | 32.878543 | 36.872770 | +12.1484% |
| replay wall | 32.879422 | 36.888727 | +12.1940% |

Raw timing: `experiment/development/cost.csv/json`. High-water RSS всего исследовательского Python-процесса = **257343488 bytes**; это НЕ отдельный RSS кандидата и не ROS measurement. **Свежий installed enabled H12 ROS benchmark, оба clock modes, 2 CPU/500000000 bytes не проводился**, поскольку accuracy-gate провален. 20 Гц здесь — проверенное offline расписание, не wall-clock/latency гарантия. Превосходство по CPU отсутствует.

## Воспроизведение

Нужны git, Python 3.13.5 и закреплённые NumPy/SciPy из requirements. Данные загружаются штатно и проверяются хешами.

```bash
git checkout c5fe78712c621527f9ccf5f9860db1ee04c54d92
python -m pip install -r requirements-research.txt
python tools/get_dataset.py
PYTHONPATH=src/reserve_odometry python -m unittest discover -s tests -v
python -m unittest discover -s research/tests -v
python research/R2/H12/test_h12.py
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
OUT=/tmp/H12-new-run
python research/R2/H12/run.py --stage development --output "$OUT"
python research/R2/H12/run.py --stage freeze --output "$OUT"
# Publish FREEZE plus development evidence in your new checkpoint branch,
# then write its actual commit SHA to "$OUT/FREEZE_COMMIT.txt".
python research/R2/H12/run.py --stage validation --output "$OUT"
```

Точный исполненный порядок checkpoint commit/push дан в `.github/workflows/r2-h12.yml` закреплённого SHA. Freeze запрещён при провале development gate; validation требует неизменные source/parameter hashes и опубликованный freeze. Повтор использует новый output/run, без перезаписи этих результатов.

## Evidence, источники и ограничения

`PLAN.md`, `algorithm.patch`, `BASELINE.json`, `SOURCES.md`, `wolfram.wl`, `wolfram_output.txt`; `experiment/FREEZE.json`, `candidate.json`, `candidate_guarded_readout.py`; `train/results.json`, `development/` и `validation/` raw results, aggregates, per-bag CSV, access, phase, traces; полные логи в `logs/`.

Actions artifact **R2-H12-36184024656-1**, id **10885603277**, скачан и проверен: **7181108 bytes**, SHA256 `507c9bf72611d409768fd845d806a86e7a424345352b760a0aa951613bbf6f60`. Raw bags, секреты и кэши не опубликованы. Локальный прямой git доступ был недоступен из-за DNS; GitHub connector/Actions обеспечили реальное исполнение. Нет незавершённого accuracy этапа.

Consensus/Scite: журнальная работа Guarro et al., DOI 10.1002/rnc.7213, прочитаны abstract/metadata и 6500 символов введения, не статья целиком. Контекст mentioning не считается независимой верификацией. Другие сенсорные интерфейсы не перенесены. Wolfram реально проверил affine endpoint error `j*h^2/2`, right-rectangle `j*h^2/(2*n)`, constant/h→0 пределы, units, среднее индивидуальных интегралов и bounded correction recursion. Первоначальные warnings и неупрощённый bound сохранены; второй Reduce вернул False для существования контрпримера. Условная аналитика не доказательство accuracy.

Validation уже использовался прежде: **это не независимый final test**, статистическая значимость/обобщение не заявляются. Проверен один фиксированный piecewise-constant вариант; accepted skew покрыт узко; истинная общая колёсная ошибка без внешнего якоря остаётся неоднозначной. Distance — scalar reanchored span surrogate, не XYZ/ENU и не полный terminal drift. Отклонённый output-only patch не заменяет установленный runtime.
