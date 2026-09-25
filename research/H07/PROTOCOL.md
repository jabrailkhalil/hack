# H07 — разная динамика тяги и торможения: протокол до экспериментов

Статус: зарегистрирован до чтения новых измерений и подбора H07. Baseline первого раунда: `984fdf2fc4faf05325249215d6b8541c0e68209a`, профиль `src/reserve_odometry/config/adaptive_v5.json` / `.yaml`. Ветка: `research/parallel-H07`. Main, чужие ветки, опубликованные отчёты и final-test не изменяются. Merge и auto-merge запрещены.

## Изученные предшествующие результаты

- `reports/research_v3/REPORT.md`: balanced_physics идентифицировала семь эффективных параметров на wheel-only train; gain_only не достиг 2% clean gain. Общая actuator_tau_s = 0.3927619145850434 с. Это эффективная динамика, не паспортная характеристика привода. Колёсная псевдоразметка может содержать common-mode slip.
- `reports/research_v5/REPORT.md`: ускорение disturbance-адаптации немонотонно по качеству; 0.25 с хуже принятой 0.5 с. Process-noise x4 добавлял ложные остановки. Поэтому adaptation_tau_s, шум и gate в H07 заморожены.
- `reports/research_v6/REPORT.md`: projection/decay давали clean gain ценой недопустимой fault-регрессии. Нельзя подтверждать H07 только чистой ошибкой или offline fitting loss. Validation уже использовался повторно; это не независимый final test.

## Механизм и границы изменения

Один существующий скаляр drive_a сохраняется. При действующей нормализованной команде u > command_deadband использовать traction_tau_s, при u < -command_deadband — braking_tau_s; внутри deadband и при stale/invalid/future команде — исходную actuator_tau_s. Обновление остаётся drive_a += (1-exp(-dt/tau))*(drive_target-drive_a). Выбор режима определяется только причинно доступной controller-командой, не GNSS, не будущим измерением и не знаком скорости (торможение также работает при движении назад). Это проверка реакции на текущую команду, не отдельная идентификация release/hysteresis.

Два новых параметра равны 0 по умолчанию: каждый независимо наследует actuator_tau_s. В таком режиме поведение должно побитово совпасть с baseline. Положительные значения включают H07. Состояние, ограниченная память, входы controller/front/rear, 20 Гц, delay_s=0, timestamp logic, маски, gate, stop/reacquisition, disturbance, физические gain и wheel scale не меняются. Runtime не получает SciPy/NumPy.

## Заранее ограниченный поиск: ровно шесть кандидатов

Пусть tau0=0.3927619145850434 с. Пары (traction_tau_s/tau0, braking_tau_s/tau0), в порядке разрешения точных ничьих:

1. T05_B10: (0.5, 1.0)
2. T10_B05: (1.0, 0.5)
3. T20_B10: (2.0, 1.0)
4. T10_B20: (1.0, 2.0)
5. T05_B20: (0.5, 2.0)
6. T20_B05: (2.0, 0.5)

Дополнительная контрольная модель: исходный adaptive_v5 (не седьмая гипотеза). Непрерывная оптимизация, расширение сетки и повторный подбор после validation не разрешены. Все остальные параметры берутся из baseline adaptive_v5 без изменения.

## Идентификация и выбор — только train

Использовать неизменные split_v3/plan_v3 и Store.load(bag, 'train') с проверкой роли до SQLite IO. Development разрешён владельцем, но в данном протоколе не используется. Не открывать train GNSS. Повторно использовать training_set из tools/research_v3/experiment.py: тот же deterministic sample selection, quality mask и offline Savitzky–Golay wheel-acceleration target. Центрированная производная допустима только для offline train target; её нет в runtime.

Идентифицируется только пара постоянных времени из указанной сетки. Сохраняется один drive-state с исходной дискретизацией offline acceleration() (dt=0.1), но alpha выбирается по режиму. Считаются train weighted acceleration RMSE и soft_l1 objective с f_scale=0.1. Веса: те же group weights и mode balance, что balanced_physics; все кандидаты на совершенно одинаковых точках/весах. Выбирается один кандидат с минимальным soft_l1 objective; точные ничьи разрешаются порядком выше. Даже при отсутствии train gain можно один раз проверить выбранного кандидата, но train loss не является доказательством точности одометрии.

До открытия любого validation-bag сохранить selected.json, полный config, SHA256 протокола/runner/core/evaluator/split/модели и train-access journal. Зафиксировать эти артефакты отдельным git-коммитом checkpoint/H07-<run_id>-<run_attempt> ДО validation. Без успешной фиксации validation не запускается. Runner validation не выбирает и не меняет параметры.

## Общий неизменный измеритель

tools/finalization/evaluate.py и tools/research_v3/experiment.py из baseline остаются побайтно неизменны. Score, match, metrics, distance_surrogate и fault-сценарии берутся из них; summary/reproduction/decide — из неизменного tools/research_v6/compare.py. Не вызываются finalization main/FinalStore, stage test или verify_freeze исторического test.

На validation одновременно повторяются v4 (только для исторической проверки), v5 baseline и один frozen H07. Используются все 19 validation-bag, оба GNSS receiver без отбора, исходные 76 fault-сценариев (bias 5 с, dropout 5/10 с, lock 3 с), те же timestamps, reference masks и group aggregation. Baseline должен повторить опубликованные числовые поля v5 с допуском 1e-10; кандидат сравнивается с НОВЫМ измерением baseline, не с перенесёнными историческими числами.

Основные критерии v6 неизменны: не менее 2% clean RMSE gain ИЛИ 5% fault-event RMSE gain относительно adaptive_v5; регрессия каждой основной агрегированной метрики не более 0.5%, scalar-distance не более 1%; per-bag/receiver clean RMSE рост не более max(0.005 м/с, 5%); нулевая потеря coverage/числа точек, отсутствие дополнительных false stops/unrecovered случаев, resets/causality errors. Для pooled RMSE также явно проверяется ограничение 0.5%: оно заявлено в общем контракте, хотя исторический decide() отдельно его не проверяет. Это заранее добавленная проверка контракта, не изменение измерителя или смягчение порога.

Дополнительная описательная диагностика без влияния на выбор: ошибки на первых 2 с после смены режима controller (traction/coast/braking), по каждому типу fault и каждому bag/receiver. Маска переходов строится только по прошлым controller stamps, одинакова для baseline и H07; reference matching/metrics те же. Недостаток reference сохраняется как null, не 0. Диагностика не заменяет общие acceptance gates.

## Опровержение, остановка и отчётность

H07 отвергнута для данной сетки/набора, если frozen кандидат нарушает любой gate либо не достигает минимального выигрыша. После отрицательного validation не подбирать заново. Недостаточно данных — если нет доступа к данным/runner, воспроизводимость baseline нарушена или validation не завершён. Никакие синтетические/unit результаты не выдаются за real-bag accuracy.

Сохранить все train-варианты, исходные результаты, per-bag/receiver metrics, access journal, hashes, команды, фактически выполненные unit/integrity/runtime проверки и все существенные регрессии. Результаты только в новых H07 run_id/run_attempt каталогах и checkpoint-ветке; существующие отчёты не перезаписывать. Проверка ROS/resource limits должна быть новой; история v4/v5 не является benchmark H07. До такой проверки не заявлять подтверждение latency/resource контракта.

Финальный draft PR на русском: подтверждена / отвергнута / недостаточно данных. Неподтверждённое улучшение явно обозначить исследовательским отрицательным/неподтверждённым результатом, не готовым к merge. Main default не переключать; merge/auto-merge не выполнять.
