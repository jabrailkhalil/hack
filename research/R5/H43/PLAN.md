# R5-H43 — AUDIT, план до измерений

Только карта ошибок фиксированного v8 и аудит одного опубликованного H36. Новых fitting/teacher/map/runtime candidates нет. Bootstrap source/dataset выполнен, извлечены только 17 development DB; measurement SQL до этого плана не выполнялся. Main, чужие ветки и старые отчёты не менять. Merge/auto-merge/force запрещены.

## Источники
Baseline b2783206000091ab11a1c11ac3ff79082188a4fb, tree973d50d288e050325ee1c71a90fa8d81f2a099af. Полный source ZIP проверен штатным R5 verifier. Двенадцать numerical/profile/scorer/split файлов побайтно совпали с прежним e3b0c9c039d2953fbfcda51231263d38ef9f1024. GuardedReadoutObserver, все поля champion_v8.yaml, Estimate.v/s,20Hz/delay0,readout1/.5,tau.5,quarantine1.5.
Dataset SHA256 d0b2483e13990edb8219b0d7bbcafc7ed001cce549a4d3af467069b2472e7d52. Только development17/7groups; SQLite read-only controller/front/rear и master/rover GNSS velocity внешнему scorer. Train/validation/test не открывать. Полный Q&A уточняет: raw GNSS не официальный fused /localization/kinematic_state; primary proxy-score не изменяется.
H36 source4bd4908821e55e08195f08bd88eb7cfab17dc3c7, profiled.yaml blob daf4877655dbf0716c0fb1e4f17d331c84becf64. Remote compare: runtime/scorer неизменны, добавлены research files. Локальный3a1843... и control b=0 исключены; связь версий не установлена. Report216d85... — историческое свидетельство, не заново проверенный optimizer.

## Бюджет: baseline, H36, ровно две вложенные ablations
main — полный v8; h36 — тот же класс, точный H36 YAML с начала replay.
coherent — v8 до первого output tick t>=fault.start, затем смена только config на H36. Вся предыстория v/drive/d/P/readout/used samples и s сохранена, no reset/copy future. Это диагностически согласованное начальное состояние.
hold_d — идентичен coherent, дополнительно удерживает последний доотказный v8 d перед/после каждого шага [start,end). STOPPED имеет приоритет и прекращает удержание до конца события. После end штатная адаптация, s не сбрасывается. Это вторая вложенная ablation, не третья: coherent->hold_d изолирует event d updates при одном начальном состоянии. h36->coherent меняет ВСЮ предысторию, не одно поле. hold_d-v8 не объявляется чистой физикой: v8 может ещё адаптироваться.
Границы известны только offline intervention wrapper; ablations не runtime кандидаты, не выбирать победителя и не использовать oracle для deployment. Clean main/h36; все исходные faults — все4 factories в штатном crop и в полном faulted bag. Коэффициенты, bins, masks и бюджет после результатов не менять.

## Измеритель
Импортировать неизменные guarded.compare/fault_windows,evaluate.replay/distance_surrogate,ex.match/metrics,v6.summary. Меняются только роль/factory и пассивный collector. Одинаковые order/timestamps/held samples/reference masks. Baseline fingerprint: clean .09266814298282507,fault .2375486120563008,pooled .1293056944774334,distance5.310295004801444,n394221, exact equality. H36 historical rounded aggregates сравнивать с точностью опубликованных знаков, не выдумывать exact delta0 для округлений. Отсутствующий reference — null. Все индивидуальные unrecovered/slower recovery сохранить. Full distance отдельно по виду/длительности и целиком, не вместо event score.

## Предзаданные разрезы
Одинаковые для моделей masks по baseline/внешнему reference. Command: traction u>.04,braking u<-.04,coast иначе,stale отдельно. Baseline |v|:[0,.07),[.07,.5),[.5,2),[2,5),[5,10),[10,infinity). Каждый исходный group/receiver отдельно. Mode trajectories отдельно, их разные subsets не маски общей accuracy.
Time bins: pre[-5,0); event[0,1),[1,2),[2,3),[3,5),[5,10) пересечь с event; post от конца[0,1),[1,3),[3,10),[10,end]. Не суммировать разные разбиения. Пустые bins N/A.
GNSS sensitivity: оба finite и abs(master-rover)<=.5; оба finite и>.5; peer missing; отдельный zero-versus-moving flag min<=1e-9,max>2. Антенны симметричны, виновный receiver неизвестен. Никаких удалений из primary masks. Числа по двум receivers одной поездки не независимые испытания.
Pre-fault v/drive/d/P/readout,model accel/speed clipping,disturbance-limit occupancy,modes; signed bias/MAE/p95/RMSE/counts. Все группы и все leave-one-group-out, не выбирать выгодное исключение. Group-macro и pooled SSE contribution раздельно.

## Полные интегралы
Signed velocity-error integral на event, start..end+10,start..последний output. Трапеции с дробными краями; не мостить reference gaps или dt>.051s. При неполном покрытии full_integral=null, только integral_on_covered_edges с covered/requested seconds. Не выдавать его за true terminal drift.
Published delta_s(model-main) в последнем tick<=end,end+10 и в конце с actual timestamp; отдельно прирост относительно последнего prefault tick. Это разность алгоритмов, не XYZ truth. Независимая проверка интеграла output delta_v против изменения delta_s, tolerance1e-8m, без стирания prefault offsets/recovery offsets. Все worsened event/full-distance cases и baseline failures в COUNTEREXAMPLES. Трасса сама по себе не доказывает причину.

## Исполнение и завершение
До DB IO — legacy/research/audit tests,profile identity,passive parity,oracle boundaries,STOPPED,affine/gappy integral,role rejection. Source receipt и source hashes до run. Все clean main/h36 сопоставить с uninstrumented factories по outputs/counters; у ablations exact prefault v8 parity. Исходный полный source не менять.
AUDIT_COMPLETE:17clean+56original crops+56full faulted cases,exact baseline fingerprint,primary parity/schedule/coverage,integral checks,separated H36 versions. Gain2/5% не нужен. Enabled ROS и ABBA нового кандидата N/A_NO_RUNTIME_CANDIDATE. Compute timing — только offline audit.
ERROR_ATLAS.json,per-group/per-case/time/phase/receiver CSV,COUNTEREXAMPLES.json,H36_VERSION_BINDINGS.json,сжатые traces,receipts/logs,REPORT/commands,R5_HANDOFF.json(kind=atlas). Handoff проверить штатным R5 verifier. Small files Git, large compressed evidence отдельно, никаких DB/секретов. Branch research/R5-H43,Draft PR на русском. [skip ci] не означает PASS CI; выполнение локальное, source/report SHA разделены.
