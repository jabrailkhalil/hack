# R5-H47 — INCONCLUSIVE / FOUNDATION_FAILED

26 сентября 2026 года. Продолжение existing PR58/research/R5-H47 с проверки покрытия. Это завершённая реальная диагностика, не обученный кандидат и не отрицательный RMSE-результат.

**На всех 64 исходных train bags найдены только 2 допустимые faulty-proxy метки в одной fit-группе и 0 в check. Квалифицирующихся групп 0/3 fit и 0/2 check. Обучение не запускалось.** Старый DEPENDENCY_PENDING преодолён; старые отчёты сохранены, новый scientific verdict INCONCLUSIVE.

## Версии

Baseline `b2783206000091ab11a1c11ac3ff79082188a4fb`, полный tree `973d50d288e050325ee1c71a90fa8d81f2a099af`, все320 paths/bytes/modes проверены. Полный GuardedReadoutObserver/champion_v8,20Hz,alignment_delay=0.
PLAN без изменения: `49fd44ffd5216526c757b2c9b8eb04a88b07ddce`.
Предыдущий head: `5715837a035bb43eff00de719b84f3b3e231ebdd`.
**Измеренный диагностический source: `435f8be420a6512870a6c9d005bb33f968ac7012`**, опубликован и сверен с локальными bytes до первого измерительного replay.
Lock SHA256: `8d51437390d20b9f6d2505ffa53396bddf9d6cc8166be174ebd2ca46c46f3884`.
Candidate SHA / trained coefficients / validation freeze: **N/A**. Последующий report commit не является измеренным source.

## Реальный preflight и метод

Transport и оба producer-native verifier прошли:85teacher+53atlas files. Actual folds bridge подтвердил64 назначения/27 групп. Dataset SHA256 `d0b2483e13990edb8219b0d7bbcafc7ed001cce549a4d3af467069b2472e7d52`; только64trainDB извлечены, сверены и открыты. H42/H43 не пересоздавались; atlas не использовался как label source. Development/validation/final-test DB не извлекались и не открывались.

Vehicle SQL выбирает только controller/front/rear в исходном `ORDER BY m.timestamp,m.id`; decoder, единицы, Timeline и profile неизменны. Native v8 и passive CausalFeatureProbe исполняются независимо; на каждом такте сверяются Estimate, held inputs и все24 native state fields. Только после полного vehicle replay данного bag offline adapter читает frozen H42 `stamp_ns/speed_mps/accepted`.

Метки и признаки прежние: обе READY-строки, native hard-accepted пара, >=1м/с, unique nearest accepted teacher в пределах0.05с от собственного source timestamp каждого колеса. Ошибка<=.20м/с означает clean proxy; >=.50м/с — faulty proxy лишь при clean другом канале. Common/intermediate/missing/ambiguous случаи — abstain. Направление из teacher не выводится. Ни GNSS, ни quality/future flags не входят в runtime features.

До чтения данных COVERAGE_PROTOCOL фиксирует metadata-only wire representative и episode gap>1с в одном bag/time domain. Квалифицирующаяся группа требует>=10faulty updates,>=100clean updates,>=2separated onsets в одном representative bag. Общий допуск>=3fit И>=2check таких групп. Никакой augmentation или подстройки порогов.

## Результаты после wire-deduplication

| Показатель | Fit | Check |
|---|---:|---:|
| Исходные bags / groups |50 /20|14 /7|
| Уникальные wire streams |36|12|
| READY-пары |229439|84518|
| Clean-proxy updates |323540|127964|
| Faulty-proxy updates |**2**|**0**|
| Группы хотя бы с одной faulty-меткой |1|0|
| Квалифицирующиеся группы |**0**|**0**|
| Требуется |3|2|

Без deduplication:64bags,430468READYpairs,533152cleanupdates,те же2faultyupdates. Даже без episode condition остаётся одна fault-bearing fit-группа и ни одной check-группы: вывод не обусловлен только сегментацией эпизодов или deduplication.

Оба примера — rear, bag `30618_2050d396`, group `4a5f0d46327316bb`, один эпизод, output t399.90/399.95с. Rear error .510427577/.698316444м/с; front error .003603939/.034731840м/с. Это метки относительно H42 PROXY_ONLY, не независимое доказательство физического отказа.

На48 уникальных потоках313957READYpairs:225751cleanpair,2rear-faultpair,86921missing/ambiguousteacher,1010intermediate/common,273low-speed. Ещё683771ticks без обеихREADYстрок. В20 из64bags нет принятыхteacher targets. Это не нулевая ошибка и не доказательство отсутствия иных реальных сбоев: здесь исследованы только уже принятые hard gates измерения.

## Проверки

Первый run: **1370779 тактов**, все24native fields/Estimate совпали; future-input ошибок0. Максимальная история12прилимите16/1с. **161canonical +43integrity +60H47 tests PASS** (42прежних+18новых). Full11-file patch применён к pristine,bytesсовпали,320baselinefilesсохранены; те же60tests повторноPASS. CompilationPASS.

Независимый `audit_coverage.py` не импортирует coverage/features/offline_labels и заново вычисляет vectorized nearest targets, все labels/sampleIDs/episodes/groupgates:64bagsPASS,134rawfilesverified.

Повторный полный run того же source/lock:64NPZ побайтово/SHA256 совпали,64bagJSON и3CSV совпали. SUMMARY совпадает кроме timing; repeat exit0. Это проверка повторяемости, не новый подбор и не независимые поездки. Python3.13.5,NumPy2.3.5,threads1. Wall93.44/94.85с относится к offline audit, не runtime latency.

Git clone был недоступен поDNS, interactive streaming отказал до запуска; обычные локальные процессы и GitHub connector позволили выполнить работу. Новый CI/Actions/enabled ROS не запускались. [skip ci] не означает CI PASS. Новых Consensus/Scite запросов после известногоquota stop не было; старый Wolfram worksheet не назван новым экспериментом.

## Решение и ограничения

**INCONCLUSIVE / FOUNDATION_FAILED.** Optimizer calls0; model not trained; candidate/freeze/odometryRMSE/classifierrecall/ROS costs=N/A. Ready_to_merge=false. Пассивное равенство подтверждает неизменность baseline в этом аудите, не преимущество learned reliability. Недостаток natural positive examples в frozen label space запрещает fit по данному PLAN. Не менять .20/.50м/с, не добавлять hard-rejected samples/augmentation и не переносить development в train ради допуска.

Main/чужие ветки/старые отчёты не изменялись; merge/auto-merge/force-push не выполнялись. Сохранять canonical v8.

## Материалы и воспроизведение

[Полный русский отчёт](https://drive.google.com/file/d/1Sp-gyJAhZz4oiLPXflpYqwKoOpGqo7nw/view)
[Компактный пакет с кодом/patch,lock,native receipts,tests,raw bag JSON,CSV,audit и ACTUAL_COMMANDS](https://drive.google.com/file/d/1Y5QCxSFUuzNjbtvli7pM8PTtsilyaMqI/view)
[Все64 per-bag](https://drive.google.com/file/d/1OEfMs_fm_aNOSHWMWuckZ-yAfLJb2FH1/view) · [Все27 per-group](https://drive.google.com/file/d/1-Jw2AVGBYy0rh0qOPFvWBNQFIBOx9ll6/view)
[Полный dependency lock](https://drive.google.com/file/d/1GpnQzrbmom0kyWxY0wf0TeSDr9Mg6Z7B/view)
[32NPZ,часть1](https://drive.google.com/file/d/14QwKAj6UoxNVEbHta_XDGXtKxjenbShi/view) · [32NPZ,часть2](https://drive.google.com/file/d/1yIvdRjIIRLH9cNVIoOcUZQLQXVSfULPy/view)
Это два самостоятельных ZIP; оба вместе содержат все64traces. Hashes и размеры в SUMMARY.json. Общие source/data/teacher не дублируются.

После получения точного checkout и preflight, с новым output:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
python research/R5/H47/coverage.py run \
 --lock /absolute/preflight/DEPENDENCIES.lock.json \
 --data-root /absolute/train-data \
 --teacher-root /absolute/components/teacher/R5_H42_teacher \
 --output /tmp/h47-new-coverage-output \
 --source-sha 435f8be420a6512870a6c9d005bb33f968ac7012
```

Command journal включает transport/native/folds/prepare/tests и independent audit. Это coverage-only driver; train/validation subcommands отсутствуют. Проверять source hashes и роли до IO; не повторять fitting под старым PLAN.
