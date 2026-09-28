# R5-H48 — карта маршрута: preflight checkpoint

Статус плана: PRECHECK_ONLY_NOT_FITTING_AUTHORIZATION. Это не завершённый numerical design freeze.

## Идентичность и предмет

Только R5-H48, GEOMETRY_COMPONENT, wave 2. Baseline b2783206000091ab11a1c11ac3ff79082188a4fb / tree 973d50d288e050325ee1c71a90fa8d81f2a099af. Ветка research/R5-H48. Полный новый пользовательский source ZIP проверен: 320 файлов, SHA256 4823fbdbbb979d7b561841e2831e68f2f7d9d8ec0d14e970f09a38cd51dff4c4. Старые H07/H18/H38 сюда не переносятся.

Гипотеза: ordered robust multi-pass antenna-trajectory proxy из train-fit может уменьшить геометрический шум по сравнению с deterministic ordered polyline. Route.at(s) уже существует и не считается новой гипотезой. В этом checkpoint нет карты, обученного кандидата, MAP_FIT, MAP_V0 или готового map handoff.

## Обязательные зависимости до fitting

1. R5_H42_teacher_component.zip: 28190115 bytes; SHA256 2ee08edb32343350bf6ae6202836644de4fb309640f2d140a1eb9d5791af28b8; полный manifest 5c8129133758bbb715f2e170122b976f95d0240c18daa731472d910f0bf274d0.
2. R5_H43_atlas_handoff.zip: 1076521 bytes; SHA256 6a759f4bafe4ece014e9dd4f25b201549e317f2ca9db7b47b6c15d4443d9b011; полный manifest 73d3269f012f25f4c46787369bdb85fc218fbf149d29cd60c63eb8f20687bd5c.

Получены только публикационные receipts PR55/56. Оба ZIP найдены в Library, но files.materialize вернул для обоих: This Project file does not have an authorized raw-byte materialization path. Это access/transport blocker, не отсутствие датасета или отрицательная геометрическая проверка. Не обходить этот отказ, не восстанавливать teacher запуском H42 заново. Получить обычные вложения пользователя либо разрешённую опубликованную копию.

Входной пакет wave2 задаёт: outer SHA/CRC и manifest -> отдельные native teacher/atlas verifiers -> folds bridge -> новый DEPENDENCIES.lock.json. Ожидаемые hashes/receipts и синтетические fixtures не являются выполненным native preflight. Не создавать положительный lock до этих проверок.

## Разрешённый текущий объём

Проверить полный source tree, неизменные unit/integrity tests, hash датасета и все 64 train/17 development DB без SQL/декодирования. Проверить metadata folds. Реализовать только интерфейс ordered metric graph и тесты топологических инвариантов, используя синтетические точки. Никакого чтения GNSS measurements, fitting, objective calls, check geometry или validation/test. Интерфейс не экспортируется как обученная карта и не подключается к canonical ROS.

Geometry interface сохраняет явные edge/node IDs и provenance; пересечение координат не создаёт соединения, повторное посещение точки не удаляет другую arc-length гипотезу. Existing Route.at используется для заданной ветки, не переписывается. Проекция на полную траекторию допустима только offline и не считается локализацией/start. Кватернион касательной не объявляется body heading. Система координат задаётся явно; UNRESOLVED geoid/extrinsics/MGRS не подменяются числами.

## Сохранённый prospective научный бюджет

Ровно две representations: deterministic ordered polyline control и один robust multi-pass centerline. Train-fit: 50 bags/20 source groups. Train-check: 14 bags/7 source groups. Исходный folds SHA 7efb88def952af5089e89c0415256b529bf6e944cda8596387569cc055192356; producer H42 имеет иной JSON SHA, но ожидаемая семантика та же. Missing groups не перемещаются; wire duplicates не независимы.

После native dependency preflight, ДО чтения координат для fitting, дополнить этот план отдельным immutable DESIGN_FREEZE: конкретные spacing/smoothing, bounded matching/topology, разрывы, frame/origin/height/receiver provenance, solver budget, единые masks и aggregation/coverage definitions. В этом checkpoint численные настройки этих правил не выбраны. Никакой настройки по check/development atlas errors. Atlas — диагностика, не training targets. Teacher не причинный и не runtime feature.

## Критерии без изменения

Check cross-track RMSE не хуже control; целевой gain >=5%, либо compression >=2x при p95 regression <=1% и без потери покрытия. Непокрытые и неоднозначные области, per-group результаты и leave-one-group-out sensitivity сохраняются. Nearest-point error не равна localization error. Official XYZ/base_link gain не заявляется без внешнего контракта. Unsigned teacher speed не даёт направление или body heading.

Один deterministic full-train build после фиксации правила предварительно разрешён этим планом, без нового tuning; старые check-метрики относятся исключительно к MAP_FIT. Карта <=1000000 несжатых байт — внутренний бюджет, не официальный предел. Если кандидат не улучшает control, control может стать MAP_V0 лишь после реальной компонентной проверки и handoff, не автоматически.

START_V0 пока только контракт: согласованный причинно доступный GNSS prefix <=3s; ближайшая уникальная проекция, иначе UNLOCALIZED; после окна доступ закрыт. Не использовать teacher quality, available_after_bag, весь check-проход, истинный start/branch или будущее. До привязки relative output; прошлые оценки не переписываются. Порог уникальности должен быть frozen до start/geometry check, здесь не выбран.

## Завершение checkpoint

NOT_EVALUATED / DEPENDENCY_PENDING; candidate_implemented=false, component_ready=false, ready_to_merge=false. Невыполненные метрики null/N/A, не нули. Отдельные interface_source_sha, report_sha; measured_candidate_sha и freeze_sha отсутствуют. Публиковать только свою ветку/draft; не merge, auto-merge, force-push, не менять baseline/старые отчёты. После получения двух payload ZIP продолжить с native preflight, не повторяя H42/H43 или прежние отборы.