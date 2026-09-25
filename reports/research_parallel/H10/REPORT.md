# H10 — отрицательный исследовательский результат

**Вывод: проверенный вариант `H10_joint_q004` отвергнут. Улучшение не подтверждено; draft PR #18 не готов к merge.** Это вывод об одном заранее зафиксированном варианте, а не доказательство невозможности любого совместного observer.

## Идентификаторы и исходные результаты

- Baseline: `984fdf2fc4faf05325249215d6b8541c0e68209a`, профиль `adaptive_v5`.
- Пререгистрация до реализации/экспериментов: `50515d4924cf0275ef071c8af38bd6cf0b6810d6`, [PLAN.json](../../../research/parallel/H10/PLAN.json).
- Измеряемый код/runner: `867ff876284a50355d855273c214769e2356a4ae`. Последующие коммиты добавляют документацию, не меняют алгоритм или результаты.
- [Алгоритмический патч](../../../research/parallel/H10/algorithm.patch), SHA256 `b4957a1fcb0221076ac24c4d337fbb3cc8d2d69a1538f149e70f451f53526be8`.
- SHA256 применённого core: `420d21470aa4c57934b7e7f479efac4709c34ac5f8e304ea10e8aee1ccb75654`.
- [GitHub Actions 36175232852, attempt 1](https://github.com/jabrailkhalil/hack/actions/runs/36175232852): job `measure` завершился success. Success означает корректное завершение эксперимента, **не принятие кандидата**.
- Checkpoint commit: `0b19c3282a38d9c3836eb591d42fe5b6418756d1`, ветка `checkpoint/research-H10-36175232852-1`.
- [Полный checkpoint с train/validation/логами](https://github.com/jabrailkhalil/hack/tree/0b19c3282a38d9c3836eb591d42fe5b6418756d1/reports/research_parallel/H10/runs/36175232852-1).
- [Исходные validation JSON](https://github.com/jabrailkhalil/hack/blob/0b19c3282a38d9c3836eb591d42fe5b6418756d1/reports/research_parallel/H10/runs/36175232852-1/validation/results.json), [все clean/fault per-bag метрики CSV](https://github.com/jabrailkhalil/hack/blob/0b19c3282a38d9c3836eb591d42fe5b6418756d1/reports/research_parallel/H10/runs/36175232852-1/validation/comparison.csv), [решение](https://github.com/jabrailkhalil/hack/blob/0b19c3282a38d9c3836eb591d42fe5b6418756d1/reports/research_parallel/H10/runs/36175232852-1/validation/decision.json).
- Artifact `H10-36175232852-1`, ID `10881672362`, ZIP SHA256 `9435dd44aa3af34e05139c1c01d5e7f791afee149d10dfddf5acd07070cc9a45`. Его 102 файла также доступны через постоянный checkpoint выше; retention artifact — 30 дней.

## Гипотеза и реализация

Один вариант без подбора параметров: состояние `[v,d]`, ковариация `Pvv/Pvd/Pdd`, disturbance random-walk `q_d=0.04`, начальное `Pdd=(disturbance_limit/2)^2`. Вместо отдельного эвристического обновления d — одна velocity innovation, `H=[1,0]`, связанный Kalman gain и полная Joseph-форма ковариации. Вне прежних условий доверенной пары `Kd=0`; Pdd не сокращается как будто d измерено ненадёжным колесом.

Сохранены средний прогноз движения, физические коэффициенты adaptive_v5, исходное robust R без деления на число согласованных колёс, timestamp/stale/range/rate/innovation/disagreement guards, eligibility адаптации, stop/zero-lock и bounded reacquisition. Ковариация распространяется с локальным якобианом и ограничивается PSD-preserving масштабированием. При проекции состояния/подтверждённом stop/reacquisition cross-covariance сбрасывается согласованно с реализованными ограничениями. При dropout среднее d удерживается: не повторяется отвергнутый в v6 mean-decay.

Реализация находится в экспериментальном `algorithm.patch`: workflow применяет его к core в рабочей копии. Активный core/default в ветке не заменены; после применения патча H10 всё равно требует `joint_observer_enabled=1`. Disabled-path отдельно проверен на точное совпадение с немодифицированным baseline. Runtime-зависимости не добавлены, используется stdlib math; состояние и sensor histories ограничены постоянным размером.

## Методика и защита от подгонки

Train-loader проекта разрешает только controller/front/rear; train GNSS не читался. Поэтому выбрали не скрытую настройку на validation, а **один заранее заданный вариант без fitting/search**. 64 train-bag использованы только для causal replay, одинакового output schedule и вычислительной стоимости. Train accuracy не заявляется.

После train создан FREEZE.json: **2026-09-25 18:45:52.329452 UTC**. Validation started.json создан **18:45:53.446728 UTC**, до открытия validation-bag. Source/config/evaluator hashes проверены перед доступом. Алгоритм и параметры после validation не менялись.

Использованы без редактирования `tools/finalization/evaluate.py` и `tools/research_v6/compare.py`; подменена только фабрика конфигураций. Scoring, match/reference masks, timestamps, оба receiver, fault anchors/windows и group-macro aggregation одинаковые. Неизменность evaluator/Timeline/split/config файлов проверялась против git baseline. Вспомогательный v4 включён только для исходной проверки воспроизведения; целевой baseline — v5.

19 validation-bag / 10 групп; reference доступен для 30 bag/receiver-пар в 9 группах. Четыре bag без reference не записаны как нулевая ошибка. 76 fault-сценариев, 120 сравнений с reference. Сценарии исходные: bias 5 с, dropout 5 с, dropout 10 с, lock 3 с. Output 20 Гц, дополнительная задержка 0 с.

Проверка исходной `reproduce_published_v5`: **468 числовых полей, максимальное абсолютное расхождение 0.0**, passed. Final-test loader не вызывался; access journal содержит только 64 train и 19 validation bag. Загрузка исходного общего архива не означает оценивание находящихся в нём final-test записей.

## Основные результаты

Изменение = candidate / baseline − 1; для ошибок положительное число означает ухудшение.

| Метрика | adaptive_v5 | H10 | Изменение |
|---|---:|---:|---:|
| Clean group-macro RMSE, м/с | 0.117138274 | 0.117451999 | +0.267824% |
| Fault group-macro RMSE, м/с | 0.538434411 | 0.545225943 | **+1.261348%** |
| Pooled RMSE, м/с | 0.216723603 | 0.216799479 | +0.035010% |
| Scalar span distance RMSE, м | 4.630977808 | 4.648774599 | +0.384299% |
| Сопоставленные reference-точки | 698891 | 698891 | одинаково |
| False stop samples, clean | 18 | 18 | одинаково |
| False stop samples, fault | 0 | 0 | одинаково |
| Невосстановленные fault-сравнения | 0 | 0 | одинаково |

Нарушены два условия: нет ≥2% clean gain или ≥5% fault gain; fault-регрессия +1.261348% превышает 0.5%. Другие агрегаты укладываются в лимиты, но не компенсируют этот отказ. Per-bag clean gate не нарушен. Потери coverage, новых false stops, causal errors или resets не обнаружено. Причины исходного `decide()`: `aggregate_regression`, `insufficient_gain`. Дополнительный письменный лимит 0.5% для pooled RMSE также проверен, без изменения общей функции scoring или ослабления порогов.

## Регрессии, которые скрывает среднее

Следующие разрезы — описательный анализ уже полученных JSON, не новый подбор кандидата и не замена основной метрики. Для разрезов по типам fault используется та же group-macro формула на соответствующем подмножестве.

| Fault | Baseline RMSE, м/с | H10 RMSE, м/с | Изменение |
|---|---:|---:|---:|
| bias 5 с | 0.414541580 | 0.414088467 | −0.109305% |
| dropout 5 с | 0.559015226 | 0.570078664 | +1.979094% |
| dropout 10 с | 0.723795502 | 0.731585069 | +1.076211% |
| lock 3 с | 0.456385335 | 0.465151573 | +1.920797% |

**63 из 120** fault/reference сравнений ухудшились. Наиболее заметные случаи:

| Bag / receiver | Fault | Baseline → H10 RMSE, м/с | Изменение |
|---|---|---:|---:|
| 30639_50956d6e / rover | dropout 10 с | 0.086758940 → 0.647218142 | +645.996% |
| 30639_50956d6e / master | dropout 10 с | 0.087056790 → 0.646421015 | +642.528% |
| 30618_68d1748a / master | dropout 10 с | 0.228631764 → 0.544112157 | +137.986% |
| 30618_68d1748a / rover | dropout 10 с | 0.227550008 → 0.540816601 | +137.669% |
| 30639_50956d6e / rover | dropout 5 с | 0.075012589 → 0.347107645 | +362.733% |
| 30639_50956d6e / master | dropout 5 с | 0.077536285 → 0.348348682 | +349.272% |
| 30639_50956d6e / rover | lock 3 с | 0.080561466 → 0.245123868 | +204.269% |
| 30639_50956d6e / master | lock 3 с | 0.083810987 → 0.246410401 | +194.007% |

Clean RMSE ухудшился в 26 из 30 сравнимых bag/receiver-пар, но ни одна регрессия не превысила исходный `max(0.005 м/с,5%)`. Наибольшая абсолютная clean-регрессия: `30639_d601d28f/master`, 0.105715414 → 0.106782166 м/с, Δ +0.001066752 м/с. Полная таблица всех clean-регрессий находится в checkpoint `validation/REPORT.md`, все clean/fault результаты — в `comparison.csv` и `bags/*.json`.

Нулевое число невосстановлений **не означает одинаковую скорость восстановления**: recovery_s ухудшился в 17 сравнениях. Худший случай `30618_49fe4c54/master`, bias 5 с: 0.205104267 → 1.005104267 с, Δ +0.8 с. Это раскрытый результат, а не новый задним числом введённый порог.

Глобальная дистанционная регрессия +0.384299% скрывает локальное ухудшение `30639_3b3d9eb8`: rover 26.522054181 → 27.044924014 м (+0.522869833 м; +1.971453%), master 12.861796436 → 13.135913614 м (+0.274117179 м; +2.131251%). Лимит 1% задан для агрегата; дополнительного per-bag distance gate не придумывали.

## Реально выполненные проверки и стоимость

Локально Python 3.13.5: 20/20 H10 implementation tests passed (0.341 с). В GitHub Actions с применённым патчем: **22/22 legacy core tests** (0.091 с) и **20/20 H10 tests** (0.634 с). Проверены Joseph против явной матричной формы, аналитический Jacobian против finite differences, integrated Q, PSD/state/memory invariants на 15000 шагах, exact disabled-baseline equivalence на 6000 шагах, AST-неизменность исходных guard-методов, stale/held/future samples, stop/zero-lock/reacquisition. Это проверки реализации, не доказательство реальной точности.

На 64 настоящих train-bag replay каждого алгоритма обработал 2646426 input events и сформировал **1366299 outputs**. Порядок baseline/candidate чередовался между bag.

| Offline replay | Baseline | H10 |
|---|---:|---:|
| Сумма wall time, с | 33.252175 | 38.877262 |
| Сумма wall time / число outputs, мкс | 24.337407 | 28.454432 |

Измеренная стоимость offline replay выросла **на 16.916450%**. Это один проход в общей среде Actions; время включает Timeline и сбор output-массивов. Это **не** ROS callback latency, publisher-to-subscriber latency или full runtime benchmark под заданным лимитом CPU/RAM. На train и validation не зарегистрировано causal errors/reset нарушений; coverage/timestamps совпадают.

## Команды воспроизведения

В отдельной рабочей копии фиксированного source commit:

```bash
git fetch origin research/parallel-H10
git worktree add --detach ../hack-H10 867ff876284a50355d855273c214769e2356a4ae
cd ../hack-H10
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-research.txt
export H10_BASELINE_CORE="$(mktemp /tmp/H10-baseline-XXXXXX.py)"
git show 984fdf2fc4faf05325249215d6b8541c0e68209a:src/reserve_odometry/reserve_odometry/core.py > "$H10_BASELINE_CORE"
git apply --check research/parallel/H10/algorithm.patch
git apply research/parallel/H10/algorithm.patch
PYTHONPATH=src/reserve_odometry python -m unittest discover -s tests -p test_core.py -v
python research/parallel/H10/test_joint.py
python tools/get_dataset.py
OUT="$(mktemp -d /tmp/H10-results-XXXXXX)"
python research/parallel/H10/run.py --stage train --output "$OUT/train"
python research/parallel/H10/run.py --stage freeze --training "$OUT/train" --output "$OUT/FREEZE.json"
python research/parallel/H10/run.py --stage validation --freeze "$OUT/FREEZE.json" --output "$OUT/validation" --workers 2
```

Выполненный workflow содержит именно эти apply/test/data/train/freeze/validation стадии; logs и access journal сохранены в checkpoint. Повтор неизменного кандидата для воспроизводимости не является новым независимым test.

## Ограничения и решение

Полный ROS end-to-end benchmark H10 под 2 CPU / 500 MB **не проводился**. Обычный CI активного default не следует приписывать экспериментальному H10. Локальный контейнер не имел DNS-доступа к GitHub/датасету; GitHub read/write и реальное выполнение в Actions были доступны и использованы.

Ковариация приближённая: actuator-history uncertainty не входит в [v,d]; robust R, проекции и ограничение covariance не создают калиброванный confidence interval. У произвольной common-mode ошибки двух колёс остаётся неоднозначность. Никакие GNSS/IMU или будущие samples в observer не добавлены. Distance — переякоренный скалярный surrogate, не xyz.

Validation уже использовался раньше и не является независимым final test. Исторические final-test цифры не использованы для подбора или оценки H10. Увеличение ошибки на dropout/lock совместимо с менее удачной оценкой удерживаемого d, но причинная локализация этой регрессии не доказана отдельной ablation; представлять это как установленную причину нельзя.

**Оставить adaptive_v5. H10_joint_q004 не продвигать.** Во время работы актуальный main независимо изменился; приведённое сравнение относится строго к согласованному baseline первого раунда, не к более позднему main. Не выполнялись merge, auto-merge, изменения чужих веток или опубликованных отчётов.
