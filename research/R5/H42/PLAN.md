# R5-H42 — PLAN до teacher measurements и downstream fitting

Тип DATA. Baseline b2783206000091ab11a1c11ac3ff79082188a4fb, tree 973d50d288e050325ee1c71a90fa8d81f2a099af; source ZIP проверен полностью (320 файлов). Dataset SHA256 d0b2483e13990edb8219b0d7bbcafc7ed001cce549a4d3af467069b2472e7d52, 256294592 bytes. Только R5-H42; другие гипотезы не запускаются. Ветка research/R5-H42 создана после пустого exact-ID поиска. Локальное исполнение, не Actions.

## Основание
Карточка сообщает 390 exact-stamp zero/>2m/s пар train GNSS и UNKNOWN covariance. Проверить заново, не считать эти наблюдения готовой очисткой. Приложенная qa-необрезанная.md содержит полную текстовую стенограмму вместо прежнего summary: это свидетельство сказанного, а не верификация скрытого evaluator. Отделять DB/schema observations, Q&A statements, engineering assumptions и неизвестные поля coordinate/extrinsics contract.

## Одна policy v1, без fitting/sweep
Teacher — offline scalar horizontal speed proxy, не signed longitudinal truth и не official XYZ. Исходные 3D linear/angular velocities и все NavSatFix fields сохраняются. Никаких vehicle/observer values в функции качества. Не выбирать receiver по ошибке baseline или по колёсам. Нулевую скорость саму по себе не исключать.

1. Source timestamps — int64 ns, record timestamps сохранены отдельно. Сначала exact-stamp pairing, затем взаимно-однозначное mutual-nearest pairing оставшихся времён в пределах 50 ms. При равном nearest-distance не выбирать произвольно: abstain. Один sample не используется дважды. Exact duplicate stamp+payload coalesce с сохранением всех raw rows; conflicting duplicate stamps остаются ambiguous.
2. Согласие scalar speeds: |v_master-v_rover| <= max(0.30 m/s,0.02*max(v_master,v_rover)). Применять только finite data. Pair frame_ids должны совпадать и быть непустыми. Label=(v_master+v_rover)/2 только для принятой пары; иначе NaN и explainable reason codes. Временная метка пары — integer midpoint, оба исходных stamp сохранены. Это не transport/interpolation. Raw disagreeing receivers никогда не заменяются одним выбранным.
3. Для каждого receiver требуется соответствующий nearest fix в пределах 200 ms по source time, status>=0, finite/range-valid latitude/longitude. Неизвестная altitude отмечается отдельно и не превращается в нулевую высоту. UNKNOWN covariance/нулевая матрица НЕ precision evidence и сами по себе не veto scalar speed. Coordinates остаются raw antenna coordinates, не base_link.
4. Консервативная собственная временная проверка: adjacent unique finite speeds на интервале 0<dt<=0.5 s с |dv|>0.5 m/s+8 m/s^2*dt помечают ОБА конца как temporal-jump ambiguity. Это фиксированный инженерный тест, не аппаратная калибровка. Он использует neighbouring GNSS offline; future label support/availability явно помечаются. Gaps>0.5 s, record-source lag, source reversals, isolated zero между >2 m/s и стабильные both-zero эпизоды диагностируются отдельно, не выбирают виновный receiver. Без интерполяции через gaps. Дополнительных thresholds после check/development не вводить.

No scales are fitted: all thresholds fixed above. Поэтому fit/check не используются для оптимизации masks. Перечисленные проверяемые условия — один teacher, не набор вариантов.

## Данные и folds
Новый отдельный read-only loader проверяет исходный split/DB hash до SQLite IO, открывает URI mode=ro/query_only. SQL payload select только GNSS fix/vel; topics metadata разрешена для inventory отсутствующего official reference. Старый Store, runtime, masks, evaluator и guards неизменны.

64 train bags /27 source groups; folds20 fit/7 check согласно contracts/TRAIN_FOLDS.json. Если оригинальный файл не доступен, восстановить membership только опубликованным правилом seed R5-data-route-20260926, отдельно labels30618/30639, sort SHA256(seed+':'+group), первые5/2 check, остальные fit. Семантическое восстановление не выдавать за совпадение неизвестных JSON bytes. Wire duplicate groups не пересекают folds; независимая единица — source group.

После train создать отдельный POLICY_FREEZE с хешами полного кода, policy, folds, source/dataset/split и train results; опубликовать до первого descriptive development IO. Development17 bags: только описательное применение той же policy, без fitting/выбора. Canonical masks не менять. Validation19/test22 payload не извлекать и не открывать.

## Проверки и результат
Expanded CDR decoder сверить с неизменным tools/export_bags.py на ВСЕХ декодированных GNSS сообщениях по общим полям. Synthetic CDR oracle: endian/alignment/strings/truncation/NaN; независимая policy oracle и metamorphic vehicle-independence, duplicate/no-reuse, boundary/tie/gap/zero tests. Counterexample raw CDR + exact message IDs/DB hash для каждого наблюдавшегося reason code; отсутствующие в данных reasons отдельно пометить synthetic-only, не выдумывать реальные случаи.

Учесть все64train; coverage по bags/groups/labels/folds, raw agreement/disagreement/ambiguity/missing, lag/gaps/duplicates/zeros. Остановка без независимой истины — stationary proxy, не подтверждённая real-stop label. Соглашение двух GNSS не исключает общий bias. Coverage acceptance: минимум3fit и2check source groups с accepted labels, оба metadata labels представлены в каждом fold. Конечный DATA verdict AUDIT_COMPLETE/COMPONENT_READY, не runtime gain. No supervised model fitting, no runtime promotion.

Артефакты: REFERENCE_CONTRACT.json (observed/reported/unknown XYZ/MGRS/base_link matrix), TEACHER_POLICY.json, TRAIN_FOLDS.json, raw decoded arrays/teacher arrays по bag, coverage/reason tables, examples/*.cdr, schema, tests/logs, access journal, POLICY_FREEZE, R5_HANDOFF.json(kind=teacher) со всеми hash bindings. NPZ/DB не коммитить; компактные код/контракты/отчёт в своей ветке и draft PR на русском. Полный compressed evidence передать пользователю. Никаких main/чужих веток/старых отчётов, merge/force/auto-merge. При конкретном blocker сохранить доступное и truthful status.
