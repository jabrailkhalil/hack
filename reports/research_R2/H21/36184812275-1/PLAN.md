# R2-v7-fixed / H21 — PLAN до экспериментов

Baseline: 65bba39ed05c781f3f69a65c02f69931152cbfd9. Canonical GuardedReadoutObserver, guarded_readout_v7.yaml, Estimate.v/s, 20 Hz, delay=0, readout gain=1 / holdoff=.5, inner compensation=0, adaptation_tau=.5. Main/H11/v8 не включать. Ветка research/round2-H21 создана от этого SHA. Предшествующий source-export только архивировал baseline; inherited CI проверял неизменённый baseline, не кандидата и не accuracy.

## Механизм, один вариант, без fitting

Один кандидат H21-envelope. Дополнительные скаляры [v_lo,v_hi,drive_lo,drive_hi], время anchor/доверия/ambiguity и счётчики. Он не изменяет основное numerical prediction, физические коэффициенты, Q/R, readout, stop, hard gates, bounded recovery или Timeline. Отдельный no-op hook ПОСЛЕ исходных hard gates и разрешения competing pair, ДО fusion: может удалить лишь уже допустимое слабое измерение; не создаёт измерения, скорость или остановку. Исследовательский core-hooks.patch применяется только в изолированной копии. Активный core и опубликованные pins не переписывать.

Anchor условный: обе свежие согласованные колёсные скорости, принятые основным observer; разность <=3*wheel_sigma, residual каждого <=innovation_floor; .5 s непрерывно healthy held evidence, anchor только на FUSED. Начальный диапазон среднего z: +/-[3*wheel_sigma + max_accel*mean_age]. Согласие пары НЕ даёт независимого 1/sqrt(2) сужения и НЕ доказывает отсутствие common bias. Внутри активной эпохи не пересекать интервал с wheel measurements и не переякорять его. Начальный drive interval — полный физический [-max_brake_force/mass, efficiency*gear*torque/(radius*mass)] с учётом travel_direction, НЕ точечный inner drive. Модельная additive uncertainty +/-disturbance_limit=.6 m/s^2; это условное ограничение, не доказанный bound настоящего трамвая. Не использовать адаптированный disturbance как независимую истину.

Propagation: расширить velocity tube на +/-max_accel*dt, ограничить физическим max_speed. Для u>=0 экстремумы torque/power target находятся по minimum/maximum |v| на ВСЁМ tube; для u<0 -q*B*tanh(v/.2) монотонно убывает. Resistance монотонно возрастает, его extrema на концах tube. Для изменившегося causal ZOH controller взять hull предыдущего и текущего command targets (и u=0 при смене знака), при stale — полный физический target. rho=exp(-dt/tau); распространить drive endpoints rho*a+(1-rho)*target, взять hull старого/нового drive на шаге. Bound g=[drive_min-resistance_max-D, drive_max-resistance_min+D], clip по +/-max_accel. V_next=clip([V_lo+dt*g_lo,V_hi+dt*g_hi],+/-max_speed); включить 0 при возможном переходе через ноль. Это enclosure условной clipped модели при указанных anchor/error/ZOH допущениях, не гарантированное множество истинных скоростей. Расширение без измерений, исключая насыщение полными физическими пределами.

Supervisor активен при возрасте anchor <=2 s и ширине <=innovation_cap=3 m/s. Измерение сравнивать с V_next, дополнительно расширенным на max_accel*measurement_age+3*wheel_sigma. Удалять только measurement с |z-predicted|<=innovation_floor=.8 и |z|>stop_model_speed=.25; сильные corrections, zero-lock/stop и recovery не подменять. Внешняя проверка не может разрешать уже запрещённые hard gates. При пустом пересечении: статус REACHABILITY_AMBIGUOUS, оставить полный prior interval, не прижимать velocity к wheel. Максимум .5 s последовательной ambiguity, затем отключить supervisor, очистить anchor и запретить новый anchor ещё .5 s. Ширина>3 либо возраст>2 отключают supervisor до нового условного anchor после новой healthy выдержки; неисправные колёса не заблокированы навсегда. Off — буквально canonical baseline; широкая uncertainty — базовое поведение.

Фиксированные числа выведены из существующих physics/gates плюс заранее заданные 2 s lifetime и .5 s dwell/release. Бюджет=1, никаких альтернатив/подбора после development или validation. Ошибки реализации можно исправить до dataset measurement с сохранением истории. После первого development replay параметры и механизм заморожены; infrastructure/diagnostic fixes не меняют измеренный алгоритм и требуют отдельной provenance.

## Отличия от прежних попыток и источники

H08 менял квадратуру и ухудшил faults; здесь основное предсказание неизменно. H06 менял recovery и продемонстрировал опасность динамически согласованной ложной пары; recovery здесь неизменен. v6 projection/decay и H02 covariance weighting не используются. PR14/23 readout и zero-lock сохранены. H11/26 блокирует recovery после abrupt common RATE_ANOMALY; это НЕ наш механизм, его код не включать.

Научный ориентир: Huang, Application of interval state estimation in vehicle control, DOI 10.1016/j.aej.2021.04.074, AEJ 61(1), 911–916 (2022); прочитан abstract издателя и результаты узкого Consensus search/fetch. Другая LPV модель и simulation, не доказательство нашего bound. Scite metadata/fulltext/citation context недоступны: месячный MCP лимит, конкретный ответ сохранить; подписки не покупать. Wolfram worksheet: observability matrix для x=[v,d,b], A={{0,1,0},{0,0,0},{0,0,0}}, C={{1,0,1}}, rank/nullspace, g signs, positive propagation coefficients, saturation order, physical dimensions и dt->0. Вывод сохранить фактически, без выдуманного PASS.

## Данные, этапы и покрытие

Роли берутся неизменно из research/plan_v3.json и split_v3.json. Train: все 64 bags, только три vehicle-топика, без GNSS; pseudo-label не независимая истина. Development: ВСЕ 17 bags / все manifest groups; отдельный read-only role-checked loader, GNSS только во внешнем evaluator. Тот же pinned SQL order, decoder, scales, timestamps. Test payload не открывать. Archive download/extraction сам по себе не evaluation; SQLite measurement IO только разрешённых ролей.

До candidate compare воспроизвести canonical baseline отдельной factory, сверить off Estimate/status/counters и весь baseline state потактово. Factory observer явно GuardedReadoutObserver, не adaptive_v5. Новый research source manifest, старые pins не менять. Score/match/distance/fault placement/aggregation только неизменённые функции baseline, в ev.score подменяется лишь factory; source hashes проверяются.

Sanity: unit/integrity базовые отдельно, candidate safety и bound tests, off equivalence, prefix causality, repeated/stale/future/NaN/reset, signed movement, zero-lock/true stop, bounded memory; случайный seed=2107. Не выдавать тест модели за real accuracy.

Development original suite: исходные front+bias5 на5s, both dropout5/10s, both lock3s, anchors из existing fault_windows. Дополнительные, ОТДЕЛЬНО: prolonged dropout30s; common drift +/-1.5m/s^2 до +/-3m/s (ramp2s, hold2s, затем normal wheels), те же разрешённые anchors и warmup20s/recovery10s. Никакой injected flag в runtime. Синтетика отдельно: true disturbance step +/-0.6; genuine braking to stop; common slow drift; long dropout; reverse direction. Естественную смену нагрузки диагностировать на clean development через wheel acceleration residual, не считать её подтверждённым physical ground truth. Phase traces до/во время/после, interval width, anchor count, eligible/veto/ambiguity/wide ticks, actual GNSS interval coverage как ВНЕШНЯЯ диагностика.

Классификация veto внешним evaluator: все доступные GNSS в пределах .25 m/s от wheel и вне expanded interval — false rejection; все дальше .5 — fault-consistent rejection; промежуточное/missing — ambiguous/unlabelled. Не маскировать missing нулём. Threshold достаточного покрытия: >=200 активных ticks и >=20 veto ticks суммарно в real development+заранее заданных diagnostic injections минимум в двух исходных группах; off alone не покрытие. Если нет активации — INCONCLUSIVE, не опровержение семейства. Любое подтверждённое veto настоящего движения/остановки, новые false stops/unrecovered, causal/reset failures — REJECTED, не расходовать validation.

Для validation требуется также прохождение общего accuracy-контракта на development original suite. Если candidate действует, но контракт не проходит, REJECTED на development и validation не запускать. Если покрытия достаточно и development contract/safety PASS, отдельный freeze commit с SHA и hashes кода/patch/config/data/split/evaluator/driver, затем ровно один paired validation всех19 bags; никаких новых вариантов. Final test всегда закрыт. Validation reuse раскрывать, не independent final.

## Неизменный общий контракт R2

Clean group-macro RMSE gain >=2% ИЛИ original fault-event group-macro gain >=5%. Clean/fault/pooled aggregate regression <=.5%, scalar-span distance <=1%; clean per-bag/per-receiver <=base+max(.005m/s,.05*base). Coverage и n не терять; false stops по каждой паре не повышать; новых unrecovered cases (по каждой паре, а не только сумме), causal errors и unexpected resets не допускать. Base=0: абсолютная разрешённая aggregate delta 1e-12 только roundoff, выигрыш по этому нулевому знаменателю не засчитывать. Missing aggregates=>INCONCLUSIVE. Отдельный driver дополняет legacy gate pooled/per-case recovery guards, не меняет старые критерии. Показать MAE, signed bias, recovery и все существенные местные regressions. Приёмники одной bag не независимые поездки, группировка исходная.

## Стоимость и публикация

На первых60s первого development bag, 1 AB warmup +5 AB/BA measured pairs, OPENBLAS_NUM_THREADS=OMP_NUM_THREADS=1; одинаковый output collector. Replay CPU/wall отдельно от step CPU и RSS. ROS latency не выводить из replay. Если accuracy REJECTED или INCONCLUSIVE, full installed ROS benchmark не запускать и прямо указать; при accuracy PASS нужен свежий installed enabled candidate, оба clock modes, offline 2 CPU /500000000 bytes.

Команды (новый OUT каждый раз):
```
python -m pip install -r requirements-research.txt
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
python tools/get_dataset.py
PYTHONPATH=src/reserve_odometry python -m unittest discover -s tests -v
python -m unittest discover -s research/tests -v
python research/R2/H21/tests.py
python research/R2/H21/run.py --stage train --output "$OUT/train"
python research/R2/H21/run.py --stage development --output "$OUT/development"
# Только если prevalidation PASS:
python research/R2/H21/run.py --stage freeze --development "$OUT/development" --output "$OUT/freeze"
# Публикация freeze отдельным commit ПЕРЕД этой командой:
python research/R2/H21/run.py --stage validation --freeze "$OUT/freeze" --output "$OUT/validation"
```

Evidence: reports/research_R2/H21/<run-id>/, отдельная checkpoint/R2-H21-<run-id>-<attempt>, без raw bags/secrets/cache. Измеренный candidate SHA отдельно от later report SHA. Draft PR по-русски с CONFIRMED/REJECTED/INCONCLUSIVE, mechanism verdict и merge readiness отдельно. Отрицательный/неполный: «исследовательский артефакт, не готов к merge». Не merge/auto-merge/force-push, не менять main/чужие ветки/опубликованные reports.
