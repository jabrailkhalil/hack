# Итог: NO_MERGEABLE_CANDIDATE — не сливать

Задача: получить подтверждённо лучший текущего main кандидат, а не ещё один формальный MR. **Merge-ready PR не создан: проверенные варианты не прошли критерии.** Снижение одной fault-метрики не выдаётся за общую победу.

Baseline: `b2783206000091ab11a1c11ac3ff79082188a4fb`, tree `973d50d288e050325ee1c71a90fa8d81f2a099af`. Live main повторно проверен после экспериментов: та же версия. Полный v8 GuardedReadoutObserver и полный champion_v8.yaml, не Config defaults. Все 320 исходных файлов, профиль, scorer, timestamps, reference masks, anchors, split и старые отчёты сохранены. Main/чужие ветки не менялись; merge/auto-merge/force-push не выполнялись.

## Фактическое сравнение — development

G: одна GNSS-supervised физическая калибровка по H44-протоколу. W: согласованный wheel-target контроль, не выбираемый запасной кандидат. I01: новый причинный state-aligned reserve с замороженным G-shadow.

| Метрика; меньше лучше | main | G | W | I01 |
|---|---:|---:|---:|---:|
| Clean group-macro RMSE, м/с | 0.092668143 | 0.092444346 | 0.092451005 | 0.092662954 |
| Original fault-event RMSE, м/с | 0.237548612 | 0.214494065 | 0.223379997 | 0.232415427 |
| Clean pooled RMSE, м/с | 0.129305694 | 0.128915547 | 0.128939626 | 0.129302953 |
| Clean distance proxy, м | 5.310295005 | 5.368194377 | 5.356119428 | 5.307511987 |
| Full-faulted-bag distance proxy, м | 6.269376947 | 6.509833196 | 6.477325282 | 6.434508437 |
| H11 event RMSE, м/с | 0.100632272 | 0.083596132 | 0.085500861 | 0.099854698 |
| Low-speed event RMSE, м/с | 0.368545673 | 0.340805238 | 0.357994535 | 0.368046643 |

Это скалярный GNSS speed/distance proxy, **не официальный XYZ score**. Distance — неизменный reanchored_span_rmse_m по доступным reference spans; полного reference для каждой секунды нет. Full-faulted записи проиграны от начала, а накопленная delta_s не стиралась при recovery.

## Почему не merge

**G:** original fault gain 9.705191%, но clean distance regression 1.090323% и full-faulted distance regression 3.835409% при лимите 1%. На frozen check нарушен per-group предел в `0d4506540f0e7621` и `dc785decbed3d7ce`. При диагностическом исключении группы `8269991eafa82c45` fault RMSE уже ХУЖЕ main на 20.194830%. Группа не удалена из главного score. Специфическая польза GNSS против W не подтверждена: fault gain G/W только 3.977944%, ниже attribution-порога 5%.

**I01:** fault gain 2.160899%, ниже требуемых 5% при отсутствии clean gain 2%; full-faulted distance regression 2.633938%. Check veto в трёх группах. Один вариант, 0 новых fitting calls, без post-hoc tuning. План опубликован до реализации/replay: `2b6277fe1c3dda08b17c4858deb1b8cea8f1a951`, `research/final_causal_reserve/PLAN.md`. Runtime сохранён в `research/R5/FINAL/causal_reserve.py`, source commit `ef851dde45d890f83597bf73d9d9c14005ad3bf7`; обычный checkout его не включает. Потребитель исследовательского класса использует возвращаемый Estimate; last_estimate намеренно остаётся main-output для полной state isolation. Дизайн мотивирован просмотренными development-результатами: это exploratory, не независимая проверка.

**H45 scale:** A=0.9996429879949134; B=(0.9996430719059628,0.9996429040847155). 5+6 objective calls, 22116 fit/8253 check интервалов в 16/6 группах. Identity check Huber 0.018274363747490988 → A 0.020274347641240725: regression 10.944205%. Scale development не запускался.

## Данные и реальные проверки

Получены исходные H42/H43 ZIP из Library; transport/CRC/manifest PASS, native teacher verifier 85 files/64 train arrays PASS, atlas verifier 53 files PASS, фактический semantic fold bridge 64 назначений PASS. Teacher/atlas не пересозданы. Полный dataset ZIP и 81 разрешённая DB проверены по hashes. Извлечены только 64 train и 17 development. Fitting G/W: 141 fit-window/15 groups и 54 check-window/5 groups, одинаковые окна/веса, настоящий scalar observer, 36+87=123 фактических residual calls включая numerical Jacobian, без restarts.

G F/m,P/m,B/m = [1.288533438861773,10.72819314542046,0.8221194868508274]; W = [1.2312810632970033,9.653188178443996,0.8221201636602369]. Меняются только исходные torque/power/brake; readout, gains, физическая структура и gates неизменны. Никакой GNSS/teacher/bag ID/fault oracle в runtime.

17 clean bags, 56 original cropped faults, те же 56 полных faulted bags, 28 H11, 26 low-speed случаев. 6 reference-bearing clean groups, 394221 scored receiver-samples — не независимые поездки. Baseline заново воспроизведён с нулевым расхождением fingerprint. Новых false stops/individual unrecovered нет. Старые неподтверждённые recovery сохранены: original4/H11 2/low-speed6; не объявлены нулём. Максимальная ошибка delta_s=integral(delta_v): 5.8051e-11 м. Сохранены prefault state, signed integrals, +10s и terminal delta_s, все локальные регрессии и leave-one-group-out.

161 canonical +43 research-integrity +29 новых tests финально PASS. На чистом новом root повторены dependency checks, tests и baseline replay. Wolfram проверил algebraic identities; это не доказательство accuracy. Consensus/Scite вернули месячный quota limit, новые статьи через них не получены.

Scalar benchmark python -S, 10s warmup+180s, три AB/BA цикла: median main11.217µs/G11.037µs/I01 28.608µs. I01 примерно2.55x дороже. Это НЕ ROS topic latency или deployment certification. Enabled installed ROS/оба clock modes/лимиты2CPU500MB не измерялись после accuracy rejection.

**Validation/final-test measurement DB не извлекались и не открывались.** Нет validation freeze или утверждения о новом CI success. Два driver/JSON serialization сбоя и synthetic fixture исправление документированы; fitted параметры/scorer не менялись, повторные прогоны не считаются независимыми экспериментами.

## Передача

Полный self-contained source snapshot, fit/replay/check drivers, frozen configs, подробные метрики и receipts переданы в conversation-артефакте `odometry_final_research_20260926.zip`; patch — `odometry_final_research_20260926.patch`, полный replay archive отдельно. В этой GitHub-ветке сохранены preregistration, исследовательский runtime и этот compact report, а не весь локальный evidence payload. Архив включает offline reproduce.py с проверенным режимом baseline; четыре исходных source/dataset/teacher/atlas ZIP обязательны. Обычный main v8 остаётся выбранным решением.
