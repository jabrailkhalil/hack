# R6-H57 — REJECTED на общем train-check

**Исследование выполнено; параметрический кандидат C1 отклонён, не готов к merge.** Это не отсутствие данных и не остановка только на интерфейсе. Проверены исходные зависимости, перечислены реальные окна, опубликованы selection freeze и отдельный freeze обеих моделей, выполнены ровно два fit и один общий check. После отрицательного check development/validation/test не запускались.

Это компактная GitHub-сводка. [Полный русский отчёт](https://drive.google.com/file/d/1gLk1v8xA0mzpA2O6YRxcBT_BrnoGbaX9/view), [полная SUMMARY](https://drive.google.com/file/d/1wATpMvh0EaUzIGrVHJ7QMRiMzVipHeDs/view), [workspace](https://drive.google.com/drive/folders/1P5jA4Y9ySrZg-P7osoqel07svGf3YRU7).

## Механизм и freeze

Baseline b2783206000091ab11a1c11ac3ff79082188a4fb / tree973d50d288e050325ee1c71a90fa8d81f2a099af. Полный champion_v8 и GuardedReadoutObserver, 20Hz/delay0. Точный H44 source0ca93500d4d305c21c998bfd8d2a2e78c98b90ad.

C0 использует первые две допустимые train-точки каждой bag/phase. C1 использует две временные квантили1/3,2/3. Изменён только выбор train anchors. H42, F/P/B, loss/scales/prior,5s warmup, TRF/bounds, wire representatives, runtime/scorer не менялись. Новые guards, H52/H53/H54, d-confidence или recovery logic не добавлялись.

PLAN c846a9f65e80309dd304d16beb55eacb3679f6d3 опубликован до F0. Pre-data уточнение n=3:59e435c030b8d5680ed0bc2d5c106d0876208c7e. Измеренный numerical source d4c8d77534b576075223a867104f421909d0176d. Selection freeze fdda3a1e04301768f95a25c19c8d9222e14fbde2 до обоих fit. Freeze обеих моделей1724ff3cdd2f46a18cfbfcdf2a5505f03e317903 до первого check prediction. Поздняя публикация CANDIDATE_FIT.json сохраняет точные ранее frozen bytes, не является переобучением.

## Данные и основание

Source320файлов, dataset/64trainDB, teacher85, atlas53, H44evidence216файлов и folds bridge64bags/27groups проверены. Новый consumer dependency lock SHA256 d75a16d0d3bfea6236a890b50321543004365e54553ed6b1846bb82d2a21f497 создан до SQL. Teacher только offline PROXY_ONLY; H43errors не ранжируют anchors. Только originaltrain:50fit/14checkbags и20/7groups.

На1370779тактах перечислено3245eligibleanchors, из них2703wire-representative. C0metadata/samples/targets точно воспроизвели H44. Оба fit получают141окно/15групп и одинаковые balanced weights. C1 заменяет127IDs (90.070922%). Материально изменены13групп при требовании3. Тяга/торможение присутствуют в14fit/5checkгруппах. Foundation PASS.

| Часть fit-поездки | C0 | C1 |
|---|---:|---:|
| Первая треть |134|40|
| Вторая треть |5|74|
| Последняя треть |2|27|

Временной перекос есть, но это не доказывает, что first-two ухудшает калибровку. Все27групп сохранены, неподдержанные группы=N/A. Check одинаковый:793окна/9representativebags/5групп, выбранный до fitting. Legacy first-two54окна — только дополнительная диагностика.

## Два реальных fit

| Величина | C0 | C1 |
|---|---:|---:|
| F/m, м/с² |1.288533445119809|1.101147668484754|
| P/m, Вт/кг |10.728192862270857|10.603850320978552|
| B/m, м/с² |.8221195064444401|.6060941707565445|
| nfev / njev |15 /7|29 /18|
| Actual residual calls |36|83|

Оба ftol success; total119calls при лимите1000 и max_nfev80/fit. Рестартов нет. C0 заново точно воспроизвёл historical H44G config/cost/calls. Сходимость ftol не доказывает глобальный оптимум. Training costs разных выборок не используются как общий gain.

## Общий check: основной отрицательный результат

Primary — одинаковый group/bag/window-balanced RMS шести нормированных ошибок скорости/интеграла на .5/2/5s, без prior. Положительная Δ означает ухудшение.

| Метрика | C0 | C1 | Δ |
|---|---:|---:|---:|
| Normalized combined RMS |.46053607109003086|.495825331007144|+7.662648%|
| Скорость RMS, м/с |.46578992681862125|.520859399275698|+11.822813%|
| Integral RMS, м |1.0149225362673022|1.0991623045851568|+8.300118%|

Integral здесь — до5sпрогноза, **не full-faulted-bag distance**. Это train-check, **не clean/original-fault benchmark и не officialXYZ**. Все793окна оценены парно.

| Check group | Окна | Primary Δ | Velocity Δ | Integral Δ |
|---|---:|---:|---:|---:|
|0d4506540f0e7621|98|+10.386268%|+12.498064%|+10.492988%|
|6090ff2c1bc8dee6|159|+6.330418%|+9.829402%|+7.345335%|
|bc1e4cbe924a90ce|186|+4.136944%|+10.233722%|+5.309121%|
|dc785decbed3d7ce|177|+14.285386%|+18.696878%|+12.841958%|
|eeabf7d118bbcdac|173|+8.557265%|+11.712378%|+9.624219%|

Улучшений0/5; leave-one-group-outрегрессия+6.936507…+9.316712%. Primary хуже во всех фазах: тяга+11.994374%, торможение+8.056280%, выбег+2.428179%; и во всех временных третях:+1.900110/+9.681360/+9.658029%. Legacy54окна хуже агрегатно на1.692271%, несмотря на некоторые локальные улучшения. Они не подменяют общий check.

Зарегистрированные gates нарушены: нет2%gain, скоростной/интегральный aggregate выше+.5%, многочисленные group regressions>5%, ни двух улучшившихся групп, ни LOOgain. Поэтому C1 REJECTED и далее не допускается.

## Проверки и реальные ограничения

161canonical+43integrity+27H57unit PASS. Independent Fraction selection/weight audit PASS. Независимый пересчёт сохранённых прогнозов без импорта scorer:960числовых значений/64секции, maxabs5.50e-15. Патч применён к pristine,12overlayфайлов совпали,320baselineфайлов/режимов сохранены;27tests повторноPASS. Frozen Config loading на синтетике точно повторил101прогнозную точку C0/C1, не installedROS.

Первый baseline test invocation имел неверный PYTHONPATH, затем исправлено окружение. До F0 тест обнаружил n=3quantilecollision, устранённую опубликованным уточнением без данных. Первые два F0 завершились после полного64bagreplay с JSONnp.int64ошибками (receipt, затем console); третий serialization-onlywrapper завершилсяexit0. Все15measurement/selectionфайлов идентичны; все логи/partialreceipts сохранены. Fitting/checkcode и scientific rule после результатов не менялись.

Новый CI/Actions, development, validation, test, installedROS, latency/RSS **NOT_RUN**. ContractL относительно canonicalv8 **NOT_EVALUATED**. Нельзя заявлять отсутствие safety/full-distance регрессий. Frozen unsigned H42teacher не независимая истина; соседниеокна коррелированы. Это не доказательство оптимальности первых двух окон вообще.

## Артефакты и повторение

[Evidence ZIP](https://drive.google.com/file/d/110PNX90r_jitOa79M2uJ2zcCdbAjITX2/view):1633426B,SHA256 f8644c6ab5a1c2bf573a5e25e40e9cbbf7d5170d92bd30905647480404197b84.94entries,rawcheckpredictions/CSV/receipts/logs/sourceoverlay/patch/independentaudit/restore script. Архив реально восстановлен в новую папку,960значений проверены повторно без новогоfit/predictor.

[Selection ZIP](https://drive.google.com/file/d/14l6BrSkoQGDm1oiNqkn46VsNnITZASH2/view):4454504B,SHA256 7ef801f5a8ef2f4cf78a3a816f1615ad9906efe082ea5b8ddf13efa09d026da0; exactELIGIBLE/FIRST_TWO/STRATIFIED/CHECK_GRID иarrays.

[Fit ZIP](https://drive.google.com/file/d/1QaQZTOoS0jr1CVOfRbNcJGzAygEdvY1t/view):9574B,SHA256 38a4e6df99f2f1014a3082ff0fbc986bf8a65c84d1b005b771a2aa508133c388;CONTROL_FIT/CANDIDATE_FIT/fullconfigs и все residualcalls.

[Все check sections](https://drive.google.com/file/d/1BvBz40aXriCi-LjS19Cw7pHwis5J-Bxu/view) · [Все27групп](https://drive.google.com/file/d/1LSvs32UT0-HoXBPSHrDGzbZ-saUH-9lV/view) · [Research patch](https://drive.google.com/file/d/1KIFFHaFPparf5103SnypXSCCQGmNerSn/view) · [Candidate parameter patch](https://drive.google.com/file/d/1r_WvKBKonhpdvcbNDina-uBuBWmgNRFr/view).

Полные команды вREPORT/README_REPRODUCE иACTUAL_COMMANDS. Краткий repeat сохранённогоcheck без fit:

```bash
python research/R6/H57/driver.py check \
 --selection /restored/h57/F0-verified \
 --c0 /restored/h57/fit-C0/CONTROL_FIT.json \
 --c1 /restored/h57/fit-C1/CANDIDATE_FIT.json \
 --freeze /restored/h57/receipts/FIT_FREEZE.json \
 --freeze-commit 1724ff3cdd2f46a18cfbfcdf2a5505f03e317903 \
 --output /tmp/new-h57-check
```

Использовать точный source/два frozen checkpoints, новыеoutputкаталоги. Для полногоdatareplay сначалаnativepreflightи новый consumerlock с правильнымиpaths; не переписывать immutablelock. Default не переключён. **Сохранить canonicalv8, H57 не продвигать.**
