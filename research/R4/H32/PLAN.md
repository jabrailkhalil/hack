# R4-H32 / R4-v8-fixed — PLAN до candidate measurements

## Основание и единственный механизм

Baseline e3b0c9c039d2953fbfcda51231263d38ef9f1024, tree eae49a504bc59b5c9b408445150bef32e111956f, полный canonical GuardedReadoutObserver/champion_v8. Полный ZIP проверен: 301 файл. Foundation заранее опубликован b25385074e63d7dbf5d0ce7806dd0578f5bec063, run36230458244. Baseline-only на64train/27groups/1370779ticks:93833 materially changed hypothetical drive endpoints,25 групп с>=10; порог100/3группы выполнен. Median/p95/max абсолютной разницы drive_a=.003324629/.017798271/.075026135 м/с². Эти данные использованы для постановки, но не являются candidate accuracy или независимой истиной времени привода.

Ровно один кандидат H32_event_time. Никакого fitting, L, tau sweep, изменения wheel/readout compensation. Уже полученные controller events действуют только после source timestamp внутри ещё не опубликованного внешнего шага. Для всех substeps target зависит от старой внешней скорости v_prev. Меняется только propagation drive_a; конечное a_model, Euler v, сопротивление, Q/R, disturbance adaptation, wheel gates, readout, zero-lock и quarantine неизменны. Source stamp=effective actuation является проверяемым приближением, не установленным физическим фактом. Возможен конфликт с прежней калибровкой.

Для d'= (T-d)/tau сегмент: d_next=d+(1-exp(-h/tau))*(T-d). Два target T0/T1 со сменой через s от начала: event-minus-baseline=(T0-T1)*(1-exp(-s/tau))*exp(-(h-s)/tau). Wolfram проверил равенство, T0=T1, s=0, s=h, h=0 и convex boundedness; не nonlinear stability proof.

## Точные hooks, bounded state и fallback

Изолированный hook заменяет только три строки drive propagation в точной копии Observer.step вызовом helper. GuardedReadoutObserver вызывает этот step через отдельный класс; canonical исходники не изменяются. Единственный Timeline hook после успешного ingest(0,sample) доставляет sample кандидату в фактическом порядке поступления. Для вычисления сегментов упорядочиваются только уже полученные события ограниченной очереди, не весь bag. Baseline/feature-off получают оригинальный Timeline; расписание, очереди wheel, clock/reset semantics и scorer не меняются.

Не более32 дополнительных сохранённых команд:31 pending плюс1 predecessor; горизонт.5с. Более поздние future events первыми отбрасываются при overflow/превышении горизонта; записываются счётчик и source interval потери. Это не должно влиять на outputs до source stamp потери. На затронутом интервале — явный legacy whole-step fallback; после него восстановление от свежей текущей команды. Любой current stale/invalid command, недостающий/просроченный predecessor или непокрытая история дают исходную формулу. История не продлевает timeout. Позднее событие со source<=previous_output может действовать лишь с начала следующего ещё не опубликованного интервала, без rewind. Никакой новой команды в уже опубликованном Estimate.

Равные значения команд coalesce до сегментов, чтобы constant-command arithmetic точно совпал с v8. При левограничной смене новая команда действует весь шаг; при правограничной смене её длительность0 и drive равен прогону предыдущей команды. Нельзя одновременно требовать равенства ошибочному whole-step-new-command baseline в этом правограничном случае. Feature-off всегда воспроизводит весь canonical v8.

## Санити и counterexamples

До development: полные исходные unit/integrity; специальные тесты formula/multiple events; step/impulse у обеих границ; source-future и availability-prefix; late, duplicate, malformed, overflow/horizon, stale, reset/seek; exact feature-off по полному Estimate и всем базовым полям; constant-command exact; сохранение published v/s/a согласованности; low-speed zero-lock, H11 quarantine и true-stop. Никакого будущего wheel target в runtime. Любая ошибка causality, feature-off, memory bound или safety-counterexample запрещает продвижение. Coding bug fixes до freeze с журналом допустимы без второго научного варианта.

## Development и измеритель

Все17 development bags/7 групп; один candidate. Только vehicle inputs; оба reference receivers только score. Unchanged evaluate.score/replay/match/metrics/distance, guarded aggregate/fault_windows и H11 common_fault_windows/inject_common/common_summary. Factory и прозрачный collector допускаются, формулы не меняются. Baseline реально пересчитать и сверить fingerprint: clean.09266814298282507, original fault.2375486120563008, pooled.1293056944774334,distance5.310295004801444,matched394221. Отдельный canonical driver сверяет baseline, не исторический v5 label. Same timestamps/masks/arrival order/injections. Off проверяется также на всех реальных clean/fault replays.

Original suite неизменна. Low-speed predicate из measured R3-H30 f1a940ebb8ea4694efcbc20d96b9062befdc4ab5: valid,abs(f-r)<.15,1<(f+r)/2<2,u>=0,t>max(25,.1*t_end),t<t_end-25; первый anchor,locks3/5с. H11 common-mode helper из baseline: +5м/с оба колеса на.7/1.2с. Это отдельные pinned suites, не замена original gain.

Дополнительная диагностика: первые не более3 source-command transitions |du|>=.1/bag, >=20с от начала/конца, >=10с между anchors; dropout1с с transition+.05с, 20с warmup/10с recovery. Phase error — union[t_change,t_change+2с] всех таких переходов на clean. Никакого выбора по GNSS/error. Эти suites не дают альтернативного admission.

Full-faulted-bag distance для всех original fault anchors: replay полного bag, та же scalar span distance; aggregate distance regression<=1% как дополнительный заранее объявленный guard. После recovery отчёт показывает delta_s на end+10с и на конце bag, не стирает/переякоривает её. Полные массивы сжаты в artifact, не миллионные JSON в Git.

## Все обязательные численные gates

Минимум2% clean group-macro gain ИЛИ5% original fault-event group-macro gain; clean/fault/pooled regression<=.5%; clean distance<=1%; per-bag/receiver clean<=baseline+max(.005м/с,5%baseline). Тот же n/coverage/schedule; нет added false stops, новых individual unrecovered, causal/reset errors. Low-speed/common-mode event regression<=.5%, без новых safety failures. Full-faulted original distance<=1%. Activation до validation:>=100 step endpoints отличаются>=1e-6м/с² и>=100 published velocities отличаются>1e-9м/с, >=3 исходные группы с>=10 modified endpoints. Baseline=0: только равенство0 для nonregression; null остаётся missing. Не смягчать thresholds после чисел.

Если нет activation — INCONCLUSIVE; safety counterexample либо accuracy FAIL — REJECTED. При negative development validation не открывать. Ни один текущий workflow не содержит вызова validation. Если все gates пройдены, отдельный exact-source/config/evaluator/split/data freeze commit должен быть опубликован до единственного reused validation; historical final-test не открывается.

## Стоимость, публикация и завершение

На первом development bag:10с warmup+60с;6 AB/BA пар, threads1, одинаковый collector, отдельно step CPU/replay CPU/wall и process RSS. Отдельно artificial active-path cost допустим лишь с явной маркировкой. При accuracy PASS — свежая установленная enabled ROS node в обоих clocks под2CPU/500000000bytes; иначе NOT_RUN_AFTER_REJECTION. Generic CI не является enabled-runtime benchmark.

Не менять main, чужие ветки, опубликованные manifests/reports. Новый run_id в reports/research_R4/H32. Код/PLAN/compact metrics/checkpoints в Git, compressed arrays/logs в artifacts30days. Полный source receipt, patch, reproducer и русский REPORT/SUMMARY/PR_BODY. measured_source_sha отдельно от diagnostic/report/freeze. Draft PR с честным терминальным verdict. Merge/force/auto-merge запрещены.
