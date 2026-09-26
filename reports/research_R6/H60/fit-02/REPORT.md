# R6-H60 — FOUNDATION_FAILED / INCONCLUSIVE

Исследование завершено на foundation. Recovery contribution есть в 18 исходных train-fit группах, но ни один из семи preregistered causal predictors не прошёл совместный критерий |rho| >=0.30 и group-LOO MSE gain >=5%. Runtime-кандидат не создавался; ready_to_merge=false. Это не доказательство отсутствия любых нелинейных или многомерных recovery mechanisms.

## Версии и preflight
Baseline b2783206000091ab11a1c11ac3ff79082188a4fb, tree 973d50d288e050325ee1c71a90fa8d81f2a099af. Полный GuardedReadoutObserver/champion_v8.yaml. Ветка research/R6-H60.
PLAN опубликован ДО новых измерений: 200225d3c369308c1b6afcc93ed7b7e932957d24.
Диагностический код: ee2dfc1fcd8ee08cb0e288a9186648b6922e0403. Это не candidate SHA. Candidate/freeze/PR — N/A.
Новый DEPENDENCIES.lock SHA256 3500bd030830e5bc505f96e87004fc236fa243c1ef2063982893f2297af8da40 создан до нового SQL. Проверены 320 source files/tree, dataset hash, 50 train-fit DB, H42 85 payload files, H43 53, actual folds bridge 64 records/27groups. FD2 export 304524852 bytes, SHA256 2ecda6c68a31c921fe7dc6bda1fcc02d6d39264629e87772903b98100b95f08a; 544 manifest files verified. Это полный опубликованный export scope, а не все исторические raw traces FD2.

## Реальные измерения
36 wire-представителей из20 fit groups; 728978 clean initialized ticks. Всего3761эпизод:3760инъекций (3008dropout,376bias,188drift,188lock) и1natural. Четыре короткие записи не дали anchors и сохранены вcoverage. 18групп имеютэпизоды и>=2 supportinganchors сabs post-trust10s integral>=.05m.
3587полных10s после firsttrusted;171без diagnosticfirsttrust;3снеполным10sпослемаркера. 171НЕ означает171officialunrecovered. Natural исключён изregression: n3586, дляmodelresidual3570.
Два полных replay fit-01/fit-02 дали точно одинаковые episode metrics. Второй усилил диагностику gain до stopreset и exactTimeline rejoin; после стабильной сортировки group/bag/event_id ассоциации совпали точно. Ранее completion-order roundoffrho <=6e-17 не менял вывод. Параметров кандидата нет.

## Ассоциации
Target — counterfactual integral faulted-minus-clean published velocity за10s после firstfullytrustedpair, не officialXYZ. Доверие:>=.5s continuoushealthy и>=3newFUSEDpairs, markerнаnewupdate. Это доверие gates, не независимая истина. Runtimeinstrumentation толькоcontroller/front/rear; H42magnitudeproxy исключительно во внешней диагностике.

| Predictor | group-weighted rho | group-LOO MSE gain,% |
|---|---:|---:|
| innovation | -0.2359614195 | -0.0132944624 |
| d | 0.1027341350 | -1.8036025549 |
| drive_a | -0.2253411898 | 0.0104005280 |
| model_residual | 0.1410068588 | -0.0193842576 |
| P | -0.0483906055 | 0.0298548894 |
| gain | -0.0909575942 | 0.0905597120 |
| published-minus-inner v | -0.1650698982 | 0.0441900219 |

P/gain используютabs target, остальныеsigned. Один predictor наridge model, train-foldstandardization, penalty1e-3; 126LOOfolds, equal-groupheldoutMSE, interceptcontrol. Sign stability100% у всех; все7провалилиjointcriterion. Дляgain MSE2.610540514 ->2.608176416m²; это НЕ odometry accuracygain. Сохранены всеphase/group/bagrows и18group-omissiondiagnostics; невыбиралосьудачноеисключениегруппы.

## Фазы и FD2
Сохранены заданные6фаз отfaultend иfirsttrust. Отдельно10frozenclasses, включая7ранееCONFIRMED; это train-fit descriptive, не новыйcheck. Дляdriftboth10/coast meanabsolute posttrust10integral=1.860251m; driftboth10/traction/positiveaccel=.416960m; biasboth5/traction/positiveaccel=.186420m; dropoutboth15/braking/negativeaccel=.009219m.
Глобальные group-macroabs значения .748679m отfaultend и .159773m отtrust относятся кРАЗНЫМокнам: ихотношение не recoverypercentage. Исторические72.47/27.53 относятся кузкомуrealFD1slice, не универсальнойsyntheticдоле.

## Экстремумы и проверки
Полным неизменным FD1replay дополнительно воспроизведены train-fit terminalcounterfactuals:30618_87afe526/event33d30b67349f3ff03822=-48171.61991355505m;30618_095a115b/eventfd7a1779c8717bb9ecd7=33094.406017625144m. Full-vs-foundationterminaldifference0.0. ДлительнаяMODEL_ONLYтраекторияbaseline послеbiasинъекции, не H60регрессия/officialXYZ/единственный30639checkcaseA0. Полныетрассысохранены. Локальное10sокно не гарантирует отсутствие позднего срыва.
Максимальный defect delta_s-integral(delta_v)=4.2709871195e-9m <1e-6. s/backfill/resetкоррекциянепроизводилась.
LOCAL:161canonicalunit,43researchintegrity,22H60testsPASS; compileallPASS. Все36instrumentedcleanoutputs/features/modes/countersexact. Шесть independentfullreplaychecksнапервых3bags и2extremechecks;8PASS. Prefixcausality,stale/future/duplicate,onegoodthenbad,alternating,commonbias,low/nearstop,single/skewedreturn,reverse/reset/NaN/boundedstate10000steps. Offlineprefixcache/rejoin не runtime.
Wolfram:Josephidentity0,gainboundsTrue,convexboundTrue,trapezoiddifference0,equalvelocityretains s0-z0. Первый JSONexportзапросfailed, исправленныйserializationуспешен; worksheet/output сохранены. Не доказательство нелинейнойустойчивости.
Shortexecution-smoke был прерванtimeout, неPASS. Collectorimport/snapshotalias/диагностическиепроверкиисправлялись; completedpassesотделены. Freshbootstrap заново проверил50fitDB/36wires и22tests, без новогоcandidate.

## Что не выполнялось
Ниодной enabledcandidateevaluation, выбораreconciliationfamily, candidatefreeze, train-check/development/validation/finaltest, officialpairedaccuracy, ActionsCI, installedenabledROS/latency/RSS/ABBAcandidatecost. ЗначенияN/A, не0. TRAIN_CHECK_CONFIRMATION.csv=NOT_RUN_FOUNDATION_FAILED; DEVELOPMENT.csvне создавался. candidate.patch отсутствует: переданы research.patch (diagnostic-only) и candidate.patch.NA.md. По заданию PR допускается толькопослеgates; поэтомунеоткрыт. Main/чужиеbranches/reports/merge/auto-merge/force-pushне тронуты.

## Полная поставка
Этот GitHub файл — краткая запись результата. Полный REPORT, REPRODUCE, lock, source/patch, native verification receipts, всеJSON/CSV/логи двухcompletedpasses, FD2classmapping и rawNPZтрассы второгоpass находятся в workspace:
https://drive.google.com/drive/folders/1Zvm7mXnqWCn34QZXxgVkAb8JiZfKjqij

Исследовательский пакет и отдельныйrawtraceZIP сохраняют per-file hashes. Исходные DB/teacher находятся толькоcanonicalstorage. Кодосновногоизмерениявcommit выше; deliveryhelpers публикуются впакете отдельно, невыдаютсязаruntimecandidate. Репликация требуетstandaloneраскладкиFD1/FD2 по REPRODUCE, анепростого запускаизnestedrepo path. Итог INCONCLUSIVE: явление есть, но выбранноеоснование дляодного минимальногомеханизма не подтверждено.
