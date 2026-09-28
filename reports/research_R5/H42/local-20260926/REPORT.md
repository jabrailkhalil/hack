# R5-H42 — COMPONENT_READY / PROXY_ONLY

**Готов проверенный DATA-компонент: единый GNSS-only teacher v1 и read-only аудит. Не доказанный выигрыш runtime-одометрии, не официальный XYZ reference и не предложение merge.** Выполнена только H42. Downstream fitting, карта, другие гипотезы, validation и final/test не запускались. Canonical runtime/scorer/masks/guards сохранены.

## Версии и порядок

- Baseline: `b2783206000091ab11a1c11ac3ff79082188a4fb`; полный tree `973d50d288e050325ee1c71a90fa8d81f2a099af`.
- PLAN до train: `d981d3ebcf28abd2dda9b06d5b659d7b3e5bd762`.
- Измеренный teacher source и опубликованный policy-freeze: **`656cedb7be5ba0730377856c855ab4505b9c3f3f`**.
- Ветка: `research/R5-H42`; исполнение локальное, не Actions. Report SHA — enclosing commit.

Все320 исходных файлов проверены по paths/bytes/executable bits; полный Git tree совпал. Source ZIP3871238 bytes, SHA256 `4823fbdbbb979d7b561841e2831e68f2f7d9d8ec0d14e970f09a38cd51dff4c4`. Dataset256294592 bytes, SHA256 `d0b2483e13990edb8219b0d7bbcafc7ed001cce549a4d3af467069b2472e7d52`; каждая разрешённая DB проверена до SQL. Локальная Git history не выдумывалась.

PLAN опубликован до train. Train выполнен на локальном source-set `d4dcc488907664fcbf08e5e0ad0a7981d97c3a41b5d1dd998ea637649449fe3c`; все8 измеренных Python/contract blobs затем опубликованы и побайтно сверены с656cedb7. Кодовый commit не выдаётся за существовавший до train. **Freeze опубликован до первого descriptive development IO**, execution receipt добавляет только настоящий enclosing commit. Policy после train/development не перенастраивалась.

Исходные bytes общего TRAIN_FOLDS.json не были доступны. Membership восстановлен по явно разрешённому правилу seed `R5-data-route-20260926`, отдельно labels30618/30639, sort SHA256(seed+':'+group), первые5/2check. Получены20fit (17/3 labels) и7check (5/2), wire duplicates folds не пересекают. Наш JSON SHA256 `e4867077a80e340c67cff73c1c04a1250680f848060ed3ce974370e110ca3546` **не подменяет** ожидаемый оригинальный SHA `7efb88def952af5089e89c0415256b529bf6e944cda8596387569cc055192356`; семантический membership hash в handoff. Другие гипотезы из общего задания не запускались.

## Реализация

Отдельный read-only Store проверяет role до ZIP/SQL, DBhash до SQL, использует URI mode=ro&immutable=1 и query_only. Payload SELECT — только master/rover fix/vel; vehicle payload не читался. Metadata topics учитываются отдельно. Старый Store не ослаблен.

Независимый CDR1 decoder сохраняет integer source/record timestamps, frame_id, все3 linear/angular components, lat/lon/alt, status/service, covariance_type и9covariance values. **Все2 168 009 реальных GNSS-сообщений совпали по общим полям с неизменным tools/export_bags.py**. Raw arrays, включая отклонённые сообщения, сохранены.

Одна fixed policy, fitting/objective calls=0:

1. Exact-stamp pairing имеет приоритет; затем один проход взаимного однозначного nearest среди оставшихся samples, допуск50ms. Tie/conflicting duplicate остаются ambiguous, sample не используется дважды.
2. `|vm-vr| <= max(0.30 m/s,0.02*max(vm,vr))`; одинаковые непустые velocity frames, finite скорости. Приёмникам нужны соответствующие fixes в пределах200ms, status>=0 и finite/range-valid lat/lon.
3. Соседние GNSS speeds при0<dt<=0.5s и `|dv|>0.5+8*dt` помечают оба конца TEMPORAL_JUMP. Это заранее установленный инженерный тест, не аппаратная калибровка. Gaps/lag/source reversals отдельно диагностируются.
4. При всех пройденных условиях target=(vm+vr)/2; иначе NaN/reason bits. **Нет выбора receiver по колёсам/observer/error, нет single-receiver fallback. Ноль сам по себе не veto; UNKNOWN covariance не точность и не вес независимого датчика.**

Target — горизонтальный модуль скорости, не signed route speed, не XYZ. Timestamp — midpoint native source stamps, не20Hz output grid и не transport. Teacher использует будущую GNSS историю offline; `available_after_bag_record_ns` консервативно требует финализации целого GNSS bag. Target/quality/fix запрещено подставлять в causal features или state.

## Покрытие и результаты DATA

| Роль | Bags / группы | Группы с целями | Строки | Принято | Ambiguous | Missing | Доля принятых |
|---|---:|---:|---:|---:|---:|---:|---:|
| Train-fit |50/20|16 (13/3 labels)|340432|321756|568|18108|94.5140%|
| Train-check |14/7|6 (4/2 labels)|110126|100513|9|9604|91.2709%|
| Development descriptive |17/7|5 (2/3 labels)|104058|92833|101|11124|89.2127%|

Проценты относятся к union native velocity rows после pairing, **не к времени всего проезда или accuracy**. Учтены все64train/17development bags. 20train bags/5groups вообще без GNSS — пустые arrays и N/Acoverage, не error0. Вdevelopment7bags без GNSS; ещё30639_e4379d7f имеет только rover:5705строк и0accepted, без выдуманного fallback. Цели есть в44train и9development bags. Source groups, а не ticks/receiver/wire-дубликаты, являются единицами групповой агрегации.

DATA coverage requirement >=3fit и>=2check groups с обоими labels выполнено:16/6. Это не проверка 2%/5% runtime gain.

| Native diagnostic | Train64 | Development17 |
|---|---:|---:|
| Master velocity |435373|95213|
| Rover velocity |441235|102124|
| Master fix |449650|98224|
| Rover fix |442983|103207|
| Exact paired stamps |426050|93279|
| Raw agreeing pairs |425521|93198|
| Final accepted targets |422269|92833|
| SPEED_DISAGREEMENT rows |529|81|
| Exact0 vs>2m/s |390 на8bags|40 на3bags|
| BOTH_ZERO accepted |11 из11|0 из0|
| TEMPORAL_JUMP rows |93|37|
| PAIRING_AMBIGUITY rows |1712|246|
| MISSING_FIX rows |3350|351|

Reason bits могут пересекаться, поэтому их суммы не равны disjoint state counts. Все430zero/>2 пары воздержались от label без выбора виновного receiver. Train30618_3e9f4952: stamp1787743738700000000ns, master3.911m/s против rover0, raw messages69031/69027 сохранены. Это не подтверждение master как истины.

Одиннадцать both-zero train pairs сохранены. Но точных both-zero серий>=1s не найдено; независимой разметки истинных остановок нет. **Real-stop recall/false rejection не установлены.** Final accepted near-pairs0; nearest/tie/широкий skew в этих данных не получил покрытия принятого near-label, несмотря на synthetic tests.

## GNSS и координатный контракт

Во всех81разрешённых DB отсутствует `/localization/kinematic_state`. Все1 094 064fix messages имеют covariance_type0 и9нулевых covariance. Это UNKNOWN, не точная позиция. Fix.status встречается0/1/2: status не подменяет численную uncertainty. Все4GNSS frame_id равны gps, что не устанавливает одинаковые origin/extrinsics антенн.

Наблюдаются source reversals и record-source differences. Train master-vel offset: −0.923209459..+3.423552961s; development rover-fix максимум+5.505832978s. Это не оценка физической latency: согласованность clock domains не подтверждена. Политика не подбирает lag correction.

Полная текстовая qa-необрезанная.md прочитана; аудио не проверено. REFERENCE_CONTRACT разделяет DB/schema observations, Q&A testimony и unknowns:

- В Q&A разрешены offlineGNSS для идентификации/карты(06:18); combined localization сlidar, не rawGNSS, названа reference(23:43); topic/MGRS(10:24); XYZ/Cartesian distance(16:50).
- В Q&A base_link — центр передней тележки на верхнем уровне рельса(03:56), Xвперёд/Yвлево/Zвверх(20:15). 7550mm — расстояние тележек, **не антенн**.
- Точные MGRS zone/square/projector/numeric origin/axis mapping, GNSS→base_link extrinsics, antenna lever arms, геоид/rail height/Z-offset и route_s0 неизвестны. ENU не выдаётся за officialMGRS.
- Длительность начального GNSS-окна не установлена(03:29/19:49).3s — R5 experiment assumption, не правило организаторов. H42 это окно или карту не реализует.

Исходный frozen contract не переписан. Отдельный train-observed REFERENCE_CONTRACT сSHA `c7b335ed6ed9fb9f68992acd687960ec5df16e4b8c0662cdada51fb20035d037` уже связан сfreeze; development observations находятся отдельно. Raw GNSS agreement не исключает общий bias, scalar agreement не проверяет heading/vector consistency.

## Выполненные проверки

Локально PASS:161canonical tests +43research-integrity +29H42tests, compileall. Patch git apply --check, roundtrip байтов и повтор29H42tests прошли. Неизменность всех320baseline files подтверждена.

Readonly recomputation:81NPZ/554616teacher rows — exact masks,targets,indices,flags. Все GNSS common fields совпали с canonical decoder.3254проверки ссылок на реальные CDR witnesses независимым fixed-layout oracle; это не число независимых поездок. Каждый наблюдавшийся reason code имеет CDR/ID/DBhash witness; отсутствующие реальные случаи не выдаются за измеренные, synthetic-only coverage отмечено отдельно.100random pairing streams сверены с независимым naïve oracle. Никаких vehicle аргументов в quality API; запрещённые roles отклоняются до IO.

Handoff verifier дополнительно прошёл7тестов integrity/path/role/fold/неперезаписи lock и проверку85файлов компонента. Компактная проекция64train NPZ сохраняет все450558teacher rows/422269targets без изменения маски. Полные raw GNSS vectors/fixes/covariances сохранены в отдельном audit archive.

Wolfram реально подтвердил common-bias persistence и Var(mean)=(s1²+2rho s1s2+s2²)/4: приrho=1 нет автоматического деления на2. Проверен Lipschitz midpoint bound при заданных предположениях. Worksheet/output сохранены; это не GNSS precision или nonlinear observer stability proof. Прочитаны полные официальные ROS2 humble NavSatFix/NavSatStatus/TwistStamped.msg. Consensus/Scite не вызывались из-за quota-stop.

Нет fitting, runtime изменения, canonical mask замены, validation/test IO, Actions run или enabledROS. **Runtime gain/официальный score N/A**, DATA verdict COMPONENT_READY, ready_to_merge=false.

## Evidence, handoff и воспроизведение

Полный `R5_HANDOFF.json(kind=teacher)` передан в самостоятельном teacher ZIP; в Git сохранена квитанция с его точным SHA, а не фиктивный Actions artifact. Компонент содержит64train arrays, policy/reference/folds/schema, source bindings и verifier. `verify_handoff.py` проверяет каждый payload hash и создаёт новый DEPENDENCIES.lock.json **до downstream fitting**. В teacher ZIP нет development labels; fit50bags/check14bags разделены. Не использовать teacher в onlinefeatures и не заменять canonical masks. Exact originalfoldbytes недоступны; membership восстановлен по разрешённому правилу и помечен отдельно.

Артефакты беседы:

- R5_H42_teacher_component.zip:28190115bytes, SHA256 `2ee08edb32343350bf6ae6202836644de4fb309640f2d140a1eb9d5791af28b8`.
- R5_H42_audit_evidence.zip:152282052bytes, SHA256 `db57a5d54da90f9a729c6456bc7d77d0dc505918e26dd6ed85dc5f1ed10f4af5`.
- R5_HANDOFF.json SHA256 `5c8129133758bbb715f2e170122b976f95d0240c18daa731472d910f0bf274d0`.
- Полный R5_H42.patch SHA256 `5d4ee676af430e3d7a03b0e15d770ef59db4725ccfe86be5b430d44260709e12`.

Fullaudit содержитall81raw/teacherNPZ, perbag/pergroup/reasons/coverage, CDRexamples, полный русский report, source/PLAN/patch, QAтекст, baselineZIP, stdout/exit/access/verification receipts. **Нет DB или полного dataset ZIP.** БольшиеNPZ не коммитились, внешняя retention не обещается. Неизменные исходные JSON/CSV и полный расширенный отчёт находятся в архиве; этот REPORT — компактная публикация.

```bash
git checkout 656cedb7be5ba0730377856c855ab4505b9c3f3f
python -m pip install -r requirements-research.txt
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
python research/R5/H42/test_h42.py
python research/R5/H42/audit.py --role train --dataset /path/dataset.zip \
 --data-root /tmp/H42-new-data --output /tmp/H42-new/train \
 --source-commit 656cedb7be5ba0730377856c855ab4505b9c3f3f
# Published freeze receipt from the evidence, with unchanged source/policy hashes.
python research/R5/H42/audit.py --role development --dataset /path/dataset.zip \
 --data-root /tmp/H42-new-data --output /tmp/H42-new/development \
 --source-commit 656cedb7be5ba0730377856c855ab4505b9c3f3f \
 --freeze /path/audit/POLICY_FREEZE_EXECUTION.json
```

Смена teacher после этого результата — новая версия, не тихое исправление маски. H42 завершена как проверяемый DATA teacher; независимая accuracy и последующая польза для физики/reliability ещё не измерялись. Не выполнять merge/auto-merge.
