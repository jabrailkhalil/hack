# R7-A0 — Oracle Headroom Audit

**INSUFFICIENT_FROZEN_EVIDENCE. Аудит доступных evidence завершён, численный headroom и классификация пула не установлены.**

Это A0 новой архитектурной волны, не реализация MHE/A1. В данном исполнении 0 model replay, 0 fitting, 0 oracle selector calls. Validation/final/test не открывались. Runtime не менялся; candidate.patch и PR не создавались. Main, общая infrastructure branch и A1 не изменены. Permanent claim claims/R7-A0 сохранён.

## Версии

- Baseline: b2783206000091ab11a1c11ac3ff79082188a4fb, tree 973d50d288e050325ee1c71a90fa8d81f2a099af.
- Infrastructure base: 4979cff1aaaffd316d931504e818851d5e6b36b1.
- PLAN binding: 90bfddda184069802f654ab8d9d12da597ef2e5b.
- Audit source binding: 861864a30e57b77ad09741fda11b5a1644d91b2f.
- Exact audit.py SHA256: 8061b531370d64d783229823bf96cbc45d020ea1ebe6ae21eb504906b42b60a6.
- Source ZIP: https://drive.google.com/file/d/1OkhnU5LQ73mEXXWyOaNCdjrDZB65TfP5/view ; SHA256 e13c38f6542db5e9f99094116522523128f9a7ced5ed10c36cdfad8b5eefd39d.

Source binding — Git commit, привязывающий точные байты к immutable Drive ZIP, не runtime candidate SHA. PLAN/lock опубликованы до parsing development predictions/truth. Код аудита не менялся после binding; последующий post_audit.py проверяет CSV без оригинального scorer.

## Проверенный паритет

H44-v8 и H54-v8: 73 общих сохранённых cases, 17 bags, 7 source groups, 1584837 ticks. Timestamp grids, original reference и masks совпали; max abs v=0, s=0. H54-C1 также совпал с v8 и исключён как дубликат. Пороги parity 1e-12 m/s и 1e-10 m не изменялись.

## Покрытие

| Suite | Metadata cases | Exact common arrays |
|---|---:|---:|
| clean | 17 | 17 |
| cropped original fault | 56 | 0 |
| full-history original fault | 56 | 56 |
| low-speed | 26 | 0 |
| common-mode | 28 | 0 |

Итого 183 replay identities, 73 массивных, 110 без массивов. Frozen develop.py исполнял cropped и full-history независимо; их одинаковые fault start/end не означают один replay. Для первого case 30618_0652866c/bias cropped recovery timestamp=161.906544646 s, ближайший stored full timestamp=161.9 s. Разница 0.006544646 s: slicing не воспроизводит даже output grid. Не было интерполяции или нового replay.

В 112 full-faulted receiver-pairs есть 60 с некоторым reference, но 0 с whole-replay endpoint error: full_span_terminal_error_m=null. Reanchored span RMS конечен, но это другая метрика. Подставлять его в J вместо abs(endpoint_error), заполнять reference gaps или использовать longest span без нового контракта нельзя.

## Численные результаты из сохранённых массивов

| Модель | Clean RMSE m/s | Pooled clean m/s | Clean span distance m | Full-recording faulted speed RMSE m/s | Full-faulted span distance m |
|---|---:|---:|---:|---:|---:|
| V8 | 0.092668142983 | 0.129305694477 | 5.310295004801 | 0.115533759932 | 6.269376947281 |
| H44-G | 0.092444346136 | 0.128915547471 | 5.368194375188 | 0.111490526542 | 6.509833186784 |
| H44-W | 0.092451004917 | 0.128939625900 | 5.356119424069 | 0.111534850675 | 6.477325266910 |
| H54-C0 | 0.092792626595 | 0.129472953985 | 5.307240104886 | 0.116899341680 | 6.239600847371 |

Это full-recording speed RMSE, НЕ опубликованный cropped original fault-event RMSE. 394221 matched clean samples; false stops на доступных clean/full массивах 0 у всех. 8340 scalar field comparisons: max delta=0, mismatches=0. Historical scalar results отдельно reaggregated, но это не array-level reproduction отсутствующих cropped traces. Историческое 0.2375486120563008 m/s не присвоено новому oracle.

## Почему oracles N/A

Заданный joint PRIMARY требует exact original fault evidence и endpoint error. Общий допустимый joint pool пуст; S_v/S_s, O_GROUP/O_BAG/O_CASE/O_BLOCK_2S, отдельные speed/distance gains — null. Winner/correlation tables header-only с NOT_COMPUTED.json. Нулевая доступность evidence не означает нулевого headroom. Нельзя присвоить POOL_CEILING_LOW, MIXED или отклонить A1/MHE по этому результату.

## Реально выполненные проверки

Exact four transport hashes, ZIP CRC, все 216/194 producer payload hashes; все 320 source paths/bytes/modes и tree. Original preflight дважды выявил packaging defects: вложенный data.zip/.db3 и manifest-excluded count. Исправлены только эти пункты, исходные FAIL/PASS сохранены, expected hashes/counts не менялись.

Извлечены только 17 development DB, SHA проверены до SQL. Декодировано 197337 сообщений двух GNSS velocity topics. Vehicle/fix/teacher/другие роли не декодировались. Оригинальные pure functions AST-extracted без module-level runtime imports. 23 новых unit tests PASS, py_compile PASS. Independent CSV audit: 876 indexed rows, 30 aggregates, max delta 1.7763568394002505e-15. All320 baseline files unchanged.

Python3.13.5 / NumPy2.3.5 / BLAS,OMP,MKL threads=1. Audit8.308509s — offline post-processing, не latency модели. CI/ROS не запускались; [skip ci] не зелёный CI.

## Артефакты и продолжение

Полный русский отчёт: https://drive.google.com/file/d/1MSX9b5rH0OhoMtFLdr8yujjoMYCI63Pa/view

HEADROOM_SUMMARY: https://drive.google.com/file/d/1Bo2coHrD2plTwpqpzg6U4bdkl9RcjKOb/view

Evidence/code/tests/reproduction: https://drive.google.com/file/d/1QSjpPbyrOsvruKjMN2KUkgrNMhCu1P6J/view

Evidence ZIP SHA256 f6f4c877c6acdf2e66998946471f3e1ebbc508019f10ca17e2be8695eb0c5782, 212465 bytes, 45 payload files + manifest. Shared dataset/source/H44/H54 not duplicated.

Для численного oracle нужны точные cropped traces уже frozen моделей и заранее определённый endpoint contract при неполном reference. Если outputs не были сохранены, их получение требует отдельно разрешённого frozen-model replay, который A0 запрещает. Это новая версия аудита, не тихая замена текущих метрик.

Workspace: https://drive.google.com/drive/folders/1Aq868Y0sgSBgo9zhl91xgm4OGrgry8R_
