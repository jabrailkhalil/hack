# H06: повторный захват по свидетельствам — отрицательный результат

## Решение

**Кандидат H06_evidence_04s_15x ОТВЕРГНУТ. Draft, не готов к merge.**

Один заранее зафиксированный кандидат прошёл исполнение на реальных записях, но дал **0% улучшения** clean и fault RMSE: `insufficient_gain`. На фиксированном наборе не возник ни один выход `REACQUIRING`, поэтому этот прогон не доказывает эффективность изменения именно при повторном захвате. Дополнительная явно отделённая синтетическая диагностика выявила регрессию защиты от динамически согласованного общего смещения колёс. Алгоритм и параметры после validation не изменялись.

Baseline первого раунда: `984fdf2fc4faf05325249215d6b8541c0e68209a`, профиль `adaptive_v5`.
План до экспериментов: `641df56dc24368b4269870fc6186a1ce2e0e8f70`, [PLAN.md](../../research/H06/PLAN.md).
Реализация и фиксированные хэши кандидата: `1a656508fd417eafe7301c42a882204a9a0acd42`.
Фактически измеренный source commit: `3ab24fbeb87c8622f06e52dd19d29abe5ee12191`.

[Завершённый исследовательский запуск 36174988639, attempt 1](https://github.com/jabrailkhalil/hack/actions/runs/36174988639) — **success как исполнение исследования, не как принятие кандидата**. Job `108203292345`. Сохранённый checkpoint commit: `6a9acd75420eb489b25734b07162179b42e1c2ab`, ветка `checkpoint/H06-36174988639-1`.

## Что действительно изменено

`RecoveryObserver` — отдельный opt-in класс. Патч `research/H06/core-hooks.patch` добавляет две точки расширения в исходный Observer: расчёт выдержки и предела шага. Их базовая реализация сохраняет исходную арифметику. Патч применяется только в экспериментальной рабочей копии; активные `core.py`, `default.yaml`, `adaptive_v5.yaml`, node/timeline, опубликованные отчёты и существующий evaluator в исследовательской ветке не заменены.

После прежних hard gates учитываются только новые свежие согласованные пары. Ускорение колёс должно совпадать по знаку с причинным модельным ускорением; оба модуля не меньше 0.15 м/с², расхождение ускорений не больше 0.35 м/с², расхождение колёс не больше min(штатного порога, 0.2 м/с). Требуется валидная команда controller. Интервал пары — от 0.05 с до max_age_s. Модельное ускорение берётся из той же физической модели до коррекции, а не из изменения скорректированного выхода.

На хорошем интервале накапливается dt, на плохом вычитается 2dt; память ограничена 0.4 с. При q = evidence/0.4 выдержка меняется от 0.8 до 0.4 с, ограничение шага — от 0.15 до 0.225 м/с на номинальную новую пару 0.1 с. Сохраняется исходное масштабирование по pair_dt; prediction-only такты не дают дополнительных коррекций. Hard failure, нормальное слияние и reset очищают накопление. Физическая модель, disturbance-адаптация 0.5 с, residual/zero-lock/rate gates не менялись. Дополнительное состояние — три скаляра, память O(1).

Историческое multirate-исправление уже присутствует в baseline и не засчитывается как H06. Предыдущие отрицательные v6-результаты изучены; clean gain не служит оправданием fault-регрессии.

## Методика и неизменность измерителя

Проверен ровно один вариант, без сетки и подбора параметров по validation. Train smoke: первые 180 с первого разрешённого train-bag `30618_0259fe53`, 7137 входных событий, 3520 выходов на модель. Загрузчик открыл только controller/front/rear; reference_used=false. Это проверка исполнения и инвариантов, не оценка точности и не полный development benchmark.

В логе Actions `FROZEN` записан 25 сентября 2026 в 18:41:58.323 UTC; команда validation началась после него в 18:41:58.399 UTC. `candidate-freeze.json` и `validation/started.json` совпадают. В них закреплены исходники, конфигурации, план, split, runner и операционные параметры. Перед IO проверяется неизменность evaluator/split/config относительно baseline и SHA256 самого кандидата.

Использованы исходные `tools/finalization/evaluate.py` и `tools/research_v6/compare.py`, включая score/replay, reference matching, метрики, агрегацию, anchors и окна сбоев. Меняется только фабрика Observer: baseline загружается из исходного core указанного SHA, H06 — из класса RecoveryObserver. Одинаковые timestamps, маски, оба GNSS-приёмника только для офлайн-оценки; 20 Гц и alignment_delay_s=0. GNSS/IMU не передаются алгоритму.

Четыре исходных fault-сценария на bag: bias front +5 м/с на 5 с; dropout обоих колёс на 5 с и 10 с; zero-lock обоих на 3 с. Основной показатель fault RMSE не заменялся показателем времени recovery. Сохранены group-macro и pooled оценки, значения каждого bag/receiver и отсутствие reference как null.

Исходный v6 gate не редактировался. Требования: ≥2% clean gain ИЛИ ≥5% fault-event gain; регрессия основных агрегатов ≤0.5%, дистанции ≤1%; clean per-bag/receiver ≤max(0.005 м/с,5%); без потери coverage, дополнительных false stops, невосстановлений, нарушений причинности или неожиданных resets. Дополнительно с самого плана задана внешняя проверка pooled RMSE ≤0.5% регрессии, отсутствующая в исходной функции v6.decide.

Среда фактического прогона: Ubuntu 22.04.5, Python 3.13.5, NumPy 2.3.5, SciPy 1.17.0, два worker, OPENBLAS_NUM_THREADS=1, OMP_NUM_THREADS=1. Оценка 19 bag заняла 38.989 с; это wall time исследовательского runner, **не latency ROS-узла**. SHA256 архива датасета проверен: `d0b2483e13990edb8219b0d7bbcafc7ed001cce549a4d3af467069b2472e7d52`.

## Реальные записи: агрегированные результаты

| Метрика | Baseline adaptive_v5 | H06 | Изменение |
|---|---:|---:|---:|
| Clean group-macro RMSE скорости, м/с | 0.11713827416709652 | 0.11713827416709652 | 0% |
| Fault-event group-macro RMSE, м/с | 0.5384344108523412 | 0.5384344108523412 | 0% |
| Pooled RMSE скорости, м/с | 0.2167236028496654 | 0.2167236028496654 | 0% |
| Distance surrogate RMSE, м | 4.63097780847452 | 4.63097780847452 | 0% |
| Сопоставленные точки скорости | 698891 | 698891 | 0 |
| Ложные stop samples, clean | 18 | 18 | 0 |
| Ложные stop samples, fault | 0 | 0 | 0 |
| Сравнения без подтверждённого recovery | 0 | 0 | 0 |

19 validation-bag / 10 групп; reference доступен в 9 группах и 30 bag/receiver-парах. Четыре bag без reference не считаются нулевой ошибкой. 76 fault-сценариев, 120 fault/receiver-сравнений с reference. Обе исторические baseline v4/v5 воспроизведены: **468 числовых полей, max absolute delta = 0**.

По сохранённым выходам evaluator нет различий ни в одном поле H06 и соответствующем поле adaptive_v5: clean/fault RMSE, MAE, p95, bias, coverage, recovery_s, false stops и вложенная distance surrogate. Runtime-словари также совпадают. Отдельный post-validation audit проверяет 264 clean и 1296 fault числовых полей верхнего уровня, а вложенные поля — целиком. Покадровые v/s в этом штатном evaluator не сохранялись; это сравнение сохранённых результатов, не заявление о выполненном побитовом сравнении всех реальных траекторий.

### Per-bag clean RMSE

Значения в таблице одинаковы для baseline и H06. Полные неокруглённые clean **и все fault per-bag/receiver** метрики находятся в CSV и JSON checkpoint, ссылки ниже.

| Bag | Master, м/с: baseline = H06 | Rover, м/с: baseline = H06 | Изменение |
|---|---:|---:|---:|
| 30618_0686195f | 0.094452304 | 0.094170108 | 0% |
| 30618_2255aade | нет reference | нет reference | — |
| 30618_2dbce472 | 0.130075572 | 0.057647387 | 0% |
| 30618_2f104a1d | 0.031473771 | 0.067776972 | 0% |
| 30618_437e855c | 0.042843732 | 0.043447871 | 0% |
| 30618_49fe4c54 | 0.037652351 | 0.899881383 | 0% |
| 30618_4e1e3181 | нет reference | нет reference | — |
| 30618_68847170 | 0.030245108 | 0.046760547 | 0% |
| 30618_68d1748a | 0.147618205 | 0.321360612 | 0% |
| 30618_76e1f9c7 | 0.040516075 | 0.041029762 | 0% |
| 30618_7bfbb5ed | нет reference | нет reference | — |
| 30618_95c49c30 | нет reference | нет reference | — |
| 30618_b15eafc3 | 0.032322455 | 0.033179249 | 0% |
| 30618_b8044aa0 | 0.032019489 | 0.031806330 | 0% |
| 30618_defd0170 | 0.114357219 | 0.114253227 | 0% |
| 30639_3b3d9eb8 | 0.215702210 | 0.216673117 | 0% |
| 30639_50956d6e | 0.129200873 | 0.371332086 | 0% |
| 30639_9f0b519f | 0.038139898 | 0.039010407 | 0% |
| 30639_d601d28f | 0.105715414 | 0.112789675 | 0% |

### Почему нулевой выигрыш не подтверждает гипотезу

Режим `REACQUIRING` не возник ни у одной модели: 0 тактов в clean и 0 в fault replay. Основные отказы в этом фиксированном сравнении не привели к применению ветви повторного захвата. Следовательно, общие идеи адаптивного recovery этим набором исследованы недостаточно. Конкретный кандидат всё равно отклонён по неизменному контракту: требуемого улучшения нет. Нельзя менять fault anchors, длительности или пороги после этого результата, чтобы получить принятие.

## Существенная регрессия: отдельный синтетический common-mode probe

После validation, без изменения кандидата или критериев, выполнен один диагностический сценарий из `research/H06/common_mode_probe.py`. Это **не часть общего acceptance evaluator и не метрики реальных записей**. Истинное движение порождается фиксированной физической моделью adaptive_v5 при controller=1; входы подаются через полный Observer.step: 20 Гц, свежая пара колёс 10 Гц. Оба колеса получают одинаковый ложный bias +5 м/с только на интервале [2.0,2.7) с. Начальная скорость 5 м/с, длительность наблюдения 5 с. Такой offset сохраняет динамику ускорения.

| Диагностика | Baseline | H06 |
|---|---:|---:|
| Первый ошибочный REACQUIRING, с от начала | отсутствует | 2.5 |
| Количество REACQUIRING тактов | 0 | 2 |
| Максимальная абсолютная ошибка за весь сценарий, м/с | 0.0024738417828658044 | 0.44836158257004044 |
| Максимальная абсолютная ошибка внутри fault-окна, м/с | 0.0012128920411100808 | 0.44836158257004044 |

Это реальная регрессия **в выполненной синтетической диагностике**: сокращение выдержки позволило раньше начать следование ложным согласованным колёсам. Условие сохранения защиты от такого сценария не выполнено. Постоянные ложные значения без динамики не получают бонусных свидетельств; zero-lock gate и его тесты сохранены, но это не устраняет найденный динамический common-mode случай. Результат: [common_mode_result.json](diagnostics/common_mode_result.json). Скрипт сохраняет полный `trace.csv` при воспроизведении.

## Фактически выполненные проверки

| Набор в исследовательском Actions run | Результат |
|---|---|
| Исходные dependency-free tests до экспериментального patch | 70 PASS |
| Research integrity / split / freeze / evaluator gates | 30 PASS |
| Исходный test_core после добавления default hooks | 22 PASS |
| H06 mechanism/invariant suite | 16 PASS |
| Исходные ObserverTests с подстановкой RecoveryObserver | 20 PASS |
| Train smoke, freeze, единственный validation run | завершены |
| Воспроизведение 468 baseline-полей | точное совпадение |

Это количества выполнений отдельных наборов с повторением некоторых тестов, не 158 уникальных тестов. H06 suite включает 10 000 seeded тактов побитового сравнения refactor baseline с исходным core, ограниченный шаг/память, сброс и затухание, отсутствие повторной коррекции held samples, future/nonfinite inputs, stale controller, zero-lock и явно обозначенную неоднозначность динамического common-mode сигнала. Локально тот же H06 suite ранее дал 16 PASS.

[Обычный CI измеренного source commit](https://github.com/jabrailkhalil/hack/actions/runs/36174988484) также завершился успешно: core, research-integrity, ROS Humble и offline 2 CPU / 500 MB. **Эти ROS/offline jobs используют неизменённый активный профиль, не экспериментальный RecoveryObserver.** Они доказывают сохранность текущей поставки, а не ресурсную приёмку H06.

## Исходные результаты и воспроизведение

[Полный checkpoint с 35 файлами](https://github.com/jabrailkhalil/hack/tree/6a9acd75420eb489b25734b07162179b42e1c2ab/reports/research_H06/runs/36174988639-1).
[Сырые results.json](https://github.com/jabrailkhalil/hack/blob/6a9acd75420eb489b25734b07162179b42e1c2ab/reports/research_H06/runs/36174988639-1/validation/results.json),
[per-bag.csv](https://github.com/jabrailkhalil/hack/blob/6a9acd75420eb489b25734b07162179b42e1c2ab/reports/research_H06/runs/36174988639-1/validation/per-bag.csv),
[aggregate.csv](https://github.com/jabrailkhalil/hack/blob/6a9acd75420eb489b25734b07162179b42e1c2ab/reports/research_H06/runs/36174988639-1/validation/aggregate.csv),
[decision.json](https://github.com/jabrailkhalil/hack/blob/6a9acd75420eb489b25734b07162179b42e1c2ab/reports/research_H06/runs/36174988639-1/validation/decision.json).
В checkpoint также находятся candidate-freeze, started, train/access и все test logs. [Post-validation audit](post_validation_audit.json) получен только из сохранённых результатов без повторного чтения датасета.

GitHub artifact ID `10881806571`, имя `H06-36174988639-1`, SHA256 скачанного ZIP: `ae256417226df558b9e9a9053abf61b940e2724e6c5afe420a6580981da18049`. Скачивание и локальная сверка SHA256 выполнены. SHA256 исходного results.json: `2618bdc2daebfd1cb38ed150dd63ac633bf1916adec328571c7f03a4d1935741`.

Команды измеренного протокола (полный checkout source SHA `3ab24fb...`; свежий OUT; Python 3.13.5):

```bash
python -m pip install -r requirements-research.txt
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
OUT=$(mktemp -d)
PYTHONPATH=src/reserve_odometry python -m unittest discover -s tests -v
python -m unittest discover -s research/tests -v
git apply --check research/H06/core-hooks.patch
git apply research/H06/core-hooks.patch
PYTHONPATH=src/reserve_odometry python -m unittest discover -s tests -p test_core.py -v
PYTHONPATH=src/reserve_odometry python -m unittest discover -s research/H06/tests -v
PYTHONPATH=src/reserve_odometry:tests python - <<'PY'
import unittest, test_core
from reserve_odometry.recovery import RecoveryObserver
test_core.Observer = RecoveryObserver
result = unittest.TextTestRunner(verbosity=2).run(
    unittest.defaultTestLoader.loadTestsFromTestCase(test_core.ObserverTests))
raise SystemExit(not result.wasSuccessful())
PY
python tools/get_dataset.py
python tools/research_H06/run.py --stage train-freeze --output "$OUT"
python tools/research_H06/run.py --stage validation --output "$OUT" --workers 2
```

В Actions OUT был `/home/runner/work/_temp/H06-36174988639-1`; stdout/stderr наборов сохранены через tee. Для дополнительного аудита и диагностического сценария использовать позднее добавленные report-only скрипты из этой ветки, не меняющие candidate manifest:

```bash
python research/H06/audit_results.py --evidence "$OUT" --output /tmp/H06-audit-new.json
PYTHONPATH=src/reserve_odometry python research/H06/common_mode_probe.py \
  --freeze "$OUT/candidate-freeze.json" --output /tmp/H06-common-mode-new
```

Каждый output должен быть новым. Повтор train/validation всегда выполняется на одном source commit с freeze до validation. Для точного восстановления исходного запуска использовать измеренный commit, а не текущий main. Для воспроизведения диагностического скрипта достаточно candidate-freeze из checkpoint и той же применённой runtime-реализации.

## Ограничения и итог

Новый installed ROS latency/memory benchmark именно H06 не выполнен. O(1) состояние и одинаковое расписание replay не заменяют эту проверку. Прототип не включён в ROS default. Train был ограничен execution smoke; независимых метрик точности train не получено. Повторно используемый validation не является независимым final test. Final test не переоценивался; его исторические показатели не выдаются за результаты H06. Локальная среда не могла клонировать репозиторий из-за DNS; доступ к данным, полноценное исполнение и запись evidence выполнены через GitHub Actions и connector.

**Итог: конкретный H06-кандидат отвергнут — нет прироста на неизменном реальном benchmark и обнаружена common-mode регрессия в отдельной диагностике.** Более общий вопрос об адаптивном повторном захвате требует данных, реально активирующих этот режим; он не объявляется решённым этим прогоном. Main, чужие ветки и опубликованные отчёты не изменялись; merge и auto-merge не выполнялись.
