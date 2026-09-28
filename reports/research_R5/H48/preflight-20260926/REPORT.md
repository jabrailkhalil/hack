# R5-H48 — DEPENDENCY_PENDING / NOT_EVALUATED

**Контрольная точка, не завершённая проверка гипотезы. Исследовательский артефакт, не готов к merge.** Выполнена только подготовка H48: идентичность исходников и данных, metadata folds, интерфейс геометрии, тесты. Обученной карты и измерений её качества нет. Ни положительный, ни отрицательный научный результат H48 не установлен.

## 1. Предмет и версии

H48 — GEOMETRY_COMPONENT: deterministic ordered polyline control против одного robust multi-pass centerline, fit на 20 исходных группах, check на 7. Это не продолжение H38 и не продольный accuracy patch. Порог компонентной проверки: check RMSE не хуже control и целевой gain >=5%, либо compression >=2x при p95 regression <=1% и без потери покрытия. Не использовать 2%/5% velocity gates другой категории.

- Baseline: `b2783206000091ab11a1c11ac3ff79082188a4fb`.
- Полный baseline tree: `973d50d288e050325ee1c71a90fa8d81f2a099af`.
- Ветка: `research/R5-H48`, создана от указанного baseline.
- План разрешённой подготовки: `2dbd1892969fed639fc0877e6255b7ad122bfa77`.
- Точно проверенные интерфейс/тесты/математика: `0e3c0baaa4adefb145d0d7f823f1f2734a7adf68`, tree `a8019b27947725ae4e142d38f8ff13fda5cf583b`.
- Measured map/candidate SHA, MAP_FIT, MAP_V0, candidate freeze: **N/A**.

Весь local source tree с интерфейсом совпал с опубликованным Git tree. Этот source commit опубликован после локальных unit-проверок, а не до несуществующего fitting. Локальный synthetic Git snapshot имеет другое ancestry и не выдаётся за удалённый commit. Canonical runtime/profile/Route/evaluator и все 320 исходных файлов сохранены.

## 2. Конкретный блокер зависимостей

Wave-2 addendum требует получить два полных ZIP, проверить их outer SHA/CRC/full manifest, выполнить каждый native verifier, затем bridge фактических folds и создать новый DEPENDENCIES.lock.json ДО fitting. Ожидаемые pins и receipts не заменяют эти проверки.

| Компонент | Размер, bytes | ZIP SHA256 |
|---|---:|---|
| R5_H42_teacher_component.zip | 28190115 | `2ee08edb32343350bf6ae6202836644de4fb309640f2d140a1eb9d5791af28b8` |
| R5_H43_atlas_handoff.zip | 1076521 | `6a759f4bafe4ece014e9dd4f25b201549e317f2ca9db7b47b6c15d4443d9b011` |

Оба архива найдены в Library. Однократный files.materialize для обоих вернул: **This Project file does not have an authorized raw-byte materialization path.** Это точный отказ выгрузки байтов, не отсутствие записей в Library. Получены и прочитаны [H42 receipt](https://github.com/jabrailkhalil/hack/blob/92bc5e0a0ad4939aa81b4c3e5a6fdf3976624e49/reports/research_R5/H42/local-20260926/R5_HANDOFF_RECEIPT.json) и [H43 delivery](https://github.com/jabrailkhalil/hack/blob/5ed818bbb1ee780d545c4f7a0ed28792132f879c/reports/research_R5/H43/local-20260926/DELIVERY.json). Они указывают полные пакеты как conversation artifacts, не Actions artifacts; H42 явно запрещает заменять полный manifest квитанцией.

Нативные payload-проверки **не выполнены**, 85+53 upstream-файла здесь не прочитаны. Положительный dependency lock не создан. H42/H43 не запускались заново для восстановления файлов. Нет попытки обойти ограничение доступа. Для продолжения нужны обычные вложения двух ZIP либо разрешённая полная копия; большие audit/raw-evidence ZIP и ещё один dataset не нужны.

## 3. Что фактически выполнено

Source ZIP SHA256 `4823fbdbbb979d7b561841e2831e68f2f7d9d8ec0d14e970f09a38cd51dff4c4`: все **320 путей/байтов/executable bits** дали полный pinned tree. В launch package проверены **29 перечисленных файлов** по размерам и хешам; это целостность полученного пакета, не независимая подпись upstream.

Dataset ZIP: **256294592 bytes**, SHA256 `d0b2483e13990edb8219b0d7bbcafc7ed001cce549a4d3af467069b2472e7d52`. Штатный bootstrap извлёк и проверил хеши **64 train +17 development DB**. SQLite не открывался, GNSS/vehicle measurements не декодировались. Validation/test DB не извлекались. Raw dataset доступен; блокировка относится к зависимым компонентам.

Metadata-only проверка двух копий folds из launch: все **64 bag/group/label/fold назначения** совпали; **50 fit-bags/20 groups**, **14 check-bags/7 groups**. Разные JSON SHA сохранены. Это не фактический bridge извлечённых producer payloads, не разрешение на fitting и не измеренное покрытие GNSS.

Локально: **161/161 canonical unit, 43/43 integrity, 13/13 тестов предоставленных wave-2 tools, 19/19 новых interface tests**, compile PASS. Последние два набора используют синтетические fixtures, не upstream arrays. Новые Actions/replay/ROS-проверки не запускались; [skip ci] не объявляется зелёным CI.

В первом запуске interface tests было 18 PASS/1 ERROR: тест вычислил крайний s чуть выше длины из-за floating arithmetic. Исправлено только построение тестового endpoint на точное length; строгий Route.at, tolerances и algorithm не изменялись. Исходный и повторный логи сохранены. Второй запуск: 19 PASS.

## 4. Реальные изменения кода и их границы

`research/R5/H48/geometry_interface.py` — интерфейс заданного ordered metric graph. Он требует явные edge/node IDs, метры, конечные XYZ и provenance, использует существующий Route.at без переписывания. Соединение существует только по заданному node ID с совпадающими endpoint coordinates: пересечения и близкие ветки не соединяются автоматически. Разрыв не интерполируется между несвязанными рёбрами. Две одинаковые координаты на разных s в петле остаются разными гипотезами; общий vertex двух соседних segments одного edge не дублируется.

Nearest projection возвращает несколько вариантов при неоднозначности; это горизонтальная XY distance, а s сохраняет исходную 3D Euclidean arc length Route. Z интерполируется, но не используется как oracle для выбора ветки. Вертикальные XY-degenerate segments отклоняются как неподдерживаемые этим интерфейсом. Tangent quaternion не объявляется body heading. Порог близости/неоднозначности — явный аргумент caller, не подобранный START_V0 threshold.

State ограничен 1024 edges/20000 points и реальным encoded budget 1000000bytes. Prototype serialization всегда содержит `component_ready=false`, `coordinate_transform=NOT_IMPLEMENTED`, `extrinsics=UNRESOLVED`. Ни синтетический graph, ни этот интерфейс не публикуются как реальная карта, MAP_V0 или map handoff.

Проверены crossing/switch/gap/loop/reverse/finite/budgets/serialization и 200 seeded Euclidean projection cases с независимым дискретным oracle. Wolfram реально подтвердил шесть скалярных тождеств: стационарную точку, выпуклость, reversal parameter/point, quadratic decomposition и reversal после clipping. Worksheet/output сохранены. Это не геодезическое преобразование, map accuracy, body pose или доказательство всей топологии маршрута.

## 5. Невыполненные измерения и контракт

Control/candidate cross-track RMSE, p95, compression, real topology/coverage, per-bag/per-group geometry, START_V0, MAP_FIT/MAP_V0/full-train build, runtime latency/RSS: **N/A / NOT_RUN**. Objective calls **0**. Real-data regressions неизвестны, а не отсутствуют. Native dependencies, полный coordinate/reference contract и numerical DESIGN_FREEZE ещё нужны до координатного fitting. Исходные бюджеты двух representations и 20/7 folds не расширены.

Q&A разрешает offline GNSS и общий маршрут; одновременно официальный reference описан как combined localization/XYZ, точные antenna extrinsics не предоставлены. Эта подготовка не преобразует GNSS в официальную MGRS/base_link систему. Будущая карта без extrinsics остаётся antenna-trajectory proxy. Teacher noncausal quality нельзя использовать в causal startup window.

## 6. Воспроизведение и точка продолжения

Проверка уже опубликованного интерфейса, без датасета и dependency ZIP:

```bash
git fetch origin research/R5-H48
git worktree add --detach /tmp/h48-interface 0e3c0baaa4adefb145d0d7f823f1f2734a7adf68
cd /tmp/h48-interface
PYTHONPATH=src/reserve_odometry python -m unittest discover -s tests -v
PYTHONPATH=src/reserve_odometry python -m unittest discover -s research/tests -v
PYTHONPATH=src/reserve_odometry python -m unittest discover -s research/R5/H48 -p test_geometry_interface.py -v
python -m compileall -q research/R5/H48
```

Для integrity-тестов нужны исходные requirements-research; текущее локальное окружение: Python3.13.5, NumPy2.3.5, SciPy1.17.0. Полный список реально исполненных команд и логи находятся в выдаваемом evidence package.

Следующая стадия после получения полных архивов, в НОВЫХ каталогах:

```bash
PACK=/path/R5_wave2_H44-H48
python "$PACK/tools/precheck_components.py" \
  --teacher-zip /path/R5_H42_teacher_component.zip \
  --atlas-zip /path/R5_H43_atlas_handoff.zip \
  --extract-to /tmp/h48-dependencies-new \
  --receipt /tmp/h48-transport-new.json
```

Затем установить component roots по transport receipt, прочитать полные manifests, выполнить native teacher/atlas verifier, bridge фактических folds и новый общий lock. Только затем зафиксировать numerical DESIGN_FREEZE (spacing/smoothing, masks/frame/provenance, solver budget) и выполнить H48 fit/check. Этот checkpoint не содержит готового fitting runner. Перезапуск upstream или старых H38/H18 не требуется.

Полные SOURCE_RECEIPT/DATA_RECEIPT, pending dependency receipt, metadata folds, package/source hashes, оба test logs и patch переданы локальным ZIP, не Actions artifact; внешняя retention не гарантируется. Датасет и upstream arrays в evidence не включены. Main, чужие ветки и опубликованные отчёты не изменены. Merge, auto-merge, force-push не выполнялись.
