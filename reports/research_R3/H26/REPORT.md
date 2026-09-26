# R3-H26 — INCONCLUSIVE: основание colored measurement noise не установлено

**Исследовательский артефакт, не готов к merge.** Проверка остановлена на предусмотренном карточкой этапе основания. Положительная serial correlation существует, но сильно зависит от контроля возраста измерений и динамической ошибки. Предзаданный консервативный критерий допуска к AR(1) не выполнен. Это НЕ отрицательный accuracy-результат AR(1) и НЕ доказательство белого шума.

## Версии и границы

Round `R3-v8-fixed`; baseline `e3b0c9c039d2953fbfcda51231263d38ef9f1024`. Класс `GuardedReadoutObserver`, профиль `champion_v8.yaml`, executable `guarded_odometry_node`; опубликованные Estimate.v/s, 20 Hz, alignment_delay=0, readout gain=1/holdoff=.5, adaptation_tau=.5, wheel_time_compensation=0, common_mode_quarantine=1.5. Все физические параметры прочитаны из точного YAML, не Config defaults.

До создания `research/R3-H26` проверены ветки и PR с scientific ID R3-H26: совпадений не было. Только собственная ветка создана от baseline. Main, другие ветки, старые отчёты, freeze/release manifests и данные не изменены. Merge и auto-merge не выполнялись.

- Предварительный протокол основания, до measurement IO: `92e8271945f06f8ff332eeb41816cb8d6a8332dc`, `research/R3/H26/PRECHECK.md`.
- Первый локальный diagnostic run выполнен после этого протокола. Сам скрипт на момент первого локального запуска ещё не был опубликован; его SHA256 записан в started.json.
- Затем опубликован ПОБАЙТНО тот же скрипт: `009ee7731d26085f4e885865d57259125633d3b3`. Git blob `3812a721f87c15cddf3926cc06b62148bb511408`; SHA256 `b1a046dc1599d8c3ebedfc407319f99cd4b9e57251d270647de86afcac601b9f`.
- Исполняемый source SHA повторного Actions-исследования: `9e79e550936a3c1302fbb02fd1dd28a72714a36f`.
- Measured candidate SHA: **N/A — AR(1)-кандидат не создан**. Validation FREEZE SHA: **N/A**.
- Этот отчёт, математические материалы и анализ сохранённых таблиц добавлены позже; алгоритмического подбора после результата не было.

## Что реализовано, а что нет

Реализован train-only диагностический driver `foundation.py`, пассивный Probe поверх полного canonical v8, проверка source/profile/split, безопасное чтение ролей, заранее заданное group-balanced отделение динамической составляющей, per-bag/per-group статистики и воспроизводимые тесты. В нём нет AR(1)-обновления, новой covariance или экспериментальной коррекции скорости/дистанции.

Probe вызывает неизменный baseline step и вычисляет диагностические величины после него, не записывая унаследованные состояния. Небольшое временное окно команд находится во внешнем offline collector, maxlen=64. Сохранённые длинные трассы — исследовательские данные, не runtime history. Никакая диагностическая age adjustment не возвращается в observer.

Минимальный патч содержит исследовательский driver и тесты, **не улучшение runtime**. Hook реального effective gain и state [v,b] не внедрялись: до этого этапа не получен допуск по основанию. Feature-off equivalence нового AR(1) не заявляется; проверена эквивалентность пассивного Probe.

Прочитаны H10/PR18 (joint [v,d], не H18), H18/PR37 и H18/PR38 с точными source/report версиями из карточки. Их числа не перенесены в H26. H26 не повторяет outage covariance/увеличение Q и не меняет mean d.

## Предварительная методика

Оригинальные 64 train bags, только controller/front/rear; GNSS train запрещён. Source groups взяты из исходного split. Разделение до измерений: группы отсортированы по SHA256('R3-H26:'+group); каждая четвёртая — check. Получено 20 fitting / 7 check групп; связанные bags не разделялись.

Trusted запись — две НОВЫЕ принятые FUSED пары, |front−rear|≤0.15 м/с, |z|>0.5 м/с, неустаревшая команда, |z−v_prior|≤3*wheel_sigma. Не используются дубликаты; разрывы доверия/времени разбивают последовательности. Для lag-1 соседние пары должны иметь интервал 0.08–0.12 с и принадлежать одному сегменту; через разрыв или между bags пары не строятся.

Отдельно сохранены raw innovation и diagnostic age-adjusted residual e_age=e_raw+a_model*mean_age. Steady subset: ≥2 с здоровых данных, диапазон команды за прошлые 2 с≤0.02, |drive_target−drive_a|≤0.1 м/с². Tight subset добавляет |предыдущее trusted wheel acceleration−текущее model acceleration|≤0.2 м/с².

Однократно решена фиксированная ridge-регрессия e_age на fitting-группах, равный суммарный вес каждой группы. Признаки и масштабы заранее записаны в PRECHECK: intercept, command, v_prior/40, a_model/3, actuator mismatch/3, old d/0.6, previous wheel-a mismatch/3, mean age/0.25, skew/0.1. Ridge=0.001 для не-intercept. Lagged innovation не входит. Фактически 351957 конечных fitting-точек в 18 группах; все коэффициенты сохранены и без изменения применены к check. Это nuisance diagnostic, не AR(1) likelihood и не новая калибровка физики.

Для достаточного основания заранее потребованы ≥3 check-группы с ≥200 tight adjacent pairs каждая, ≥1000 пар всего; положительная корреляция≥0.1 и RMS≥0.01 м/с хотя бы в 2/3 групп; median≥0.1; отсутствие смены знака fitting/check; сохранение **не менее половины** положительной медианной age-adjusted steady correlation после контроля. Последнее — консервативный prospective admission, **не общая теорема идентифицируемости**.

## Измеренный результат основания

Все 64 train записи обработаны; 1366299 опубликованных outputs; 444165 trusted innovations в 25 исходных группах. Это не 444165 независимых поездок и не измерение ground-truth error.

| Основание на check | Измерено | Условие |
|---|---:|---:|
| Qualifying tight check-групп | 5 | ≥3 |
| Adjacent tight check-пар | 8231 | ≥1000 |
| Поддерживают corr≥0.1 и RMS≥0.01 | 5/5 | ≥2/3 |
| Median age-adjusted steady lag-1 | 0.844509950 | диагностическая база |
| Median controlled tight lag-1 | 0.285683716 | ≥0.1 |
| Сохранённая доля корреляции | **0.338283422** | **≥0.5 — FAIL** |
| Median controlled fitting lag-1 | 0.429676609 | без смены знака |

Машинная причина: `correlation_not_retained_after_dynamics_control`. По PRECHECK: **INCONCLUSIVE**, AR1 objective calls=0, actual candidate interventions=0. Достаточно покрытия диагностической проверки; полезное вмешательство кандидата не проверялось.

| Check group | Tight adjacent pairs | Controlled lag-1 | Residual RMS, м/с |
|---|---:|---:|---:|
| 2b1581126a480c0f | 1335 | 0.267687029 | 0.018726485 |
| 86c32e441a296aaa | 2676 | 0.402232290 | 0.019287911 |
| f28fe86416cc8dc2 | 1624 | 0.285683716 | 0.019528402 |
| eeabf7d118bbcdac | 1817 | 0.450086473 | 0.022441701 |
| 4ca08ed0da0cb611 | 779 | 0.232635600 | 0.015324538 |

Оставшиеся check группы не скрыты: 5c1be3e9a2189121 имеет лишь 39 tight пар (corr0.159806539, RMS0.032467340), ниже заранее заданного покрытия; 96d0ec5b7ee50e7e — 0, метрики N/A, не ноль ошибки. Полные 27 group×9 и 64 bag×9 строки в per_group.csv/per_bag.csv.

### Что означает изменение корреляции

Корреляция **не исчезла** и отрицательного AR(1) accuracy-эксперимента нет. Сравнение 0.8445→0.2857 включает и ужесточение subset, и nuisance model; нельзя приписать всё одному регрессору. Отдельно показаны все комбинации raw/age/controlled × trusted/steady/tight.

Post-hoc разбор уже сохранённых CSV, не повторная настройка: на одинаковых пяти qualifying check-группах медианная raw tight correlation=0.065231022; после только age adjustment на том же tight subset=0.706181200; после nuisance control=0.285683716. Медиана age-adjusted steady на тех же пяти группах=0.839921590; retention=0.340131411, также меньше исходного 0.5. В исходном admission steady qualifying median использует 6 групп, controlled tight — 5; это раскрыто, а порог и код не менялись.

Сильная зависимость от модели/age correction мешает устойчиво приписать остаток transient observation error. Вместе с тем контроль по колёсной производной способен удалить часть настоящего colored noise. Поэтому результат не доказывает отсутствие colored noise и не опровергает семейство state augmentation.

## Accuracy и непройденные этапы

Clean/fault/pooled/distance RMSE H26: **N/A**, не 0 и не значения v7/H16/H18. Original и low-speed/common-mode candidate suites не запускались. Отдельных per-receiver/per-fault accuracy таблиц нет, поскольку train GNSS и инъекции кандидата не открывались. Предполагаемые регрессии скорости/дистанции не выдумываются.

Один AR(1) вариант с rho∈[0,.9], ≤60 objective calls и explicit gain hook был только условным следующим этапом PRECHECK. В отсутствие основания он не выполнялся. Полный candidate PLAN/FREEZE не создавался, development admission и validation не расходовались. Это предусмотренная остановка, не недоступность GitHub или данных.

Runtime CPU step/replay AB/BA, enabled ROS replay в двух clock modes, node RSS/latency под 2CPU/500000000 bytes: **NOT_RUN_NO_CANDIDATE**. Полное wall/CPU время foundation script — стоимость offline диагностики/сохранения, не время ноды или latency. Успешный baseline CI нельзя приписывать несуществующему включённому кандидату.

## Математические проверки

Для A=diag(1,rho), H=[1,1] Wolfram подтвердил det([H;HA])=rho−1. Это только линейный sanity: rho=1 смешивает velocity offset и постоянный bias. Устойчивость scalar AR component при |rho|<1 не равна устойчивости нелинейного switched observer.

При P=[[a,c],[c,d]], S=a+2c+d+R:

```text
Kv = (a+c)/S
Pvv+ = a − (a+c)^2/S
1 − Pvv+/a = (a+c)^2/(a*S)
(1 − Pvv+/a) − Kv = c*(a+c)/(a*S)
```

Поэтому прежняя scalar readout-реконструкция K вообще неверна при cross-covariance. PSD-пример P=[[.02,.005],[.005,.01]], R=.01 даёт Kv=.5, старую реконструкцию .625. Explicit gain hook потребовался бы при продолжении; здесь hook не реализован и double age correction не вносится.

Проверены полная Joseph-форма, равенство условному covariance update, det(P+)=R*(ad−c²)/S; stationary Qb=(1−rho²)*B; условный белый предел при cross-prior=0, Pbb=B и Rwhite+B=Rtotal. rho=0 сам по себе не объявляется exactv8. Дополнительно независимый numeric check 5000 PSD-матриц: max Joseph/direct разность 4.44e−15, min eigenvalue 7.84e−9. Worksheet и действительный Wolfram output сохранены; предшествующий semantic WolframContext ошибочно понял один запрос, это не использовано.

## Источники и ограничения научного вывода

Liu, Shi, Zhang, DOI10.1016/j.cam.2022.114138: прочитан индексируемый abstract первичного издателя и metadata университетской карточки; прямой fulltext open вернул403. Полный текст не прочитан. Abstract мотивирует state augmentation для finite-step noise, но не доказывает пригодность AR(1) или точность v8. Consensus/Scite не опрашивались повторно из-за указанных в задании известных месячных quota stops; новые несуществующие отказы не заявляются. Источники/границы доступа в SOURCES.md.

Training innovations обусловлены моделью, gates и sample timing; не независимая истинная measurement error. Отсутствует независимая ground truth для train. Равный вес связанных групп не превращает их в гарантированно независимые эксперименты. Никакой статистической значимости улучшения точности не заявляется.

## Выполненные проверки и evidence

Исследовательский [Actions run 36220603528 / attempt 1](https://github.com/jabrailkhalil/hack/actions/runs/36220603528) завершён success. Это воспроизведение foundation, не принятие AR(1). Source SHA: `9e79e550936a3c1302fbb02fd1dd28a72714a36f`. Сохранённый checkpoint: `1fee2a9d5c235346a3e54ba1a92205f442248e5c`, ветка `checkpoint/R3-H26-foundation-36220603528-1`.

В исследовательском job: **156 исторических runtime unit tests, 43 research-integrity tests и 13 H26 diagnostic tests — PASS**; compile PASS. Локально дополнительно те же 13 diagnostic tests PASS. Проверки относятся к пассивному Probe/неизменному v8: полное state/Estimate равенство на mixed 2000-step потоке, causal prefix, duplicates, future/stale, reset, разрывы, оба знака common bias, zero-lock и quarantine; no-check-target fitting, group isolation, запрет других ролей до DB IO.

Первый полный реальный train bag `30618_0259fe53`: **24562 published outputs** Probe и независимо созданного canonical v8 равны, все унаследованные поля проверены потактово, расписание и runtime counters совпадают. Применён неизменный official replay/score. Train GNSS закрыт: scorer RMSE=NULL/coverage0 по пустым reference, это не quantitative accuracy baseline.

57 оригинальных source/config/role файлов сверены побайтно и SHA256. Изначальный source archive дополнительно сверялся с pinned Git blob SHA. Материализация первой локальной копии брала byte-identical train/development DB из ранее доступного H16 input artifact; SQL читался только train. В Actions скачан исходный organizer ZIP SHA256 `d0b2483e13990edb8219b0d7bbcafc7ed001cce549a4d3af467069b2472e7d52`; извлечены ТОЛЬКО 64 исходных train DB. Validation/test members не распакованы, train GNSS topics не запрашивались. Access journals и preparation manifest сохранены.

Remote/local result и все per-group/per-bag numeric fields: **4689 сравнений, max absolute delta 9.992007221626409e-16**. Hash foundation.py совпадает. Wall/CPU поля исключены из численного сравнения; это воспроизводимость на тех же данных, не независимое подтверждение. Локально foundation wall43.530805343/CPU43.524810462с; Actions wall102.979064305/CPU102.692405190с. Разница среды не трактуется как изменение runtime алгоритма.

[Обычный CI измеренного source 36220603509](https://github.com/jabrailkhalil/hack/actions/runs/36220603509): все 4 jobs success, включая сборку/штатные ROS smoke и offline2CPU/500MB. Они исполняют неизменный v8 и НЕ являются enabled AR(1) ROS benchmark. CI более позднего отчётного HEAD не подменяется этим source CI.

[Компактные результаты по immutable checkpoint](https://github.com/jabrailkhalil/hack/tree/1fee2a9d5c235346a3e54ba1a92205f442248e5c/reports/research_R3/H26/R3-H26-36220603528-1): PRECHECK, source manifest, result.json, baseline_sanity.json, access, activation, per_group.csv/per_bag.csv, dependency/test/run логи, SHA256 каждого trace. Крупные trace NPZ не закоммичены.

Actions artifact **10899112982**, `R3-H26-foundation-36220603528-1`, 42040653 bytes, ZIP SHA256 `fe010daf5ce9ff9faf46f626fc8206e7f83f3ac75b895b29a02b4c8e50bc8291`, retention30days, expiry **2026-10-26T05:25:05Z**. Архив скачан, все 84 записи внутреннего SHA256 manifest проверены. В нём один комплект compressed traces; нет raw bags. Исходники диагностического run дополнительно включены как небольшой measured_source.zip. После expiry воспроизведение возможно командами ниже; Git checkpoint сохраняет компактные результаты.

## Команды воспроизведения

Выполненный локально первый запуск после PRECHECK:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python research/R3/H26/foundation.py \
  --data-root /mnt/data/h26/permitted/dataset/data \
  --output /mnt/data/h26/foundation-local
```

Повтор Actions на точном source, без AR(1)-fitting или validation:

```bash
git fetch origin research/R3-H26
git worktree add --detach ../hack-R3-H26 \
  9e79e550936a3c1302fbb02fd1dd28a72714a36f
cd ../hack-R3-H26
python3.13 -m venv .venv-research
. .venv-research/bin/activate
python -m pip install -r requirements-research.txt
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
python research/R3/H26/support.py manifest
python -m unittest discover -s research/R3/H26 -p test_foundation.py -v
PYTHONPATH=src/reserve_odometry python -m unittest discover -s tests -v
python -m unittest discover -s research/tests -v
OUT="$(mktemp -d /tmp/R3-H26-XXXXXX)"
python research/R3/H26/support.py train --path "$OUT/input/data"
python research/R3/H26/foundation.py \
  --data-root "$OUT/input/data" --output "$OUT/foundation"
python research/R3/H26/support.py inventory --path "$OUT/foundation"
```

Измеренная версия Python3.13.5, NumPy2.3.5, SciPy1.17.0; output обязательно новый. `support.py manifest` создаёт идентичный список 57 исходных hashes, сверяя pinned Git objects, а не переписывая исторические guards. Для локального дополнительного math check использовать поздний отчётный source с `research/R3/H26/math_check.py`; это проверка формул, не новый candidate replay.

## Статусы

```text
mechanism_status: FOUNDATION_CONFOUNDED; AR1_OBSERVER_NOT_IMPLEMENTED
coverage_status: SUFFICIENT_FOR_FOUNDATION_CHECK; NO_CANDIDATE_INTERVENTION
scientific_verdict: INCONCLUSIVE
accuracy_contract_passed: false
accuracy_contract_evaluated: false
runtime_verified: false
ready_to_merge: false
```
