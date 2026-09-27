# v8_residual070: проверка перед выпуском

Кандидат из PR62 сохранён без изменения float, параметров, core и readout.
**Статус этой публикации: RELEASE_BLOCKED_NOT_VERIFIED. Main не переключён.**
Это исполнимый стенд выпуска, а не подтверждение нового validation-результата.

## Что уже опубликовано

`prepare.py` проверяет исходный dataset.zip и извлекает ровно 19 validation DB.
`validate.py` сравнивает только v8 и зафиксированный residual070: clean, прежние
отказы, полные faulted записи, low-speed/abrupt/slow suites, 30618/30639 отдельно,
индивидуальные ошибки/покрытие/recovery, интеграл пути и исходный fingerprint v8.
Сохраняются полные массивы, per-bag JSON, журнал доступа и манифест SHA256.
Никакого fitting, выбора нового cap, чтения final test или автоматического merge.

`ros_selected.py` запускает именно установленный GuardedReadoutObserver с
исследовательским YAML. Проверяются пути и hashes installed Python-модулей,
оба clock modes через существующий GetParameters/publication smoke, затем
fault/pause/seek и CDR. Исходные tests/config/default не переписываются.
Это smoke под ресурсным ограничением, не длительный end-to-end latency benchmark.

## Выполнено в этом проходе

Локально: 24 новых release-теста + 27 прежних candidate-тестов + 156 исторических
runtime-тестов + 43 integrity = **250 PASS**. Python compileall, YAML parsing и
bash syntax проходят. Все 19 baseline pins и 10 frozen candidate files совпали.
Локальная исходная копия: e3b0c9c numerical snapshot с точным candidate overlay;
новые пять main packaging tests не выдаются за пройденные. Полный synthetic
worker выполняется с искусственными входами и намеренно получает REJECTED по
baseline fingerprint: синтетика не подменяет validation. Первый test fixture
выявил отсутствие безопасной обработки неполного fingerprint; исправлено до
реальных данных, failed log сохранён. Изменений алгоритма по этому тесту нет.

**Попытка GitHub Actions 36274037856** на f79af8b19346bf73e017f7b4f2bc48311b6190a4
завершилась до исполнения: обе jobs failure, steps=[], runner_id=0, artifacts=[].
Следовательно, ни download/validation, ни ROS не выполнены. Причина runner stop
по доступным ответам не установлена; billing/quota не объявлены причиной без данных.
Ретрай не запрошен. Более полный runner/workflow опубликован затем с [skip ci],
что не считается CI PASS. Изначальный ROS glue дополнительно сверён с нынешним
installed-path выражением fault probe и заменён отдельным проверяемым adapter.

В текущей среде есть 17 development DB, но нет 19 validation DB и ROS/Docker.
Полный старый research-workspace artifact не сохранился; прямой источник Yandex
не доступен из этой среды. Старые development -23.98% / -11.00% не пересчитаны
как validation и не являются новым результатом этого прохода. Старые отчёты
кандидата и main сохранены неизменными.

## Запуск на машине с исходным dataset.zip

Из полного checkout этой release-ветки, Python 3.13.5, новые каталоги результата:

```bash
python -m pip install -r requirements-research.txt PyYAML==6.0.2
PYTHONPATH=src/reserve_odometry python -m unittest discover -s research/v8_release -v
python research/v8_release/prepare.py --archive /absolute/dataset.zip --output /new/validation-inputs
python research/v8_release/validate.py --data-root /new/validation-inputs/data --output /new/validation-results --workers 2
```

Код возврата 0 = numerical VALIDATION_PASS, 2 = VALIDATION_REJECTED; ошибка ввода
или исполнения создаёт FAILURE.json и не даёт права на выпуск. Существующие
каталоги не перезаписываются. При отсутствии archive prepare пытается скачать
старый checksum-pinned ZIP. Final-test DB не извлекаются и не декодируются.

ROS-проверка описана в `.github/workflows/v8-residual070-release-preflight.yml`:
сначала provision Docker image, затем build/check без сети, 2 CPU / 500000000 B.
Два jobs не меняют main; зелёный численный результат сам по себе не является
проверкой installed default, latency/RSS либо официального XYZ.

## Что требуется для main

Положительный численный RESULT на полном validation и фактически выполненный
installed ROS check. Затем отдельное согласованное переключение установленного
YAML/launch/ACTIVE_SOLUTION, повтор проверки default и merge с expected head SHA.
Никакой force-push. При провале оставить v8. Последующие гипотезы развивать
отдельно на development, не подстраивать frozen residual070 по validation.
