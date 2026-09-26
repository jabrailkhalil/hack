# R4-H33 — INCONCLUSIVE после реальной train-проверки

**Исследовательский артефакт, не готов к merge.** Приложенный dataset.zip снял прежний блок данных. Исполнен ранее подготовленный диагностический код, без изменения PLAN, subset, порогов или окон. Основание модели независимых endpoint errors не прошло зарегистрированный prerequisite. Это **не REJECTED accuracy GLS**: runtime-кандидат не создан; development, freeze, validation и final test не запускались.

Прежний отчёт NOT_EVALUATED в `36231152403-1/` сохранён неизменным: он описывает предыдущую недоступность исполнения. Новый execution ID: `local-H33-dataset-20260926`, backend — локальный контейнер, **не GitHub Actions**.

## Версии и идентичность

- Baseline: `e3b0c9c039d2953fbfcda51231263d38ef9f1024`, tree `eae49a504bc59b5c9b408445150bef32e111956f`.
- Канонический GuardedReadoutObserver, полный champion_v8.yaml; 20 Hz / delay 0; readout 1/.5, adaptation tau .5, wheel_time_compensation 0, quarantine 1.5. Измеряются возвращаемые Estimate.
- PLAN: `2d27233cf3bea27c8343cc42ed3c6ece4c4477a6`, blob `9fc5c61995a3183af29a687d153e5b568a5477f8`. Его точная копия приложена рядом, без новых критериев.
- **Фактически исполненный диагностический source: `5c6571789b1c6ca45f9efc74861dc34920e6e308`.** Семь файлов ранее выданного patch сверены с remote Git blobs. Все 301 baseline path/bytes/executable modes повторно проверены в новой pristine-копии, затем остались неизменными в рабочей копии. Локальная Git ancestry не подделана.
- Source ZIP SHA256: `a8e0bfa033e0a02c460c30b02f34a5c64ece85b05003512941387d3cf1f319a2`.
- Measured runtime candidate SHA: **N/A**, freeze SHA: **N/A**. Диагностический SHA не выдаётся за candidate SHA.

## Данные и фактическое исполнение

Пользовательский dataset.zip: **256294592 байта**, SHA256 **`d0b2483e13990edb8219b0d7bbcafc7ed001cce549a4d3af467069b2472e7d52`**, точно совпал с pinned downloader. В новой рабочей папке распакованы **только 64 train-bag из 27 исходных групп**; SHA256 каждого DB совпал с split. Повторный независимый аудит подтвердил все 64 файла.

SQL был read-only и выбирал только `/vehicle/driver_position_cmd`, `/vehicle/front_bogie_velocity`, `/vehicle/rear_bogie_velocity`. Train GNSS не запрашивался. Development/validation/test DB не распаковывались и не открывались. Оболочка общего data.zip переносилась как архив, не как разрешение читать все роли.

Foundation started.json: **2026-09-26 09:25:46.736324 UTC**. Один успешный локальный проход, exit status 0. В started.json переменные с историческими именами GITHUB_SHA/GITHUB_RUN_ID содержат source и локальный execution ID; они **не означают запуск Actions**. Неудачная попытка открыть streaming exec не запустила процесс; затем выполнен один обычный локальный процесс, без повторного fitting/replay.

## Неизменный метод

Пассивный Probe вызывает исходный v8 и не подаёт GLS target в d, скорость, covariance или readout. Диагностируется `y = delta_z - integral(g)`, где g — pre-correction drive minus resistance. Средние native wheel-pair timestamps и ограниченная причинная история g сохраняются; будущие samples не используются. На каждом такте Probe проверяется против отдельного прямого canonical v8 по Estimate и всем унаследованным полям.

Controlled subset задан в PLAN: исходная adaptation eligibility, front/rear difference <= .15 m/s, skew <= .05 s, pair dt .08..12 s, |z| > .5 m/s; предыдущие 2 s непрерывно валидной команды с range <= .02; actuator mismatch <= .1 m/s²; непрерывные сегменты не короче 30 increments. В каждом сегменте вычитается только среднее residual acceleration. Lag-пары не строятся через разрывы или между bags. Корреляции ниже относятся к этому диагностическому residual, **не к известной ground-truth sensor error**.

## Реальный результат основания

| Показатель | Значение | Прежний критерий |
|---|---:|---:|
| Qualifying группы с >=200 lag-1 пар | 4 | >=3 |
| Lag-1 пары в этих группах | 1393 | >=1000 |
| Поддерживают lag-1 в [-.75,-.10] и sigma proxy >=.001 m/s | **0/4** | >=2/3 групп |
| Медианная lag-1 корреляция | **+0.424238821873** | [-.75,-.10] |
| Медиана абсолютной lag-2 корреляции | **0.593642811308** | <=.25 |
| Отличия GLS .40 от unweighted >1e-6 m/s² | 437491 | >=100 |
| Группы с такими отличиями | 25 | >=3 |

Объёма достаточно для предусмотренной foundation-проверки, но её содержательные условия не выполнены. Причины:

```text
negative_adjacent_covariance_not_supported_in_two_thirds_groups
median_lag1_outside_preregistered_range
nonlocal_serial_structure_lag2
```

| Qualifying train group | Lag-1 пары | Lag-1 | Lag-2 | Sigma proxy, m/s |
|---|---:|---:|---:|---:|
| 0d4506540f0e7621 | 385 | -0.042002796 | 0.223948955 | 0.012115259 |
| bc1e4cbe924a90ce | 227 | 0.270863383 | 0.584853587 | 0.018488067 |
| bf69dbfe85be52b0 | 340 | 0.697779051 | 0.783549764 | 0.021108916 |
| eeabf7d118bbcdac | 441 | 0.577614261 | 0.602432036 | 0.016800722 |

Sigma proxy вычисляется как sqrt(mean(centered increment²)/2), исходный wheel_sigma=.1 m/s не переобучался. Значения .0121..0211 m/s — не независимая калибровка настоящего шума.

Неудобные меньшие группы сохранены: например, `0f36b619fba02a9b` имеет 186 пар и lag-1 -0.355931470, `58dd5f96d4201195` — 156 пар и -0.384825620. Их недостаточно по **ранее** заданному минимуму 200; снижать его после просмотра результата нельзя. Вывод не означает, что во всех группах корреляция положительная. Все 27 групп, включая нулевое покрытие, находятся в groups_compact.csv и полном evidence.

## Объём данных и диагностическая активация

- Всего вызовов step и потактовых all-state/Estimate сравнений: **1370779**; опубликованных outputs без WAITING: **1366299**.
- Eligible adaptation pairs: **441264**; history fallbacks: **2**; сохранено **441262** диагностические строки.
- All-trusted сегменты длиной >=30: 1866, 433180 строк, 431314 lag-1 пар.
- Controlled subset до qualifying-group фильтра: **59 сегментов, 2289 строк, 2230 lag-1 пар в 14 группах**. Четыре qualifying группы содержат 35 сегментов/1428 строк/1393 пары.

| Диагностическое окно | Валидные targets | Отличаются от unweighted >1e-6 m/s² |
|---|---:|---:|
| .20 s | 188611 | 185390 |
| .40 s | 437825 | 437491 |

Это вычисления альтернативных целей, **не изменённые runtime outputs**: кандидат не включался и не создавался. Raw results сохраняют RMS отличий от двухточечного endpoint target/unweighted и условные modeled variances. Они не названы clean/fault gain. Перекрывающиеся окна и соседние ticks не считаются независимыми поездками; два колеса не дают автоматического деления variance на два.

## Проверки и аудит

До доступа к измерениям в этой локальной среде повторно прошли **156 legacy + 43 research-integrity + 19 H33 tests**, compileall PASS. Python 3.13.5, NumPy 2.3.5, SciPy 1.17.0; OPENBLAS/OMP threads=1. Диагностические исходники после измерения не изменены.

В train replay выполнены **1370779 exact all-state/Estimate checks**, без unexpected resets и future held inputs. Новый независимый audit_saved.py пересчитал Pearson correlations из сохранённых NPZ без нового DB IO: **3395 числовых сравнений, max absolute delta 7.771561172376096e-16**. Проверены group/window counts, роли всех 64 чтений и неизменность source. Полные таблицы: 162 group/subset/signal строки и 384 bag/subset/signal строки. В raw evidence дополнительно все per-bag JSON и 64 compressed NPZ.

Время foundation loop: 89.883731 s. Внешний process timer: wall 91.10 s, user CPU 90.75 s, system .32 s, max process RSS 310692 KiB. Это **offline диагностика со сбором массивов и вторым проверочным observer**, не step cost кандидата, не node RSS/ROS latency и не проверка бюджета 2 CPU/500 MB. Ни enabled candidate ROS, ни его AB/BA benchmark не выполнялись: N/A_NO_CANDIDATE.

## Научный смысл и ограничения

Формула C=sigma² DDᵀ корректна при заявленной идеальной модели независимых endpoint errors. Ранее исполненный Wolfram worksheet и numerical tests сохранены; повторного вызова Wolfram, Consensus или Scite в этом возобновлении не было. Математика не устанавливает реальные iid ошибки.

Положительные корреляции и существенная lag-2 структура у qualifying групп не дают зарегистрированного основания использовать эту covariance как модель реального residual. Вместе с тем residual включает ошибку g, реальное изменение d, feedback baseline и эффекты отбора/demeaning. Поэтому **не доказаны ни отсутствие white-noise компоненты, ни бесполезность всех GLS-методов**. Итог — INCONCLUSIVE по данному prerequisite, а не REJECTED проверенного runtime-кандидата.

В соответствии с неизменным PLAN после этого foundation failure **не создавался runtime GLS/EMA**, не выбиралось окно по accuracy, не открывались development, validation или final test. Clean/fault/pooled/distance RMSE, MAE/p95/bias/recovery кандидата и его регрессии — **N/A**, не ноль и не старые показатели v8.

## Evidence и воспроизведение

Локальный полный архив **R4_H33_train_evidence.zip**, **56903724 байта**, SHA256 **`fe5b8adc3b7569f993137f451c240c35c2fd5d5b4635e60af3cbafbed5d47fe2`**. 164 members; 163 содержательных файла сверены по manifest SHA256 и CRC. Включены результаты, NPZ, per-bag/per-group таблицы, access/extraction journals, source/data receipts, диагностический patch/source, PLAN reference, прежние math и текущие logs/audit. **Сырых .db3 и dataset.zip в evidence нет.** Архив передан пользователю в текущем чате; это не Actions artifact, гарантированный срок sandbox retention не заявляется. В Git сохраняются компактные результаты и manifest; большие массивы не коммитятся.

Raw results.json SHA256: `a812bfd6c9abe8f58915462226b5565de31b96d32892864422377261dd34983f`.
Canonical scientific-result fingerprint: `d61cc3a6bd890bc2dd1bdd8ca0d8f75de74a60ce7ba5289492f2cedebf294044`.

После checkout source `5c6571789b1c6ca45f9efc74861dc34920e6e308` и установки requirements-research.txt, поместить **проверенный пользовательский dataset.zip** в dataset/dataset.zip, не менять downloader:

```bash
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
export GITHUB_SHA=5c6571789b1c6ca45f9efc74861dc34920e6e308
export GITHUB_RUN_ID="local-H33-repeat-$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$(mktemp -d /tmp/H33-train-XXXXXX)"
python research/R4/H33/test_foundation.py
python research/R4/H33/prepare_data.py --roles train --journal "$OUT/extraction.json"
python research/R4/H33/foundation.py --output "$OUT/foundation"
```

ZIP-only режим, использованный здесь: заново проверить полный baseline штатным verifier; применить выданный диагностический patch; задать H33_SOURCE_RECEIPT на **полный** 301-file receipt. В Git-only режиме receipt-specific test пропускается; здесь с receipt прошли все 19. GITHUB_* выше — исторические имена полей provenance локального driver, не обещание CI.

**Publication:** продолжение того же draft PR #47 и ветки research/R4-H33. Старые отчёты/неуспешный Actions36231152403 не заменяются зелёным CI; новых Actions-запусков в этом возобновлении не инициировали. Report-only commits с [skip ci] не сертифицируют runtime. Main, чужие ветки, старые отчёты и параметры не менялись. Merge/auto-merge не выполнялись.
