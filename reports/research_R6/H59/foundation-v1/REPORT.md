# R6-H59 — FOUNDATION_FAILED

Проверка основания завершена на FD2 train-fit. Покрытие достаточно, но одна зарегистрированная локальная модель residual и экспонента забывания tau=2 с не прошли перенос между группами. Runtime-кандидат, candidate.patch, freeze и PR отсутствуют. Train-check, development, validation и final/test не открывались. Не менять main и не merge.

## Идентичность

Baseline b2783206000091ab11a1c11ac3ff79082188a4fb; полный tree973d50d288e050325ee1c71a90fa8d81f2a099af; 320 source файлов проверены. Canonical GuardedReadoutObserver, полный champion_v8.yaml,20Hz/delay0. Измерены возвращаемые Estimate.v/s. PLAN d4c8c7e46ac2874fa34de9387993c67c0218ec77 опубликован до train measurement IO; файл research/R6/H59/R6-H59_PLAN.md. Ветка research/R6-H59. Shared CURRENT STATE ещё пишет R5; новая явная карточка H59 задаёт R6 с тем же baseline.

Source ZIP SHA256 4823fbdbbb979d7b561841e2831e68f2f7d9d8ec0d14e970f09a38cd51dff4c4; dataset d0b2483e13990edb8219b0d7bbcafc7ed001cce549a4d3af467069b2472e7d52. Teacher/atlas manifests проверены по85/53 payload files и всем64 назначениям folds. FD2 archive 304524852bytes, SHA256 2ecda6c68a31c921fe7dc6bda1fcc02d6d39264629e87772903b98100b95f08a,12 частей/544manifested files; FD1toolkit совпал по12producer pins. Новый DEPENDENCIES.lock до SQL. Только36точных FD2fit representatives измерены. Проверка байтов check arrays не является их декодированием.

## Диагностика, не runtime propagation

Реализован отдельный causal computed-but-unused monitor: OLS наклон wheel velocity минус интеграл предассимиляционных model increments за последнюю1с;≥6unique pairs/span≥.6с; только FUSED/ACCEPTED/valid braking, согласование≤.2м/с,|v|>.5. Наклоны колёс≤3м/с² и их расхождение≤.25. Residual clip±.3м/с²; два буфера по16; forgetting exp(-age/2). Bad evidence/reset/stop/выход из braking очищают поддержку. Monitor не меняет F/P/B,d,Q/R,readout,gates,Timeline или s. GNSS/teacher/labels не входят в API.

36bags/20sourcegroups,1411452vehicle events,728978initialized outputs. Exact state+Estimate parity с независимым v8 на731365step invocations, включая waiting. Новыйcollector дополнительно совпал с исходнымFD1collector на36bags.

Исходные anchors(clean,6,15), только braking;190distinct anchors. По одному15сboth-wheel dropout с полным baseline replay на anchor. Все schedules/prefault outputs совпали;190signed integral identities, maxerror2.3562e-11м. Никакого candidate replay не было.

На h=.5/1/2/5с: y=(z_clean(h)-z_clean(pre))-(v_fault(h)-v_fault(pre)), где z — свежие согласованные SIGNED wheels. H42 unsignedproxy используется отдельно для диагностики, не как runtime/подмена z. Linear template x — интеграл frozen prefault residual с tau2, gated только stale/missing обоих wheels, valid braking и|inner v|>.5. Это foundation-probe, не точный нелинейный rollout нового observer.

108пригодных anchors/18groups, каждая≥2anchors.80безtrustedstate и2безfuturewheel target сохранены какexclusions; все190records включены вevidence.36inventorybags/20groups не сокращались по ошибке.30618:94пригодных/15groups;30639:14/3.

18leave-one-group-out closed-form fits одного no-interceptbeta,clip[0,1].Primaryh=2/5 equally weighted, затем anchors/bag,bags/group,groups; x,y делятсянаh. Нетtau/feature/objective sweep. ПослеFAIL fullfitbeta не вычислялся.

## Решение по зарегистрированным gates

| Gate | Требование | Факт |
|---|---|---|
|Coverage|≥30anchors/≥3groups с≥2anchors|108/18 — PASS|
|OOF normalized MSE gain|≥5%|**regression4.107842% — FAIL**|
|Groups improve|≥12из18|**8из18 — FAIL**|
|Every post-OOF leave-one-group-out|positive gain|17из18сregression — FAIL|
|Sign coverage|≥10anchors/≥3groups|12/8 — PASS|
|Sign agreement приabs(r),abs(y2/2)≥.05|≥60%|62.5% — PASS|
|Every training-fold unconstrainedbeta|positive|один−.879300 — FAIL|

OOF MSE **.02639582774181823→.02748012669721536 (м/с²)²**. Это НЕ canonical fault RMSE кандидата/official XYZ. В17foldsbeta>1clip1; безgroup5c1be3e9a2189121betaотрицательныйclip0. Group regressions:0448e10aab8a0e05+41.56%,bc403256f12f9710+29.79%,de891506667c23f9+32.46%. Исключениеbc403...даётлишь+.1710%gain; не использовано для сменыprimarysubset.

## Persistence, slices и контрпример

Pooled clean residual lag correlations на.5/1/2/5с: .7044/.5927/.5751/.3741; доступно97/85/68/51пар. Nonzero sign agreement62.89/55.29/47.06/49.02%. Это conditional-on-support описательная корреляция, не независимые испытания; clean d продолжает адаптироваться.

FD2-S-7f3c14c52b(negative acceleration,braking,bothdropout15):99anchors/17groups, MSE+2.4108%.2–8м/с:67/17,MSE+.2929%.30618/30639:+4.1896/+1.8155%. Brakingage1–2с gain2.92%,age2–4regression16.84%,age≥4regression5.85%. Slice не заменяетprimarygate. B0/B1вFD2 имеютduration10; здесь15с, поэтому контекстB1помеченNOT_FD2_B1, не заявляется повтор исходного10с класса.

Case497125084804ed3b373f/bag30618_4d487b0d: prefault residual+.274536м/с²; y2−1.035801,y5−3.974294м/с, но прогноз x2+.288774,x5+.436184м/с. Wrong sign. Baseline terminal s_faulted−s_clean+996.390721м — эффект fault вv8, не ошибка H59-кандидата/XYZ. Pooled corr residual vs terminaldelta_s+.27837, vs GNSS magnitude eventbias−.39345; не physical brake gain.

## Проверки и непроведённые этапы

161canonical,43research-integrity,21diagnostic tests PASS; наборы повторялись, суммы не уникальны. Full-state/off parity, prediction arithmetic, boundedOLS/recenter,duplicates/gaps/noextrapolation,future/reset/commonzero,prefixcausality. Postaudit independentlyrecomputedweights/betas:maxdelta1.7764e-15;targetsпо190tracesmaxdelta0. Source/DB/componenthashesпослерезультатаunchanged.

ДоSQLисправленаmetadataошибкаsettings.bags вместоtop-levelbags; streaming-containerотказалдозапуска. Послеэксперимента вauditисправленоокруглениеCSVparser(round-trip):data/model/gatesunchanged. Failedlogsсохранены. Wolframвернул5Truechecks,limitsg*r*tau,positiveLScurvature,носwarningsinfinity;6тождествSymPyнезависимоPASS. Не दावा switchedstability. Decayingaccelerationнепредотвращаетpersistentvelocity/positionbias.

Нетcandidateaccuracy,enabledROSbenchmark,candidatecost,traincheck/development/validation/test,новыхActions/CI. ScientificstatusFOUNDATION_FAILED,coveragePASS,candidate=false,ready_to_merge=false. Не создаватьнулевуюcandidateRMSEилипустойpatchкакулучшение.

## Публикация

GitHub.create_blobдляmonitor.pyбылзаблокированOpenAI:невозможноопределитьстатусбезопасности. Не повторялсядругимGitendpointиливдругойexternalstorage. ПоэтомуэтотreportcommitНЕmeasuredsourcecommit; source publicationPARTIAL. ЭтоотдельноотscientificFAIL,полученногоранее. Exactlocaldiagnostics/sourcehashes/tests/diagnostic.patchсохраненывлокальномпакете,нонеперезагружаютсявобходblock. Другиечисленныерезультаты/отчётвыгруженыотдельно.

[Workspace R6/H59](https://drive.google.com/drive/folders/1MF_QBFq8MzFd1Vn-tsV9-8kGjTBL_NiO). ПолныйREPORT,compactCSV/JSON,rawtraces,lock,commandsиpublicationreceiptsвсоответствующихподкаталогах;codepublicationограничениеотмеченовCHAT_EXPORT_MANIFEST. Sharedsource/data/teacher/atlas/FD2непродублированы. СтарыеH44reportsнеизменены.

Воспроизведениеизлокальногоdiagnosticпакетапослеverifiedpreflight: python code/foundation.py --work /path/to/R6-H59 --output /new/output --workers 4. АудитбезSQL: python code/audit.py --root /path/to/foundation-v1 --output /new/POST_AUDIT.json. BLASthreads=1. СначалаSTART HERE,exactdependenciesиlock;никакогоповторногоcheck/validation.

**FOUNDATION_FAILED относитсякэтойфиксированноймодели,неопровергаетвсёсемействолокальнойадаптации. PR не создан по условию карточки; следующего candidate stage нет.**
