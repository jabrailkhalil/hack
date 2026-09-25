# H02 — предварительно зафиксированный протокол

Baseline первого раунда: `984fdf2fc4faf05325249215d6b8541c0e68209a`, профиль `adaptive_v5`.
Ветка: `research/parallel-H02`. Никаких merge, auto-merge, изменений main, чужих веток или опубликованных отчётов.

## Механизм и ровно один вариант

Значения принятых измерений, их арифметическое среднее z, stamps, schedule, gates, bootstrap, recovery, stop и disturbance adaptation непосредственно не менять. Добавить только неопределённость времени в R штатной коррекции:

```
A = max(max(0, now - sample.t) for accepted samples)
S = abs(front.t - rear.t) if both samples accepted else 0
sigma_a = 0.5 * config.max_accel_mps2
R = [sigma_wheel^2 + sigma_a^2 * (A^2 + S^2/4)]
    * confidence_factor * residual_factor
confidence_factor = 1 for two accepted agreeing contemporaneous wheels, else 4
residual_factor = max(1, abs(z - predicted)/(3*sigma_wheel))
```

`confidence_factor` и `residual_factor` — существующая логика baseline. Деления R на число колёс нет: согласие не является независимостью. Используется максимальный возраст, а не оценённое ускорение для переноса z. `S^2/4` — ограниченная добавка для асинхронной пары; это консервативная эвристика, не доказанная калибровка covariance. При отключённой добавке baseline должен воспроизводиться точно. При нулевых A,S коррекция должна совпадать с baseline.

Единственный кандидат: `H02_timing_05`, новый параметр `timing_accel_fraction=0.5`. Диапазон допустимой настройки [0,1], default 0 отключает механизм. В этом раунде **нет поиска других коэффициентов и нет настройки после validation**. Число кандидатов: 1. Параметр выбран априорно как половина существующей границы ускорения, не по данным. Потенциальный эффект — меньше устаревшего колёсного воздействия; потенциальная регрессия — усиление ошибки модельного прогноза и косвенное изменение последующих gates/adaptation.

## Почему такой протокол

Изучены reports/research_v6/REPORT.md и reports/research_v5/REPORT.md. Проекция 0.5/1.0 в v6 улучшала clean, но ухудшала fault выше 0.5%. Изменение process noise в v5 также давало fault-регрессии и ложные остановки. Поэтому H02 не изменяет Q, не переносит измерения, не ослабляет gate и не считает correlated wheels независимыми.

Store.load(train) разрешает только controller/front/rear и не возвращает GNSS-reference. Этот запрет не обходить. Train использовать для причинности, расписания, конечности и воспроизводимости отключённого механизма, не выдавая wheel agreement за независимую точность. Никаких final test payloads, final test результатов, FinalStore или пересчёта старого test.

## До validation

Сначала зафиксировать исходники кандидата и тесты, выполнить structural/unit и доступные train replay проверки. Создать отдельный freeze с commit, хешами алгоритма, профиля, плана и evaluator; только после сохранения freeze допускается validation. При нарушении train-инвариантов остановиться. Изменение реализации для исправления ошибки должно быть явно отражено в журнале до открытия validation. После validation алгоритм и коэффициент не менять.

## Один измеритель

Не менять `tools/finalization/evaluate.py`, `tools/research_v3/experiment.py`, `tools/research_v3/manifest.py`, `tools/export_bags.py`, `tools/research_v6/compare.py`, frozen split/plan или архивы. Вызывать существующие score/replay/metrics/match/distance и summary. Baseline и кандидат получают одни и те же events, output timestamps, reference masks, оба GNSS receivers. 20 Hz, alignment_delay_s=0. Fault anchor и четыре сценария строго как в v6: первый допустимый anchor, bias 5 s, dropout 5/10 s, lock 3 s, то же окно и восстановление. Дополнительный reference-free train replay не является новым acceptance evaluator.

## Неизменные критерии опровержения

Минимум 2% clean group-macro RMSE gain ИЛИ 5% fault-event group-macro RMSE gain против adaptive_v5. Регрессия каждой основной агрегированной метрики не более 0.5% (включая pooled RMSE), distance group-macro не более 1%. Per-bag/receiver clean RMSE не хуже baseline + max(0.005 m/s, 5% baseline). Нельзя терять n/coverage, добавлять false stops, unrecovered faults, причинностные ошибки, сбросы или менять расписание. Проверить runtime ограничения: входы только vehicle/controller/front/rear, bounded memory, 20 Hz без ожидания будущих samples, прежние 2 CPU / 500 MB и latency требования. Unit и offline скорость не заменяют ROS runtime benchmark.

Если candidate нарушает gate или не достигает gain — отрицательный исследовательский результат, НЕ merge-ready. Если отсутствуют данные/reference, исполнение или необходимые runtime проверки — явно `недостаточно данных` для подтверждения, с отдельным перечислением доступных отрицательных свидетельств. Повторно используемый validation не является независимым final test даже при прохождении gates.

## Артефакты

Сохранить команды, журналы доступа, хеши, baseline reproduction, агрегированные и per-bag/receiver JSON/CSV, все причины отклонения и ограничения. Каждому запуску — новый `reports/research_H02/runs/<run_id>-<run_attempt>/` и своя `checkpoint/H02-<run_id>-<run_attempt>`; опубликованные отчёты не переписывать. Draft PR на русском с фактически выполненными проверками; не заявлять ещё не завершённые CI, измерения или PR.
