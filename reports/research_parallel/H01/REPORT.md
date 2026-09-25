# H01 — условная компенсация возраста измерений

**Вывод: отвергнута по заранее установленному validation-контракту. Исследовательский отрицательный результат; не готов к merge.**

На development условная проекция улучшила clean и fault RMSE. На validation выбранный gain 1.0 дал лишь **0.9719% clean-выигрыша и 1.9962% fault-регрессии**. Не выполнены два условия: достаточный выигрыш и предел fault-регрессии. Успех research workflow означает завершённую процедуру измерения, не успешное прохождение accuracy-гейтов или стандартного CI.

## Происхождение и фиксация

- Baseline: `984fdf2fc4faf05325249215d6b8541c0e68209a`, профиль `adaptive_v5`.
- Предрегистрация до реализации/измерений: `711316a8a45bede8142b33b3c0c693666e4d6542`, `research/parallel/H01/PLAN.json`.
- Коммит алгоритма: `0f5457f19222ba77bd475b7a64ef09584d7df624`.
- Источник завершённого эксперимента и patch: `dcf63fb024c3c5f24237884c1ac7bc642c708a67`. До запуска исправлялась только оркестрация workflow; алгоритм, варианты, параметры и evaluator не менялись.
- [Завершённый Actions run 36175980661, attempt 1](https://github.com/jabrailkhalil/hack/actions/runs/36175980661).
- `H01_gain10` зафиксирован 25.09.2026 в 18:52:19.514634 UTC. Freeze опубликован в checkpoint-коммите `75b50f655885d26365616dca4feabaaebbd0214c` **до validation**. Config SHA256: `980951fba29067bcd6f70d52c32894a17f1cc0de4a8d20465e6aeffe9a068c23`.
- Все результаты и логи: checkpoint `fb0ac4c650faa06b7c1dfbb8c56e4446d21b4f64`, ветка `checkpoint/parallel-H01-36175980661-1`.
- Ветка реализации: `research/parallel-H01`. Эта работа не изменяла main, чужие ветки, старые опубликованные отчёты и manifests. Merge/auto-merge не выполнялись. При создании draft PR main уже был `efc473e415795d64770ef9dfa4f1bc417078da32`; сравнение осталось с общим закреплённым baseline, не с новым main.

## Механизм и отличие от отвергнутого v6

Изучены `reports/research_v6/REPORT.md`, `research/plan_v6.json`, `research/patches/v6-projection.patch` и текущий Observer. У безусловного переноса v6 gain 0.5/1.0 clean-выигрыш сопровождался fault-регрессией 0.71%/1.89%. Это историческая мотивировка, не показатели H01.

H01 меняет correction target:

```text
z_current = raw_pair_mean + gain * a_model * mean_age
```

Перенос разрешён только для двух новых samples, принятых исходными gates, при свежем controller, age <=min(max_age_s,pair_skew_s), согласии скоростей и малом raw innovation. По предыдущей принятой raw-паре вычисляются два отдельных ускорения: они должны быть физически ограничены и согласованы друг с другом и моделью. Не допускается насыщение ускорения/возмущения. Доверие выдерживается `stop_dwell_s`; hard failure или новое одиночное колесо его сбрасывает. Duplicate-only ticks не дают повторной коррекции. Поправка ограничена `rate_noise_margin_mps`, без смены направления или превышения скорости.

Только два предзаданных gain: **0.5 и 1.0**; остальные thresholds получены из baseline Config. Bootstrap, reacquisition, stop evidence, raw rate/model gates, формула disturbance adaptation, timestamps, Timeline, ROS-адаптер и физические коэффициенты сохранены. Новый параметр по умолчанию равен нулю; опубликованные adaptive_v5/default YAML и JSON не изменены.

В алгоритме только controller/front/rear; GNSS — исключительно offline reference. Нет future samples или новой задержки. Дополнительное состояние — две ссылки на raw samples и скаляры. Gate является эвристикой согласованности, не гарантированным детектором common-mode отказа.

## Данные, измеритель и разделение ролей

Архив проверен по SHA256 `d0b2483e13990edb8219b0d7bbcafc7ed001cce549a4d3af467069b2472e7d52`; split — `20928a29daad2b4178ddb92e2a4d9ddb347952f6c03845802a8d82fff7da5ae0`. Каждый читаемый bag проверен по исходному SHA256.

Development: **17 bags / 7 групп**, usable reference в 6 группах и 19 bag/receiver comparisons; **394221 matched samples**. Выполнены **56 fault replays**, 60 receiver/event comparisons с reference. Семь bags без reference сохранены в результатах, не исключены скрытно.

Validation: **19 bags / 10 групп**, usable reference в 9 группах и 30 bag/receiver comparisons; **698891 matched samples**. Выполнены **76 fault replays**, 120 receiver/event comparisons с reference. Четыре bags без reference: `30618_2255aade`, `30618_4e1e3181`, `30618_7bfbb5ed`, `30618_95c49c30`.

Использованы неизменные `evaluate.score/replay`, `ex.match/metrics`, `compare.summary/decide`: 20 Hz, alignment delay 0, одинаковые timestamps и reference-маски master/rover; исходные fault anchors/окна/прогрев; front bias +5 м/с на 5 с, both dropout 5/10 с, both lock 3 с. V4 — вспомогательная модель для совместимости evaluator, а не более слабая цель сравнения.

Evaluator/split/runtime-adapter/profile файлы побайтно сверялись с baseline через `git show`. Отключённый H01 сравнивался с оригинальным baseline Observer на каждом clean/fault replay: **73/73 development и 95/95 validation**, массивы outputs и runtime counters тождественны. Исторический v5 validation воспроизведён по **468 numeric fields**, максимальная разница **0**.

В access journal только 17 открытий purpose=development и 19 purpose=validation. Final-test measurement DB не открывались; FinalStore и final-test CLI не запускались, старые final-test показатели не использовались для выбора/описания H01. Неизменный CI отдельно проверяет hashes/membership старого final-архива, не переоценивая измерения. Validation использовался раньше и **не является независимым final test**.

## Development: два варианта, затем freeze одного

Заранее было разрешено не требовать минимального efficacy gain на development: при ранжировании игнорировалась только причина `insufficient_gain`. Все остальные v6 nonregression/safety gates и дополнительный pooled-RMSE guard 0.5% оставались обязательными. Оба варианта их прошли; выбран минимальный clean RMSE, то есть **H01_gain10**. После выбора и публикации freeze параметры не менялись. Gain 0.5 на validation не запускался.

| Модель | Clean RMSE, м/с | Fault-event RMSE, м/с | Pooled RMSE, м/с | Scalar distance RMSE, м |
|---|---:|---:|---:|---:|
| adaptive_v5 | 0.095917228 | 0.267763967 | 0.131726437 | 5.298327606 |
| H01_gain05 | 0.094737203 | 0.266074103 | 0.130756801 | 5.303837908 |
| H01_gain10 | 0.094199511 | 0.264809244 | 0.130354894 | 5.311502516 |

Gain 0.5: clean −1.2303%, fault −0.6311%, distance +0.1040%. Gain 1.0: clean −1.7908%, fault −1.1035%, distance +0.2487%. Baseline и оба кандидата: clean false-stop=0, fault false-stop=46, unrecovered=4. Дополнительных случаев нет, но исходный baseline не безошибочен.

## Validation: отрицательный результат

Δ = candidate/baseline−1; отрицательное значение означает улучшение.

| Метрика | Baseline adaptive_v5 | H01_gain10 | Δ |
|---|---:|---:|---:|
| Clean group-macro RMSE, м/с | 0.117138274 | 0.115999802 | −0.9719% |
| Fault-event group-macro RMSE, м/с | 0.538434411 | 0.549182698 | **+1.9962%** |
| Pooled clean RMSE, м/с | 0.216723603 | 0.216615522 | −0.0499% |
| Scalar span distance RMSE, м | 4.630977808 | 4.609780101 | −0.4577% |

| Условие | Фактический результат |
|---|---|
| Clean gain >=2% ИЛИ fault gain >=5% | **FAIL**: clean gain 0.9719%, fault ухудшился |
| Основные clean/fault/pooled регрессии <=0.5% | **FAIL**: fault +1.9962% |
| Aggregate distance regression <=1% | PASS |
| Per-bag/receiver clean regression <=max(0.005 м/с,5%) | PASS; худшая +0.008783 при допуске +0.010785 м/с |
| Coverage loss / изменение числа matched samples | 0; 698891 у обеих моделей |
| Дополнительные false-stop samples | 0; clean 18→18, fault 0→0 |
| Дополнительные unrecovered comparisons | 0; 0→0 |
| Causality errors / resets во всех clean/fault replay | 0 / 0 у обеих моделей |
| Полный CI и enabled-H01 ROS/resources | Не подтверждены; см. ниже |

Причины исходного `compare.decide`: **`aggregate_regression`, `insufficient_gain`**. Пороги, matching, сценарии и правила агрегации не менялись после получения цифр.

## Регрессии: не только агрегированная цифра

Диагностические разрезы рассчитаны из сохранённых raw metrics после завершения сравнения. Они не меняют selection, acceptance или результат отказа.

| Validation fault | Baseline event RMSE, м/с | H01, м/с | Δ |
|---|---:|---:|---:|
| bias 5 с | 0.414541580 | 0.414128967 | −0.0995% |
| dropout 5 с | 0.559015226 | 0.573167927 | +2.5317% |
| dropout 10 с | 0.723795502 | 0.741733784 | +2.4784% |
| lock 3 с | 0.456385335 | 0.467700116 | +2.4792% |

- `30618_0686195f/master`, lock 3 с: **0.070614→0.136952 м/с (+93.9458%)**; rover **0.072976→0.137899 (+88.9665%)**. Абсолютное ухудшение около 0.065–0.066 м/с, не только большой процент от малого baseline.
- Тот же bag/master, dropout 5 с: **0.179942→0.242306 (+34.6574%)**; dropout 10 с: **0.357999→0.409738 (+14.4522%)**.
- `30618_68847170/master`, dropout 5 с: **0.132768→0.172533 (+29.9504%)**.
- Худший clean bag `30639_3b3d9eb8`: master **0.215702→0.224485 (+4.0719%)**, rover **0.216673→0.225325 (+3.9931%)**. Формальный per-bag лимит не превышен, но это регрессии.
- Recovery увеличился на **0.1 с** в двух lock comparisons: `30618_0686195f/rover` 0.049960→0.149960 с; `30639_9f0b519f/master` 0.049522→0.149522 с. Новых невосстановлений нет.
- При улучшении aggregate distance локально хуже: `30639_50956d6e/rover` **8.194733→8.360879 м (+2.0275%)**; `30618_68847170/master` **0.609028→0.659281 (+8.2514%)**; `30618_49fe4c54/master` **0.487566→0.522532 (+7.1714%)**. Исходный лимит 1% относится к aggregate distance, не каждому bag.
- Уже development содержал компенсирующиеся fault-регрессии: `30618_88548b02/master`, dropout 10 с **0.244769→0.282944 (+15.5966%)**; `30618_27e994fc/rover`, lock **0.037436→0.062282 (+66.3714%)**. Общий development fault RMSE при этом улучшался.

Другие показатели сохранены полностью. На validation clean group-macro MAE снизился на 3.3709%, P95 — на 2.8457%, но на полном fault+recovery scoring window group-macro RMSE вырос на 1.0051%, MAE — на 0.6601%, P95 — на 1.2850%. На development MAE полного fault-window вырос на 0.9206%. Эти дополнительные показатели не были постфактум добавлены в selection-гейт и не заменяют исходные primary metrics.

Возможное объяснение по коду: выключение переноса после отказа не отменяет ранее изменённое состояние скорости/ковариации и опосредованное влияние на модельную траекторию. Слабая регрессия при front bias и более сильная при потере обоих колёс согласуются с этим объяснением. Но внутренний state trace не снимался: это **интерпретация, не доказанная причинность**. Отдельная сегментация реальных разгонов/торможений не выполнялась; отдельный выигрыш на таких фазах не заявляется.

## Проверки и runtime-ограничения

В research Actions: 22 core +10 Timeline +7 final_runtime (структурные, не final-test data) +3 candidate_config +19 H01 = **61/61 PASS**; `compileall` PASS. H01 тестирует перенос при разгоне/торможении, history/dwell, faults, дубли, future samples, saturation, reset, bounds и точное совпадение отключённого ядра с оригиналом на **10000 синтетических шагах**. Локально 19 H01-тестов также PASS. Это проверка реализации, не доказательство real-bag accuracy.

[Стандартный CI измеренного source commit, run 36175979951](https://github.com/jabrailkhalil/hack/actions/runs/36175979951): **research-integrity PASS, ROS Humble PASS, offline-limited PASS под 2 CPU / 500000000 bytes; core FAIL**. Полный идентичный unit suite в run 36175727749: 70 тестов, 66 PASS / 4 FAIL:

```text
test_active_source_hashes_are_pinned_separately
test_current_default_is_the_selected_profile
test_rejected_experimental_runtime_is_not_deployed
test_only_adaptation_changes_from_main
```

Новый core и расширенный Config не равны опубликованному старому freeze. Старые guards/хеши/профили не переписывались. Отдельный research behavior suite **не делает полный CI зелёным** и не означает готовность к promotion.

ROS/offline проверки стандартного CI запускают неизменные default/adaptive_v5 профили, то есть **gain=0**. Они подтверждают совместимость отключённой функции, не timing/RSS включённого кандидата. Отдельный ROS latency/resource benchmark H01_gain10 не выполнялся: кандидат уже отвергнут по accuracy. O(1) памяти и отсутствие нового ожидания обеспечены структурой кода; причинность и одинаковая сетка проверены real replay. Полное выполнение runtime SLO включённым H01 **не заявляется**.

После скачивания Actions-артефакта локально заново вычислены оба решения неизменным `compare.decide`: точное совпадение. Проверены все 19 frozen source hashes и SHA256 архива. Этот аудит читает сохранённые метрики, не measurement DB. Также `git apply --check` и применение измеренного patch к точному baseline core прошли; семь исходных H01 файлов после применения побайтно совпали с артефактом.

## Исходные результаты и воспроизведение

Все ссылки закреплены за завершённым checkpoint, не за подвижным main:

- [Development raw results](https://github.com/jabrailkhalil/hack/blob/fb0ac4c650faa06b7c1dfbb8c56e4446d21b4f64/reports/research_parallel/H01/36175980661-1/development/results.json), [summary](https://github.com/jabrailkhalil/hack/blob/fb0ac4c650faa06b7c1dfbb8c56e4446d21b4f64/reports/research_parallel/H01/36175980661-1/development/summary.json), [полный per-bag CSV](https://github.com/jabrailkhalil/hack/blob/fb0ac4c650faa06b7c1dfbb8c56e4446d21b4f64/reports/research_parallel/H01/36175980661-1/development/per_bag.csv).
- [Validation raw results](https://github.com/jabrailkhalil/hack/blob/fb0ac4c650faa06b7c1dfbb8c56e4446d21b4f64/reports/research_parallel/H01/36175980661-1/validation/results.json), [summary](https://github.com/jabrailkhalil/hack/blob/fb0ac4c650faa06b7c1dfbb8c56e4446d21b4f64/reports/research_parallel/H01/36175980661-1/validation/summary.json), [полный per-bag CSV](https://github.com/jabrailkhalil/hack/blob/fb0ac4c650faa06b7c1dfbb8c56e4446d21b4f64/reports/research_parallel/H01/36175980661-1/validation/per_bag.csv).
- [FREEZE](https://github.com/jabrailkhalil/hack/blob/fb0ac4c650faa06b7c1dfbb8c56e4446d21b4f64/reports/research_parallel/H01/36175980661-1/FREEZE.json), [решение](https://github.com/jabrailkhalil/hack/blob/fb0ac4c650faa06b7c1dfbb8c56e4446d21b4f64/reports/research_parallel/H01/36175980661-1/validation/decision_v6_unchanged.json), [OUTCOME](https://github.com/jabrailkhalil/hack/blob/fb0ac4c650faa06b7c1dfbb8c56e4446d21b4f64/reports/research_parallel/H01/36175980661-1/OUTCOME.json).
- [Полный каталог evidence, включая access journals и логи](https://github.com/jabrailkhalil/hack/tree/fb0ac4c650faa06b7c1dfbb8c56e4446d21b4f64/reports/research_parallel/H01/36175980661-1).

Actions artifact `H01-evidence-36175980661-1`, ID `10881578808`, 417722 bytes содержит patch, исходники, все JSON/CSV и логи, но не measurement dataset. SHA256:

```text
archive:     02ac4b37eef07238c7cff34bea8a64e3f0405f1b13ea07757558524ea4ab4940
development: ed3730359978bbf70c84f2510afe60ad26b772286cea42a42cb2f781d2b81dae
validation:  28a46be1dd45cbc7cc76111db66780b6ae51898d68467b8790170751e2afdc9a
```

Команды ниже фактически выполнены через `bash research/parallel/H01/execute.sh`; приведён удобный вариант для checkout репозитория:

```bash
git checkout dcf63fb024c3c5f24237884c1ac7bc642c708a67
python -m pip install -r requirements-research.txt
python tools/get_dataset.py
git show 984fdf2fc4faf05325249215d6b8541c0e68209a:src/reserve_odometry/reserve_odometry/core.py > /tmp/H01-baseline-core.py
PYTHONPATH=src/reserve_odometry H01_BASELINE_CORE=/tmp/H01-baseline-core.py \
  python -m unittest discover -s research/parallel/H01/tests -v
for pattern in test_core.py test_timeline.py test_final_runtime.py test_candidate_configs.py; do
  PYTHONPATH=src/reserve_odometry python -m unittest discover -s tests -p "$pattern" -v
done
python -m compileall -q src research/parallel/H01
# Новый, ещё не существующий output; не перезаписывать прошлые результаты.
python research/parallel/H01/run.py --stage development --output /tmp/H01-new-run --workers 2
# Только при наличии FREEZE.json; сначала сохранить/опубликовать freeze.
python research/parallel/H01/run.py --stage validation --output /tmp/H01-new-run --workers 2
```

Runner отказывается перезаписывать результаты и сверяет source/config/development evidence перед validation. Workflow публикует freeze до открытия validation; ошибка публикации предотвращает validation. Повтор предназначен только для воспроизведения frozen вариантов, не подбора на validation.

## Границы вывода

Отвергнут этот конкретный, заранее ограниченный механизм и выбранный development-кандидат, не любая возможная условная компенсация. Scalar distance — суррогат по интегралу GNSS-скорости на reference spans, не полноценная XY-траектория или независимая позиционная истина. Неполный reference, повторно использованный validation, common-mode неоднозначность, отсутствующая фазовая диагностика и непроверенный enabled-H01 ROS SLO ограничивают обобщение.

**Оснований объявлять H01 улучшением общего baseline или готовым к merge нет. Fault-регрессия повторилась. Новых вариантов и ретюнинга после validation не выполнялось.**
