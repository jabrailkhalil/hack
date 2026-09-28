# R4-H32 — REJECTED на development после получения датасета

**Исследовательский отрицательный результат, не готов к merge.** Один прежний `H32_event_time` впервые измерен на полном development после предоставления dataset.zip. Baseline воспроизведён точно; изменение активно; требуемого выигрыша нет и обязательный low-speed допуск нарушен. Причины: `insufficient_gain`, `low_speed:event_regression`. Код, параметры, scorer и PLAN не менялись. Validation/test не открывались. Это локальный запуск, не успешный GitHub Actions run.

## Версии и происхождение

- Baseline: `e3b0c9c039d2953fbfcda51231263d38ef9f1024`; полный tree `eae49a504bc59b5c9b408445150bef32e111956f`.
- **Измеренные алгоритм/factory/driver/tests: `3115b66f4faaf6f2327b4427aff54feb6c69d8d7`.**
- PLAN до реализации и candidate measurements: `abacda82c1856e921a940894a1c8265b249c06e9`.
- Execution: **`local-20260926T092933Z`**, `LOCAL_CONTAINER_NOT_GITHUB_ACTIONS`, exit code 0. Новый GitHub run не создавался.
- Ветка `research/R4-H32`, существующий draft PR #49. Новый scientific ID/вариант/PR не создавался; merge/auto-merge не выполнялись.
- Этот commit добавляет только новые результаты. Старый каталог `36231386474-2` и его NOT_EVALUATED сохранены как история инфраструктурной блокировки. Они не являются терминальным результатом нового измерения.

Заново проверены все 301 файл пользовательского baseline ZIP: paths/bytes/executable bits дают точный pinned tree. ZIP SHA256 `a8e0bfa033e0a02c460c30b02f34a5c64ece85b05003512941387d3cf1f319a2`. Семь исполняемых H32 файлов и PLAN в локальном пакете совпадают с Git blob SHA исходников 3115. Ancillary docs и форматирование BASELINE.json местами отличаются от remote tree; полный checkout/history кандидата не заявляется. Полный baseline и 15 protected source hashes неизменны до/после replay. EXECUTION_BINDING.json в evidence раскрывает пути/хеши. Legacy переменная GITHUB_SHA использована только для source provenance; GITHUB_RUN_ID не задан.

## Данные, baseline и измеритель

Пользовательский `dataset(2).zip`: 256294592 байта; точный organizer SHA256 **`d0b2483e13990edb8219b0d7bbcafc7ed001cce549a4d3af467069b2472e7d52`**. Штатный stage_data.py извлёк только 17 development DB; каждый bag проверен по frozen split. Validation/test DB не извлекались и не декодировались. Общий сжатый data.zip включает другие роли, но их measurement payloads не открывались. Предыдущая train foundation не повторялась; fitting отсутствует.

Baseline — настоящий GuardedReadoutObserver/champion_v8.yaml: gain=1, holdoff=.5, adaptation_tau=.5, wheel_time_compensation=0, quarantine=1.5; 20 Hz/delay=0. Измеряются опубликованные Estimate.v/s. Candidate — factory.CommandEventObserver, enabled=True, CommandEventTimeline.

Неизменные evaluate.score/replay/match/metrics/distance, original fault placement и research_guarded.aggregate. Идентичны arrival order, inputs, injections, timestamps, masks. Независимый canonical driver подтвердил clean baseline metrics/counters: 246 top-level полей. Агрегированный baseline fingerprint по clean/fault/pooled/distance и 394221 samples воспроизведён точно, max delta=0.0.

| Suite | Сценарии | Reference bag/receiver comparisons | Группы с reference |
|---|---:|---:|---:|
| Clean |17|19|6|
| Original faults |56|60|5|
| Low-speed locks |26|34|6|
| Common-mode |28|30|5|
| Transition + dropout 1 s, diagnostic |38|45|5|
| Полные bags с original faults |56|60|5|

Всего 221 paired case; семь исходных development-групп. 15 missing clean receiver-пар сохранены как null. Два receivers одной поездки не считаются независимыми группами. Access journals: 18 успешных загрузок, 17 bags плюс первая запись для cost.

## Изменение алгоритма

Кусочно-постоянная propagation только drive_a по уже поступившим controller source timestamps внутри неопубликованного шага. Все targets используют прежнюю внешнюю v. Euler v, endpoint a_model, сопротивление, Q/R, disturbance, gates, readout, zero-lock и quarantine сохранены. Нет L/tau fitting, H08 velocity integration, H17 dead time, H30 wheel rewind, GNSS/IMU или fault oracle в runtime.

Factory накладывает трёхстрочный hook на приватную копию core, SHA256 `cbb99a186c32e7e2772b6c72285abcc238cd8e71d4022abc3220d516183a1c59`. Canonical src/default не меняется. Checkout/YAML сами по себе H32 не включают: нужны factory.candidate(config, enabled=True) и CommandEventTimeline. core_hook.patch отдельно к рабочей ноде не применять.

Очередь ограничена 31 pending + 1 predecessor и 0.5 s; stale/loss/history gap дают явный legacy fallback. Constant-command arithmetic сохранена. Правограничная новая команда действует 0 времени в прошедшем шаге. Поздние команды не меняют опубликованное прошлое.

## Результаты development

Положительная delta ошибки означает ухудшение; скорость в м/с, дистанция в м.

| Метрика | Baseline | H32 | Delta, % |
|---|---:|---:|---:|
| Clean group-macro RMSE |0.09266814298282507|0.09270419920529231|**+0.03890897**|
| Original fault-event group-macro RMSE |0.2375486120563008|0.2364976802392506|**−0.44240705**|
| Pooled clean RMSE |0.1293056944774334|0.12930721850985144|+0.00117863|
| Clean scalar-span distance RMSE |5.310295004801444|5.308221262650749|−0.03905135|
| Full-faulted-bag scalar-span distance RMSE |6.269376947281123|6.281890128750183|+0.19959211|
| Low-speed event RMSE |0.3685456733063761|0.372882745940232|**+1.17680737**|
| Common-mode event RMSE |0.10063227230134311|0.10016120672992346|−0.46810587|
| Diagnostic transition/dropout event RMSE |0.11966840438354671|0.1207759261987725|+0.92549226|

Минимум 2% clean ИЛИ 5% original fault gain — FAIL. Low-speed regression <=0.5% — FAIL. Остальные primary <=0.5%, clean/full-faulted distance <=1%, clean per-bag и coverage/false-stop/individual-unrecovered guards — PASS. Пороги после измерений не менялись; diagnostic gain не подменяет original admission.

Matched clean points 394221→394221; false stops 0→0 во всех suites, включая full-bag. Unrecovered original 4→4, low-speed 6→6, common-mode 2→2, diagnostic 3→3; новых индивидуальных случаев нет. Causal errors/unexpected resets 0. Original mean confirmed recovery 0.822233742857→0.828483742857 s, +0.00625 s; агрегация по доступным receiver comparisons, не иной исторический group-macro.

Clean MAE 0.034933352905→0.034930535504; signed bias 0.006390677420→0.006383339967; p95 0.090092790092→0.090082587742 м/с. Original fault+recovery-window MAE 0.153796529331→0.153748638795; bias 0.011170307852→0.013919807834; p95 0.456670428618→0.457138299408 м/с. Transition-window RMSE 0.069455255261→0.069420532117 м/с (около −0.0500%), но следующие за переходом dropout в среднем хуже.

## Активация и существенные регрессии

На clean 19957 material drive steps, 213287 из 318865 опубликованных velocities изменились >1e-9 м/с; 319835 checked ticks включают WAITING. Все 7 групп имеют >=10 material steps. Максимум памяти — 13 команд при лимите 32. Coverage достаточен.

Clean RMSE: 10 лучше / 7 хуже / 2 равны. Original event: 29 лучше / 23 хуже / 8 равны. Low-speed: 18 лучше / 16 хуже; common-mode: 16 лучше / 10 хуже / 4 равны. Большинство выигравших пар не отменяет групповой low-speed regression.

| Случай | Baseline→H32 | Регрессия |
|---|---|---|
| Clean 30639_0ab96c59/master |0.018981006→0.019216348 м/с|+1.2399%, ниже clean per-bag gate|
| Original dropout 10 s, 30639_dce52be4/master |0.227959065→0.260218954 м/с|**+14.1516%**|
| Low-speed lock 5 s, 30618_0652866c/master |0.176262236→0.211481117 м/с|**+19.9810%**|
| Diagnostic dropout 1 s, 30618_88548b02/rover |0.111480236→0.142716517 м/с|**+28.0196%**|
| Common-mode 1.2 s, 30618_27e994fc/master |0.048959572→0.049766225 м/с|+1.6476%|
| Full-faulted distance 30639_c31df386/rover, dropout 10 s |24.093163480→24.715948014 м|**+0.622784534 м (+2.5849%)**|

Original recovery медленнее в двух receiver cases 30618_0652866c/dropout10s: 1.256544646→1.556544646 s (+0.30 s). Три быстрее, 51 равен, четыре missing. Low-speed: один медленнее на 0.15 s; diagnostic: два на 0.05 s; все 28 доступных common-mode recovery равны.

Original fault macro по группам: 70bb14d1c90f301f 0.245582235→0.233164342; 711abb923942f9fe 0.125038907→0.124969416; 8269991eafa82c45 0.419757752→0.422021821; a0c46036cc19092a 0.230681884→0.234702734; a8a4c11ebcc1dde2 0.166682281→0.167630088. **Три из пяти групп ухудшились**, несмотря на aggregate gain.

Для полного 30639_c31df386/dropout10s остаточная s_H32−s_baseline = +0.818398561 м на end+10s и +0.784119291 м в конце. Recovery её не стирает. Это разность двух оценок, не XYZ ground truth и не изолированный эффект только fault: траектории различались до отказа. Соответствующая reference scalar-span регрессия приведена отдельно.

Clean counters: 65 late commands; 821 horizon-loss records; 22 fallback_lost_history; 1025 fallback_stale_current; 10 missing_predecessor; overflow_loss=0. Эти явно учитываемые fallback ограничивают покрытие event-time пути. История не продлевает timeout.

## Проверки и вычислительная стоимость

В текущей сессии 156 canonical unit + 43 research-integrity + 32 H32 tests PASS; compileall PASS. Patch apply --check, roundtrip bytes и повтор 32 тестов PASS. Feature-off exact на 1687746 ticks всех 221 cases. Read-only audit без нового replay воспроизвёл решение и проверил source hashes/roles/schedule/finite arrays: 221 NPZ и 1683414 опубликованных outputs на модель. Разница с checked ticks — WAITING. Независимый baseline fingerprint совпал точно.

Python 3.13.5, NumPy 2.3.5, SciPy 1.17.0. Один development bag, 10 s warmup + 60 s, warmup replay перед повторами, 6 AB/BA пар, threads=1, одинаковые collectors, без state-audit внутри timed path.

| Измерение | Median baseline | Median H32 | Медиана парного overhead |
|---|---:|---:|---:|
| Step CPU, мкс/output |12.485178750|16.100057917|**+28.5360%**|
| Replay CPU, s |0.025943616|0.032415932|**+23.9033%**|
| Replay wall, s |0.0260184395|0.0324171720|+23.9027%|

Отношения отдельных медиан составляют +28.9534%, +24.9476%, +24.5931% соответственно; они не смешаны с медианой парных процентов. Step исключает первые 10 s, replay измеряет весь 70 s отрезок. Output hash каждого профиля одинаков во всех повторах. RSS high-water=170778624 bytes всего research process, не установленной ноды. Короткий offline microbenchmark не доказывает overhead на любой машине.

**Enabled installed ROS в обоих clocks, 2 CPU / 500000000 bytes: NOT_RUN_AFTER_REJECTION.** Старые Actions failures не стали success; нового Actions запуска не было. Report-only commit не является CI/runtime-сертификацией.

## Воспроизведение

```bash
git checkout 3115b66f4faaf6f2327b4427aff54feb6c69d8d7
python -m pip install -r requirements-research.txt
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
PYTHONPATH=src/reserve_odometry python -m unittest discover -s tests -v
python -m unittest discover -s research/tests -v
python research/R4/H32/test_h32.py
python -m compileall -q src/reserve_odometry research/R4/H32
mkdir -p dataset
ln -s /absolute/path/to/dataset.zip dataset/dataset.zip
python research/R4/H32/stage_data.py --role development
# Source provenance only; this does not represent GitHub Actions execution.
export GITHUB_SHA=3115b66f4faaf6f2327b4427aff54feb6c69d8d7
unset GITHUB_RUN_ID GITHUB_RUN_ATTEMPT
python research/R4/H32/run.py --output /tmp/H32-development-fresh --workers 2
```

Output должен быть новым. Без Git: verifier полного baseline ZIP, отдельная копия и полный candidate.patch. Локальный git init не создаёт remote ancestry.

## Evidence и ограничения

В Git — этот отчёт, SUMMARY, aggregate и clean-per-bag таблица. Полные per_bag.csv (все suites/MAE/bias/p95/recovery), bag JSON, results.json, COST, 221 NPZ, логи, source/data manifests и read-only audit находятся в приложенном к беседе **R4_H32_development_raw.zip**, 54977857 bytes, SHA256 **04841df51126fc32ffe1b1da9570f7afd474becaf4718263622c9ec6d89a461a**. Он также входит в итоговый пакет. Raw DB/dataset не опубликованы. Большой архив не загружен как GitHub Actions artifact; внешняя retention-гарантия не заявляется. Полный воспроизводимый код уже в source3115; source ZIP/patch/verifier сохранены в итоговом пакете.

Wolfram worksheet/output и ограничения из предыдущего этапа сохранены, не запрашивались заново. Ideal actuator algebra не доказывает switched observer stability. Source stamp как физическое время действия команды остаётся приближением; прежняя калибровка не переобучалась. Причинный вклад state channels в регрессии не изолирован; post-hoc объяснение не выдаётся за ablation.

Результат относится к development на связанных исходных группах; это не independent validation/final test. Scalar reanchored span distance не XYZ/ENU/terminal ground truth. **Проверенный H32_event_time отвергнут по неизменному R4 admission. Всё семейство event-time моделей этим не опровергнуто.**
