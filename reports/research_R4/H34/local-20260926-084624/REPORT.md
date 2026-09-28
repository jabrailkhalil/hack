# R4-H34 — REJECTED: согласованная перекалибровка интегратора

**Исследовательский отрицательный результат; не готов к merge.** B — единственный selectable кандидат: аналитический интеграл привода/midpoint resistance с train-only refit. A — диагностический контроль, тот же refit при исходной квадратуре. B0 — новая квадратура без refit; off — точный исходный v8. Выбирать A вместо B запрещено PLAN.

B относительно pinned v8: clean gain **0.065036%**, original fault RMSE **+7.983898%**, clean-distance RMSE **+1.955668%**, full-faulted-bag distance **+5.570140%**. B против refitted A: fault gain лишь **0.297260%** при clean-регрессии **0.068087%**. Ни accuracy-контракт, ни условие преимущества самой квадратуры не пройдены. Validation/final test не открывались, freeze не создавался; после двух fit параметры не менялись.

## Версии и фактически исполненные этапы

- Baseline: `e3b0c9c039d2953fbfcda51231263d38ef9f1024`; tree `eae49a504bc59b5c9b408445150bef32e111956f`.
- Пользовательский ZIP полностью VERIFIED: 301 файл, исходные bytes/paths/executable bits; SHA256 `a8e0bfa033e0a02c460c30b02f34a5c64ece85b05003512941387d3cf1f319a2`.
- PLAN опубликован до H34 измерений: `b70706e20592dfe91450613dac3b4d82ee7d8509`.
- Точные измеренные runtime/driver bytes опубликованы в `a93181b59bdd23a2b116ea9c6a4c3f826c2cb06a`; Git blob SHA пяти driver-файлов и runtime отдельно сверены с локальными.
- Execution ID: `local-20260926-084624`. Foundation начался 26.09.2026 08:46:24 UTC, fit 08:49:05, development 08:53:50.
- Source commit опубликован ПОСЛЕ локальных расчётов, но PLAN ДО них. Это не предварительный validation freeze; его не было. Поздний report commit указан в PUBLICATION.json/PR отдельно.

Численные расчёты выполнялись **локально**, не в Actions. Run36230833147 был только data-export; его success не приёмка алгоритма. Полная история .git локально не создавалась под ложным baseline SHA. Remote commit→tree проверен connector read. Ветка `research/R4-H34` создана от pinned baseline; main/другие ветки/старые отчёты не менялись, merge/auto-merge/force-push не выполнялись.

Baseline — именно GuardedReadoutObserver/champion_v8.yaml/guarded_odometry_node: 20Hz/delay0, gain1/holdoff.5, adaptation_tau.5, wheel_time_compensation0, quarantine1.5, остальные коэффициенты точного YAML. Измеряются возвращаемые Estimate.v/s. В Git core/readout/default сохранены: explicit hooks.patch применяется только в исследовательской копии. Checkout сам не включает B.

## Механизм и предшествующие работы

Прочитаны H08/PR25, R2-H16/PR34 и поздний R3-H22 checkpoint SUMMARY. Их результаты/validation не переизмерялись и не заменяют H34. H08 менял квадратуру без refit; H16/H22 показывали компромисс fault gain против distance/safety.

Для удерживаемого target и x=dt/tau: mean_drive=drive0+(target-drive0)*(1+expm1(-x)/x), end_drive=drive0-expm1(-x)*(target-drive0). При малом x используется ряд x/2−x²/6+x³/24−x⁴/120+x⁵/720. Полушаговый интеграл даёт midpoint для resistance. Target использует начальную v, как H08; clipping/sign guards прежние, это не точное решение всей нелинейной модели.

Core hook выделяет исходное propagation с exact operation-order parity A; readout accessor для B использует реальное effective pre-correction acceleration B. Q/R/Joseph, d adaptation, gates/stop/recovery/quarantine, Timeline, input scheduling и интегрирование дистанции не меняются. H32/command-event-time не реализуется. Только controller/front/rear, O(1) новые скаляры, нет labels/GNSS/IMU/future samples или scientific runtime dependencies. Hook-disabled/legacy + старые параметры воспроизводят полный v8, не приближённую таблицу.

## Train-only foundation и одинаковый fitting

Использован объявленный в PLAN проверенный кеш vehicle-only окон H24: artifact10898348614/run36220067112, ZIP SHA256 `4d1f0473ce166a210446f54affb87ea4845cea9664c1b133c507e57850f58c06`. NPZ/metadata/coverage хеши проверены, прежние access/hash всех64train bags сверены с frozen split. **Нового локального чтения/байтовой перепроверки всех train DB не было**; это разрешённый кеш, а не новые SQL-измерения. Все H34 predictions и fit исполнены заново. Train GNSS не читался.

27 исходных связанных групп:20fitting/7check по фиксированному SHA256. Представлено205окон в24группах:154fitting в18 и51check в6.101warmup tick (5с), затем40command-only ticks (2с), горизонты.5/2с. Реальный observer пересчитывает warmup на каждой theta; будущие wheel targets используются только offline loss. Это псевдоразметка, не ground truth. Роли не пересекались.

Foundation: RMS A0−B0 на .5/2с = **.002095277/.007173153м/с**, 17групп выше .005м/с на2с. Заранее требовались .005м/с, >=3группы, >=30окон. Same-state one-step RMS=.000189409м/с. Foundation PASS. Точный H08 kernel blob `9fa1bbdbc052c9c93fc15426e8c37b4b38e1f61f` воспроизведён на3000комбинациях. Scalar/vector прогнозы совпали на всех205окнах до1e−9, также после fit; начальные максимумы v~1.78e−15м/с,s~2.84e−14м.

Один scipy least_squares/TRF вызов для A и один для B: одинаковые7effective parameters, исходные bounds, initial theta v8, objective, max_nfev80,jac2-point,ftol/xtol/gtol1e−8,x_scale=jac. Без restarts/regularization. Residual делится на.2/.5м/с, robust rho=2*(sqrt(1+r²)−1), group-balanced веса. A/B используют одну функцию residual. A:success,nfev14,njev14,112фактических calls; B:success,17/17/136. Numerical-Jacobian calls учтены отдельно. Все theta/loss calls сохранены.

Порядок theta: force/mass,power/mass,brake/mass,rolling/mass,quadratic/mass,command exponent,actuator tau.

```json
{"A":[1.2617008627926742,7.270823586886211,0.7481579508893332,4.1204659956065557e-25,0.001838972059423594,0.5139186439254485,0.3706390532364205],"B":[1.2715693504680619,7.378253727159427,0.7474904276726128,2.0983164710394956e-36,0.001816127571102726,0.5099747324878252,0.35745811254203674]}
```

Это эффективные параметры, не паспортные масса/силы объекта; rolling у обеих схем достиг нижней границы. Check velocity RMS на2с .533343788→A .457785760/B .457944792м/с, но check-coast **.306509893→.400713991/.401944388м/с**. Coast integral RMS .308952328→.406545641/.407989658м. Per-group signed velocity/integral errors сохранены. Check не использовался для ретюнинга; proxy gain не заменяет development.

## Данные и один неизменный evaluator

Data-only Actions36230833147 скачал checksum-pinned ZIP штатным downloader, распаковал только17development bags. Validation/test не извлечены, SQL exporter не выполнял. Каждый DB SHA256 перепроверен удалённо и локально. Artifact10902149285, SHA256 `418077b219ad6883139c25874ea53c82a60894049528c23764d1c1909b778e85`, expires26.10.2026 08:47:41UTC. Raw DB не коммитились.

Все17development bags/7групп, reference в6группах/19bag-receiver парах; missing=null.56original faults/60reference comparisons. ev.score/replay/match/metrics/distance и v6 aggregation неизменны; только отдельная factory/role-checked read-only loader. На каждом17clean bag независимо вызван official baseline; fingerprint совпал точно. Off state/Estimate сверяются потактово; schedules/masks одинаковы. Receiver не независимая поездка.

| Метрика | v8 | A, refit legacy | B, refit exact |
|---|---:|---:|---:|
|Clean macro RMSE,м/с|.092668142983|.092544864556|.092607875221|
|Original fault-event RMSE,м/с|.237548612056|.257279037317|.256514250784|
|Pooled clean RMSE,м/с|.129305694477|.128899795464|.128929537877|
|Clean scalar distance RMSE,м|5.310295004801|5.404815503409|5.414146723573|

Matched394221у всех, clean/original false stops0/0, original unrecovered4у всех (30639_e4379d7f/rover, все4original faults). Новых individual unrecovered, causality/reset ошибок и coverage loss нет. B изменил221306published-v ticks,6reference-bearing групп: mechanism/coverage PASS.

B0 с исходными коэффициентами:clean .092744389900,fault .238639357678м/с,distance5.313810026084м. Это same-parameter diagnostic, не selectable вариант и не повтор old validation.

B/v8:clean−.065036%,fault+7.983898%,pooled−.290905%,distance+1.955668%. Причины:insufficient_gain,aggregate_regression:fault_rmse,aggregate_regression:distance_rmse,supplemental_regression:full_faulted. Пороги >=2%clean ИЛИ>=5%ORIGINAL fault, <=.5%основные агрегаты, <=1%distance не менялись. Clean per-bag gate пройден.

B/A отдельно:clean+.068087%,fault−.297260%,pooled+.023074%,distance+.172646%; attribution-gate FAIL:insufficient_gain. A не выбирается вместо B.

## Регрессии, signed bias и coast

Clean phase RMSE v8→B:traction .111819538→.112224355; braking .127349439→.126561406; coast .034355074→.034316748м/с. Эти срезы описательные, не новые posthoc veto.

Clean MAE .034933353→.034856928м/с; signed bias .006390677→.007564260; group-macro p95 .090092790→.089455567. Fault+recovery MAE .153796529→.152242306, signed bias **.011170308→.061134217**, group-macro p95 .456670429→.469587641м/с. Group-macro p95 не pooled quantile.

**41/60 original event RMSE хуже уB.** 30618_27e994fc/rover dropout10с:.245154505→1.047558013м/с (+327.305%); master:.244432686→1.033174275 (+322.683%);30639_9c362687/rover:.258670139→.932092685 (+260.340%).

Recovery macro по определённым значениям .724358285→.677483285с, но9локальных восстановлений медленнее.30618_0652866c/master иrover dropout10с:1.256544646→1.756544646с (+.5с). Unrecovered не скрыты средним. Distance30639_c31df386/rover:28.322408035→28.964894355м (+.642486320м). Конкретный причинный вклад d/отдельного коэффициента не доказан абляцией.

## Полный faulted bag и остаточная delta_s

Все56original injections дополнительно воспроизведены от настоящего начала полного bag дляv8/A/B, без переякоривания. Это отдельная диагностика, не замена исходных cropped fault метрик. Full-faulted distance macro **6.269376947→6.607841107/6.618590014м**; B/v8 **+5.570140%** против предобъявленных1%.

Delta_s=s_faulted−s_clean того же алгоритма на последнем tick<=fault_end+10с ивконцеbag; это относительный fault-induced offset, не GNSS-position error.30618_27e994fc dropout10с,t210.1: v8−.118473616м,B+6.275318772м, сохраняется практически до конца.30639_9c362687,t156:v8+.452806009м,B+5.611743853м. Скорость восстановилась, но дистанция не «обнулилась». Full-faulted coverage/recovery без новых failures,4прежних unresolved.

## Safety suites, тесты и стоимость

Прежние low-speed lock3/5с:26events/34reference; event macro .368545673→B .345009840м/с (−6.386137%). Прежние H11 jumps+5м/с,.7/1.2с:28events/30reference;.100632272→.083186418 (−17.336242%). False stops0, сохраняются6low-speed/2common unresolved, новых individual failures нет. Их gain не заменяет original gain.

Доfit синтетика обнаружила унаследованный zero-origin rebound при velocity−.2,command−1,безwheel updates. Sign guard запрещает crossing двух ненулевых противоположных знаков, но не движение от ровно0. Изначальный тест <=0 нарушался такжеbaseline; его ожидание исправлено до реального old_v*new_v>=0, **runtime не исправлялся**. B0 увеличивает positive peak .048387428→.057878972м/с. Post-result неизменённых fitted моделей:A .037000453,B .040971277м/с. Это честно сохранённая диагностическая регрессия B0/B-versus-A, не сертификат safety. Initial failed log/правки/200-tick traces в локальном evidence.

Реально локально:156original tests+43research-integrity PASS доhooks; H34 первый запуск17/19PASS, две правки тестовых ожиданий доtrain (timestamp9.95/199*.05 иsign guard), затем19/19PASS. По19tests с фактическими A/B config PASS; independent pristine reconstruction19PASS; compileall PASS. Наборы пересекаются. Historical kernel3000,off6000ticks, bounded memory/distance12000ticks,small-dt Decimal65digits,causal/future/duplicate/stale/reset/zero-lock/quarantine. Scalar/vector parity после каждогоfit PASS. Аудит сохранённого decision не выполнял новый fit/DBIO/replay.

24offline AB/BA replays, по3цикла B/v8 иB/A,10сwarmup+180с measured, одинаковые collectors/threads1. B/v8 median step12.526847→13.462382мкс **+7.468240%**, replay CPU19.518115→20.477312 **+4.914392%**; wall+4.893273%. Healthy FUSED/SINGLE_WHEEL step+4.958943%,прочие режимы+8.751937%. B/A step+6.738766%,replayCPU+4.445106%. Ranges сохранены, это описательный замер. Process shared high-water167821312байт не RSSROS-ноды/отдельной модели.

**Enabled installed ROS оба clock modes, offline2CPU/500000000bytes, latency/RSS/GetParameters/import hashes: NOT_RUN_AFTER_REJECTION.** Старый/default CI не удостоверяет B. Grid20Hz не wall-clock guarantee. runtime_verified=false,ready_to_merge=false.

## Ограничения, публикация и воспроизведение

Wolfram вернул integral identity0,series/limit; первая JSON-export попыткаFAILED, в повтореPower::infy warning сохранён. Independent Decimal65digits tests выполнены; не заявляется неисполненный mpmath run. Аналитика не доказывает всю switched clipped систему. Consensus/Scite известные quota stops не обходились. Train wheel targets не истина; окна5сwarmup/2сforecast ограничивают модель. Distance scalar reanchored,неXYZ/ENU; scales/relative1D ограниченияbaseline сохранены. Ни historical final-test метрики, ни validation не использованы.

Публикация ОДНОГО verifier-файла через connector была заблокирована инструментом safety-check, повтор/обход не предпринимался. Он остался в исходной карточке и local delivery; остальные runtime/driver опубликованы. Перед prepare.py нужно положить verify_source.py из delivery рядом. Это ограничение публикации, не причина научного отказа. Полный расширенный русский отчёт, raw compact results/per-bag/per-group,fit/residual logs,source receipt/patch,math/probes доступны в пакете текущего ответа; не выдуман Actions accuracy artifact.

В isolated checkout source a93181b..., Python3.13.5/NumPy2.3.5/SciPy1.17.0:

```bash
# overlay из delivery содержит также локальный verifier
cp -R /path/to/delivery/overlay/. /path/to/research-checkout/
cd /path/to/research-checkout
python -m pip install -r requirements-research.txt
python research/R4_H34/prepare.py --baseline-zip /path/to/baseline.zip
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
python -m unittest discover -s research/R4_H34/tests -v
OUT=$(mktemp -d)
python tools/research_R4_H34/foundation.py --train /path/to/delivery/inputs/train --output "$OUT/foundation"
python tools/research_R4_H34/fit.py --train /path/to/delivery/inputs/train --foundation "$OUT/foundation" --output "$OUT/fit"
# Распаковать development-only.zip собственного artifact в dataset/data/
python tools/research_R4_H34/develop.py --fit "$OUT/fit" --output "$OUT/development" --workers 2
python tools/research_R4_H34/cost.py --fit "$OUT/fit" --output "$OUT/cost"
```

Повтор **без refit**: передать сохранённый delivery/evidence/fit в develop.py/cost.py. НовыйOUT обязателен; audit_results.py работает только с сохранёнными результатами. Local full REPORT содержит всеclean bag/receiver значения,а per_bag.csv — такжеoriginal/low-speed/common/full-faulted/phases. Raw DB и гигантские traces в Git не добавлены. Локальному evidence ZIP не приписывается Actions retention; data-only artifact expires26.10.2026.

**REJECTED конкретного B при зарегистрированном одинаковом A/B fit. Основание и coverage достаточны; преимущество по accuracy и квадратуре не подтверждено. Это не опровержение всего семейства интеграторов/перекалибровок.**
