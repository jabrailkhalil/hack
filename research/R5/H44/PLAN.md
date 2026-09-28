# R5-H44 — предварительная фиксация этапа 0

Baseline b2783206000091ab11a1c11ac3ff79082188a4fb; полный tree 973d50d288e050325ee1c71a90fa8d81f2a099af. Только H44: прежняя физика, обученная по frozen H42 GNSS teacher, против matched wheel-target control. Эта фиксация разрешает source/tests и baseline-only development preflight, но НЕ fitting без зависимостей. Числовая спецификация train-window/loss должна быть опубликована после проверки реальных handoffs и до первого fit; сейчас их schema/payload не проверены.

## Проверенное к фиксации

Пользовательский ZIP hack-main-2 2(2).zip даёт точный R5 tree, 320 source files. Позднее названный hack-main-2(20260926-135511).zip даёт старый R4 tree eae49a504bc59b5c9b408445150bef32e111956f, 301 files, и исключён. Canonical profile/class — GuardedReadoutObserver/champion_v8.yaml; из YAML читаются все model/readout поля, 20 Hz, delay=0. Сравниваются возвращаемые Estimate.v/s. Baseline/source unit tests уже выполнены, без новой measurement SQL. Dataset ZIP d0b2483e13990edb8219b0d7bbcafc7ed001cce549a4d3af467069b2472e7d52 распакован только для 64 train и 17 development DB с SHA256 каждого файла. Validation/test DB не извлекались.

## Жёсткий барьер зависимости

Нужны R5_H42_teacher_component.zip (28190115 bytes, SHA256 2ee08edb32343350bf6ae6202836644de4fb309640f2d140a1eb9d5791af28b8, manifest 5c8129133758bbb715f2e170122b976f95d0240c18daa731472d910f0bf274d0) и R5_H43_atlas_handoff.zip (1076521 bytes, SHA256 6a759f4bafe4ece014e9dd4f25b201549e317f2ca9db7b47b6c15d4443d9b011, manifest 73d3269f012f25f4c46787369bdb85fc218fbf149d29cd60c63eb8f20687bd5c).

Они найдены по метаданным Library и подтверждены PR56/55, но Files materialize для обоих вернул: This Project file does not have an authorized raw-byte materialization path. Отказ не обходится; producer-regeneration, поиск заменяющих arrays или копирование PR receipt вместо полного manifest запрещены. Гипотеза не становится REJECTED из-за недоступности байтов.

До training обязательны: outer ZIP/CRC/manifest verification, разные extraction roots, собственный verifier каждого producer, bridge фактических folds и canonical folds, затем новый DEPENDENCIES.lock.json с payload/native lock/bridge/policy/reference/split/source hashes. DEPENDENCIES.expected.json не является lock. Coordinator folds bridge не доказывает проверку teacher arrays. Fitting, новый GNSS cleaning/teacher, initialization по teacher и training по atlas сейчас запрещены.

## Допустимый baseline-only preflight

После этой фиксации один новый локальный replay всех 17 development bags/7 исходных групп и их 56 ожидаемых original cropped fault scenarios. Только canonical v8, без кандидата/перебора/teacher. Исходные tools/research_guarded/compare.py compare/predict/fault_windows, finalization/evaluate.py replay/distance, research_v3 match/metrics и research_v6 summary используются без изменения. Нужен отдельный read-only role adapter: только development, исходный query ORDER BY record timestamp,id, decode/scales/origin; role и DB SHA проверяются до SQL. GNSS — только внешний scorer. Сохраняются все missing, спорные reference и четыре исторических unrecovered.

Baseline fingerprint — не замена измерения: ожидаемые clean .09266814298282507, original fault .2375486120563008, pooled .1293056944774334, distance 5.310295004801444, matched 394221. При несовпадении остановить quantitative claims, не подгонять код. Сохраняются per-bag/per-receiver/per-fault, MAE/bias/p95/coverage/recovery и access. Никаких accuracy assertions о H44; candidate_metrics=null. Full-faulted candidate replay и safety suites ждут fitted candidate.

Допустим интерфейс преобразования F/m,P/m,B/m в прежние torque/power/brake поля с exact identity при исходных коэффициентах, тесты неизменности остальных параметров и source/state. Это interface-only, не обученный runtime-кандидат. Нельзя выдавать arbitrary test coefficients за H44. Тесты missing-dependency не должны выдавать training authorization. При барьере сохраняются NOT_EVALUATED/DEPENDENCY_PENDING и точная команда возобновления.

## Сохраняемый научный бюджет H44

После реального upstream preflight: один GNSS fit и один matched wheel-only fit, идентичные valid windows/group weights/causal own-config warmup/horizons .5/2/5s и prefix-integral objective/fixed prior/bounds/start/budget. Менять только F/m,P/m,B/m; остальные physics/d adaptation/readout/gates/Timeline неизменны. max_nfev80 каждый, combined actual residual calls including Jacobian <=1000, no restarts. Control не запасной selectable candidate. Неизвестный знак GNSS magnitude не подменять signed v; до fit зафиксировать magnitude-compatible loss и window-selection policy. Не заполнять пропуски teacher колёсами. Targets/quality остаются только offline; runtime controller/front/rear.

Требуются check velocity/integral aggregate regression <=.5%, per-check-group <=5%, scalar predictor parity. Общий LONGITUDINAL contract: >=2% clean OR >=5% original fault gain; main aggregate regression <=.5%, clean/full-faulted distance <=1%; per-clean-bag <=base+max(.005m/s,5%); одинаковые timestamps/masks/coverage и отсутствие новых false stops, individual unrecovered, causal/reset failures. Low-speed и H11 common suites <=.5% event regression без новых failures. Gains отдельных suites не заменяют original gain. Attribution относительно matched control обязательна. Leave-one-group-out sensitivity — диагностика без удаления групп. Own-config warmup нельзя заменить состоянием v8/H36. Full delta_s после recovery и до конца bag не обнулять.

Только после положительного полного development — отдельный опубликованный source/config/dependency freeze до одного validation. Final test никогда не открывается. Для продвижения нужен свежий enabled installed ROS both clocks/offline2CPU/500000000bytes/actual params/import/latency/RSS. Сейчас этот этап NOT_RUN_DEPENDENCY_PENDING, а не прошедший runtime.

## Публикация

Новая собственная research/R5-H44, без main/upstream/старых отчётов, merge/auto-merge/force-push. У источника интерфейса отдельный diagnostic_source_sha; measured_candidate_sha=null до настоящего fitting/evaluation. Отчёт и SUMMARY отделяют source/data/dependencies/execution/publication от scientific verdict. Не заявлять новый CI/Actions: [skip ci] — только отсутствие заказанного CI, не success. Evidence локальный, без DB/teacher arrays в Git/runtime. Подготовить draft PR NOT_EVALUATED и переносимую точку возобновления.
