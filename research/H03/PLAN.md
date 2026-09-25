# H03 — предварительный план (до экспериментов)

Baseline: `984fdf2fc4faf05325249215d6b8541c0e68209a`, профиль `adaptive_v5`, adaptation_tau_s=0.5. Рабочая ветка: `research/parallel-H03`. Main, чужие ветки, опубликованные отчёты и final test не изменяются. Merge/auto-merge запрещены.

## Механизм

В baseline disturbance обучается по разности двух новых согласованных, прошедших model-gate колёсных пар. Заменить только оценку этой производной медианой попарных наклонов (Theil–Sen) на коротком окне уже доступных доверенных пар. Не переносить скорость к текущему времени и не вводить затухание disturbance: оба механизма дали fault-регрессии в v6. В v5 дальнейшее уменьшение adaptation_tau_s до 0.25 также было хуже 0.5; tau остаётся 0.5.

Окно содержит не более 7 пар. Каждая пара поступает из двух новых FUSED samples при свежей команде. Между добавленными парами не менее 0.05 с. Используются только slopes с временной базой >=0.05 с. Для двух точек получается прежняя разность: накопление окна не задерживает публикацию. Ускорение с модулем выше существующего max_accel_mps2 не обучает disturbance; существующее ограничение disturbance сохраняется. При разрыве >max_age_s, сбросе observer, недоверенных колёсах или stale-команде экспериментальная история очищается. Prediction-only ticks не добавляют дубликаты. Общая ошибка обоих колёс остаётся неразличимой.

Добавляемый model-параметр `adaptation_window_s=0` отключает механизм и обязан воспроизводить baseline. Default и adaptive_v5 YAML не меняются. Отдельный H03 YAML будет содержать только выбранный профиль. Измерение скорости, R, gate, reacquire, stop logic, timestamps, шкала колёс и физические параметры не меняются.

## Ограниченный поиск — ровно три варианта

* H03_w020: окно 0.20 с, максимум 7 пар.
* H03_w030: окно 0.30 с, максимум 7 пар.
* H03_w040: окно 0.40 с, максимум 7 пар.

Никаких последующих вариантов, перебора tau, изменения fault-окон, порогов или reference-масок по результатам validation.

## Train и фиксация кандидата

Используется только существующий train split через неизменный research_v3.Store.load(bag, 'train'), который не читает GNSS/IMU. Внешняя accuracy-метрика для train отсутствует; не выдавать wheel-derived proxy за истинную скорость.

Диагностика на одинаковом 0.1-с grid и общей wheel-only маске: свежие согласованные колёса (|front-rear|<0.15), скорость 0.5..35 м/с, допустимая команда, полное чистое окно 11 точек и t>2 с. Offline reference ускорения: прежняя train-конвенция centered Savitzky–Golay, 11 точек, degree=2; future используется ТОЛЬКО в offline train target, никогда в observer. Для сравнения берутся общие конечные значения всех четырёх replay. Сохраняется размер общей маски и индивидуальное покрытие.

Показатели: group-macro RMSE ускорения против wheel-only proxy; group-macro RMS второй разности disturbance на непрерывных чистых тройках; диагностический lag на сетке 0/0.1/0.2 с (минимальный RMSE относительно запаздывающего target). Допускаемый дополнительный lag <=0.1 с относительно baseline; proxy-RMSE <=1.05 baseline; disturbance roughness <=0.95 baseline. Это критерии выбора по train, НЕ изменение порогов принятия v6.

Среди прошедших train-прокси выбрать минимальную roughness, при равенстве — меньшее окно. Если не проходит никто, фиксируется H03_w020 как заранее заданный диагностический кандидат с отметкой train_proxy_failed; допускается единственный validation для опровержения, без повторного выбора. Freeze.json с выбранным окном, хешами исходников/измерителя/плана и train-результатами сохраняется отдельным checkpoint-коммитом ДО открытия validation.

## Неизменное измерение и критерии опровержения

Validation: исходный validation split, оба GNSS receivers только во внешнем evaluator; это многократно использованный validation, не независимый final test. `tools/finalization/evaluate.py`, `tools/research_v3/experiment.py`, `tools/research_v3/manifest.py`, `tools/export_bags.py`, `research/split_v3.json`, `research/plan_v3.json`, `tools/research_v6/compare.py` остаются побайтно неизменными и проверяются против baseline. Score/replay/match/metrics/distance/агрегация используются из этих модулей. Alias baseline_v2 означает adaptive_v5, balanced_physics — один зафиксированный H03; это служебные имена evaluator, не другие baseline.

Fault anchor и четыре сценария на bag в точности из v6: первая допустимая точка valid & mean_wheel>2 & t>max(25,0.1*t_end) & t<t_end-25; bias front +5 м/с на 5 с, dropout обоих на 5/10 с, lock обоих на 3 с; тот же warmup и recovery window. Никаких новых более удобных масок или fault-сценариев.

Принятие: >=2% clean group-macro RMSE gain ИЛИ >=5% fault-event group-macro RMSE gain; регрессия clean/fault/pooled RMSE <=0.5%; distance group-macro RMSE <=1%; каждый clean bag/receiver <= baseline + max(0.005 м/с, 5% baseline). Нельзя терять n/coverage, добавлять false stops на любом clean/fault сравнении, увеличивать число unrecovered, нарушать расписание, причинность или сбросы. Все нарушения выводятся явно; значимые per-bag и fault-регрессии сохраняются, даже когда агрегат лучше. Сравнение baseline с опубликованным v5 — sanity check, не новые данные.

Гипотеза отвергается как merge-кандидат при непрохождении любого условия. Недоступные измерения/данные/runtime дают «недостаточно данных», а не нулевые ошибки или вымышленные прогоны. При непрохождении train-прокси успешный validation сам по себе не доказывает заявленный механизм уменьшения шума.

## Runtime и доказательства

Runtime inputs: только controller/front/rear; no GNSS/IMU/future. Окно <=7, slopes <=21, фиксированная ограниченная память, без sleep/ожидания future и новых зависимостей runtime. Сохраняются 20 Гц и существующая временная логика. Unit tests: affine/irregular slopes, common outlier, gap/reset, rejected/stale/duplicate/future samples, причинный prefix, bounded memory, disabled baseline parity. Реальный replay и microbenchmark не заменяют установленный ROS benchmark 2 CPU/500 MB; невыполненные ROS/latency проверки явно остаются ограничением.

Сохранять run_id/run_attempt/H03 в checkpoint-ветках и директориях, started/access/freeze/results/decision JSON, per-bag JSON и CSV, команды и фактический статус проверок. Исходный final test не открывается, не запускается и не используется для выбора. Публикация draft PR на русском обязательна; при неподтверждённом улучшении — исследовательский результат, не готовый к merge.
