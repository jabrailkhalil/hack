# R4-H39 — INCONCLUSIVE: train выполнен, основание интервального измерения не установлено

## Решение
Приложенный `dataset(6).zip` снял блокировку прежнего NOT_EVALUATED. Исполнен **неизменный**
`foundation.py` из `8ce1a1b708aa72e6f2126c77c023647f6febf247`: все 64 train bags,
один пререгистрированный поиск, без изменения PLAN/порогов/групп.

**Решётка не установлена ни для front, ни для rear.** Квалифицированных групп достаточно.
Runtime-кандидат, posterior-effect gate и validation не выполнялись согласно stop-rule.
Это **INCONCLUSIVE научного основания, не REJECTED по accuracy**; q_front/q_rear=null,
не0. Исследовательский артефакт, не готов к merge. Продолжение PR #52; не новый PR.
Старые отчёты и canonical runtime не изменены.

## Версии и исполнение
Baseline `e3b0c9c039d2953fbfcda51231263d38ef9f1024`, tree
`eae49a504bc59b5c9b408445150bef32e111956f`: повторно проверены все301 bytes/modes.
PLAN до train: `28afa1e554d71093164145b250b11e47fff95d22`.
Измеренный diagnostic source: **8ce1a1b708aa72e6f2126c77c023647f6febf247**.
foundation.py SHA256: `edfb20e6159e0b3236de3c14dbedd4940e4d9d8f7a6628c1d871125e9e64d951`.
Runtime candidate SHA / measured_source_sha / FREEZE: **N/A**.

Execution ID `local-train-20260926T093203Z`, train start
`2026-09-26T09:33:51.570155+00:00`. Это Python/subprocess локально, не Actions.
Новые stage_local.py и audit_saved.py — транспорт и аудит, не изменение научного
estimator; исполнены локально перед их поздней публикацией. SHA в MANIFEST.
Report/checkpoint commit связывается отдельным append-only PUBLICATION.json
и PUBLISHED_SUMMARY.json: исходный SUMMARY не переписывается.

## Данные
Dataset 256294592 bytes; SHA256
`d0b2483e13990edb8219b0d7bbcafc7ed001cce549a4d3af467069b2472e7d52` — exact pinned.
Source ZIP SHA256
`a8e0bfa033e0a02c460c30b02f34a5c64ece85b05003512941387d3cf1f319a2`.
Извлечены только64 train DB; bytes/SHA256 каждой проверены по frozen split.
Development/validation/test DB не распакованы. Полные архивы/DB хешируются как bytes,
но SQL/decode — только controller/front/rear, без train GNSS.

2646426 vehicle events, 27 исходных групп; 48 уникальных wire-потоков после исключения
16 повторов из статистики. Все64 файла прочитаны. Потоки не объявляются независимыми
поездками. Разделение было18 fitting/9 check; qualified осталось10/8 на каждом канале,
при минимуме8/4. Все остальные группы сохранены в per_group.csv.

## Train-результаты
| Показатель | front | rear |
|---|---:|---:|
| Eligible, с wire-дубликатами |98668|96570|
| Eligible, без wire-дубликатов |86799|84720|
| Eligible в qualified groups |83219|81154|
| Qualified fitting/check groups |10/8|10/8|
| Fit-only q proposals |4851|4726|
| Прошедшие coherence >=0.975 |0|0|
| Выбранный q/shift |N/A|N/A|
| Qualified groups с practical pair support >=98% |0/18|0/18|

Предложения q — внутренний бюджет опубликованного идентификатора, не тысячи
runtime-кандидатов. В поиске q=[1e-6,.5] м/с ни одно предложение не прошло coherence.
Поэтому fixed-q check не выполнялся: не было выбранного на fitting шага.
Это не «нулевая точность» выбранного q.

Основной subset использует новые timestamps, меняющиеся finite values0.1–40 м/с,
свежую разрешённую команду, backward wheel interval<=.25с. Нули/постоянные скорости
и округлённый CSV не принимаются за решётку. Ни check, ни GNSS не выбирают q/shift.

### Отдельное необходимое условие practical lattice
Предзаданный floor q²/(12*0.1²)>=.01 даёт q>=0.03464101615137755 м/с.
Это порог, не измеренное разрешение. Для каждой группы до512 непересекающихся
пар внутри bags; continuous-q sweep в [0.034641..., .5] м/с проверяет близость
разности к целому числу шагов. Shift исключается. Требование >=98% пар
в >=80% qualified групп каждой роли.

| Канал/роль | Групп | Медиана лучшего pair support | Максимум |
|---|---:|---:|---:|
|front/fitting|10|3.61328125%|4.8828125%|
|front/check|8|3.90625%|4.6875%|
|rear/fitting|10|3.90625%|4.4921875%|
|rear/check|8|4.19921875%|4.8828125%|

Во всех qualified группах512 пар. Лучший результат —25/512, даже разрешая каждой
группе собственный наиболее благоприятный q. q_at_max — диагностический witness,
не калибровка. Все50 непустых channel/group maxima независимо проверены.

Regime coverage достаточен: >=300 samples на traction/brake в10 fitting/8 check
группах на канал; coast —8/7. Lattice fit по режимам N/A, поскольку q не выбран.
Числа в per_regime.csv. Причины на обоих каналах:
LATTICE_NOT_ESTABLISHED; NO_PRACTICAL_LATTICE_PAIR_SUPPORT:fitting/check.
Недостаток числа qualified групп не является причиной остановки.

## Проверки и ограничения
До train: **156 baseline +43 research-integrity +22 H39 tests PASS**, compileall PASS.
После: все301 baseline files и4 научных files unchanged.
Независимый audit_saved.py проверил12 hashes,128 NPZ arrays,64 train-only access,
dedup/groups/counts и50 bounds через прямой endpoint/midpoint подсчёт в longdouble.
Он не выполнял fitting и не открывал DB. Это аудит одного эксперимента, не независимый test.
Foundation wall20.815392593с — не runtime latency.

Python3.13.5, NumPy2.3.5, SciPy1.17.0, OPENBLAS/OMP=1.
В stderr есть предупреждения предустановленного artifact_tool при старте Python;
они не относятся к H39, все научные команды exit0, журналы сохранены.
Локальный diagnostic patch проверен git apply --check на чистом baseline.

Нового Actions research-run нет; EXECUTE.json/workflow не менялись.
Прежний failure36231320102 не объявлен success. Обычный CI report commit не
сертифицирует отсутствующего candidate. Merge/auto-merge не выполнялись.

Baseline-only development уже реально воспроизведён на предыдущем этапе:
reports/research_R4/H39/36231320102-1/BASELINE_AGGREGATES.json.
Эти числа не переименованы в train accuracy или результат H39-кандидата.
Candidate clean/fault/distance, guards, enabled ROS обоих clocks/2CPU500MB,
validation/final-test: **NOT_RUN_AFTER_FOUNDATION_INCONCLUSIVE**.
Ранее выполненная математика сохранена в старом evidence; новых литературных
или математических результатов в этом продолжении не заявляется.

Вывод ограничен зарегистрированными моделью решётки/диапазоном/subset.
Не исключены микроскопическое, неравномерное квантование или иная обработка;
аппаратное разрешение/причина непрерывности не установлены.
512 пар — конечная audit-выборка, не probabilistic guarantee всех будущих данных.

## Воспроизведение
На checkout этой research-ветки; новый output для каждой команды:
```bash
python -m pip install -r requirements-research.txt
sha256sum -c research/R4/H39/MEASURED_CODE.sha256
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
export GITHUB_SHA=8ce1a1b708aa72e6f2126c77c023647f6febf247
python research/R4/H39/stage_local.py --archive /path/to/dataset.zip --output /tmp/h39-train-new
python research/R4/H39/foundation.py --data-root /tmp/h39-train-new/data --output /tmp/h39-foundation-new
python research/R4/H39/audit_saved.py --results /tmp/h39-foundation-new --split research/split_v3.json --output /tmp/h39-audit-new.json
```
GITHUB_SHA локально связывает точные scientific bytes с опубликованным source,
не изображает Actions execution. Для ZIP без Git history в архиве ответа есть
verify_source.py и полный offline runbook.

Git хранит compact SUMMARY, per-bag/group/regime CSV, MANIFEST/AUDIT и REPORT.
Полные raw JSON/NPZ/access/logs — в приложенном архиве ответа, raw bags исключены;
нового Actions artifact не существует. NPZ SHA256
`d6f8b2bb5f7d4e2a08ee9f7386bc9616311d0262b0bcdba53928b667f45fe859`.
Подробный REPORT_EXTENDED также включён. Протокол останавливается здесь;
ретюнинг или новая модель не выполняются под прежним ID.
