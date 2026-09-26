# R4-H35 — REJECTED: разная динамика нарастания и отпускания привода

## Решение

**Оба зарегистрированных кандидата отклонены на полном development. Исследовательский артефакт, не готов к merge.** Ratio 0.5 не достигает требуемого original fault gain и ухудшает common-mode suite. Ratio 2.0 ухудшает original fault, common-mode и точную low-speed suite. Кандидат для validation не выбран; validation/FREEZE/final-test не выполнялись. Это отрицательный результат двух конкретных ratios, не всего семейства actuator-моделей.

## Источник и версии

- Baseline: **e3b0c9c039d2953fbfcda51231263d38ef9f1024**, полный tree **eae49a504bc59b5c9b408445150bef32e111956f**.
- Приложенный ZIP SHA256 **a8e0bfa033e0a02c460c30b02f34a5c64ece85b05003512941387d3cf1f319a2**. Все301файл, paths/bytes/executable bits проверены, не только8ключевых. Remote commit→tree прочитан отдельно. Pristine и candidate раздельны; локальный snapshot не объявлен удалённым Git-коммитом.
- PLAN опубликован до данных: **4446fc50419c73fcd264c773ffb7afbe905c0007**.
- Foundation source: **f1d483a64c6cbd77b5d50a1cc4d0160b9f384120**, train начался26.09.2026 08:48:03.763673UTC.
- **Измеренный алгоритм и основной driver: c75384cda3fb77de508c2d4128f38c17ed24613b**. Опубликован09:05:34UTC;10remoteGitblobIDs сверены с локальными bytes09:08:26UTC; development начался09:08:27.979204UTC.
- Дополнительный post-rejection audit точного low-speed набора: **27ea26e128d4e26273aeaa60763d8cded705e9fa**. Он не меняет candidate.
- Ветка: `research/R4-H35`. Execution IDs: foundation-local-01, development-local-01, pinned-low-local-01, cost-local-01.
- Поздние report/checkpoint SHA приведены в SUMMARY отдельно; не выдаются за измеренный код.

Baseline — полный canonical **GuardedReadoutObserver v8/champion_v8.yaml**, не Config defaults/v5/v7:20Hz,delay0,readout gain1/holdoff.5,adaptation_tau.5,compensation0,quarantine1.5. Остальные параметры точно из YAML. Сравниваются возвращаемые Estimate.v/s. Main, чужие ветки, прежние отчёты и release manifests не изменялись. No merge/auto-merge/force-push.

## Реализованный механизм

Один непрерывный drive_a. Base tau **0.3927619145850434с**; release tau **0.1963809572925217с** либо **0.7855238291700868с**. Это уменьшение модуля накопленного состояния, не разделение знака traction/braking из H07. H17 deadtime и H24 static map не добавлялись; соответствующие PR22/30/45 прочитаны.

При x=0 или росте модуля в направлении target используется base tau. При уменьшении модуля — release tau. Свежая нейтраль является release; stale/invalid/future команда сохраняет исходный neutral fallback с base tau. При противоположных знаках до пересечения нуля применяется release, после — base на оставшееся время того же шага: `t0=release_tau*log(1+abs(x/target))`. Дополнительного output tick/reset/deadtime/d-decay нет. Малое ненулевое состояние не обнуляется новым epsilon. Ratio1 повторяет исходный порядок float operations.

Canonical core/readout/Timeline/default не изменены. Factory создаёт приватную проверенную копию core с одним actuator hook и ReleaseObserver поверх неизменного guarded readout. **Включение: factory.build(0.5) или build(2.0); build(None)=pristine v8, build(1.0)=off.** Обычный checkout/ROS launch не включает H35. Hook algorithm.patch сам по себе недостаточен; не накладывать его поверх canonical core перед factory, который уже создаёт private copy.

Runtime принимает только controller/front/rear, без GNSS/IMU/future/bagID/faultoracle. Дополнительное поле — постоянный release_ratio, новых динамических историй нет. Внешние Monitor/NPZ traces — только offline collector, не память runtime. Не изменены физические gain, d learning, measurement gates, recovery, covariance, readout и интеграл s.

Wolfram реально проверил ODE residual=0, crossing, continuity, ratio1, convex scalar step и neutral impulse=x0*tau; worksheet/output сохранены. Это не доказательство nonlinear observer stability или истинной actuator dynamics. После известного quota stop новые Consensus/Scite-запросы не делались; внешняя публикация для элементарной локальной модели не выдумывалась.

## Foundation и методика

Все64train bag полностью, только3vehicle topics. Probe и независимый pristine replay дали точно равные official arrays/counters на каждом bag: **1366299outputs**. GNSS train не декодировался, параметры не подбирались.

Foundation **PASS**:100releaseepisodes/23группы,87traction→coast и13уменьшений амплитуды. Медианный модельный потенциал **0.0930806735241043м/с**, выше предзаданных.01. False-transition proxy0/100 при лимите.25; это проверка возврата команды в следующие.25с только во внешнем offline аудите, не настоящая physical false-positive rate. Нет квалифицированных foundation brake→coast/sign-change эпизодов; эти ветви проверены unit/synthetic, их real coverage не заявляется.

Development: **все17исходных bag/7групп**. Clean reference19bag/receiver-пар/6групп;15пар missing, не RMSE0. Original faults56/14bag, reference60сравнений/5групп. Оба приёмника сохранены, не считаются независимыми поездками.

Неизменные evaluate.score/replay/match/distance_surrogate, research_v6.summary/macro, guarded fault_windows, H11 windows/injection. Wrapper выбирает только observer и сохраняет outputs. Aliases baseline_v2/balanced_physics означают реально исполненные v8/off и переименованы после scoring. Events/order/stamps/masks/faultanchors одинаковы. Hashes inputs/timestamps/targets/masks сохранены. Off arrays/counters точно равны baseline в каждом replay. **Все5числовых fingerprint development v8 воспроизведены точно**, не подставлены из истории.

Контракт:≥2%clean gain ИЛИ≥5%original fault gain; clean/fault/pooled regression≤.5%,distance≤1%,per-bag clean≤base+max(.005м/с,5%); same coverage/schedule;no added false stops/new individual unrecovered/causal errors/resets. Pinned low/common event regression≤.5% плюс safety. Full-faulted-bag distance≤1% зарегистрирован до опытов. Phase/signed/recovery diagnostics не стали новыми post-hoc veto. При провале development validation не запускается.

## Результаты development

Плюс означает рост ошибки. Скоростные RMSE вм/с, distance вм.

| Метрика | v8 | Ratio0.5 | Изменение | Ratio2.0 | Изменение |
|---|---:|---:|---:|---:|---:|
| Clean group-macro | .092668142983 | .092499275696 | −.182228% | .092982321550 | +.339036% |
| Original fault-event group-macro | .237548612056 | .232085298012 | **−2.299872%** | .265524556643 | **+11.776935%** |
| Pooled clean | .129305694477 | .129250535105 | −.042658% | .129484566658 | +.138333% |
| Scalar-span distance | 5.310295004801 | 5.333899141532 | +.444498% | 5.285661297343 | −.463886% |
| Common-mode event | .100632272301 | .102532898123 | **+1.888684%** | .101204096041 | **+.568231%** |
| Full-faulted-bag scalar distance | 6.269376947281 | 6.312562778798 | +.688838% | 6.138970742518 | −2.080050% |

Ratio0.5: insufficient_gain + common_mode regression. Ratio2.0: insufficient_gain + original/common/low regressions. **Ни одного eligible.** Matched394221 у всех. False stops clean/original0/0 у всех. Original unrecovered **4→4**, не0; common-mode2→2, exactlow6→6. Новых individual unrecovered/false stops/coverage/schedule/causal/reset ошибок нет. Средние recovery меняются: .724358285→.682170785/.735295785с; это group-macro только подтверждённых случаев, не счётчик failures.

Clean MAE .034933352905→.034836229386/.035126061829м/с; signed bias .006390677420→.006510874074/.006264286726м/с. Fault-window MAE .153796529331→.151126951125/.163827177437м/с. Все MAE/p95/signed bias/recovery сохранены в MEASUREMENTS и полном evidence. Fault-window включает recovery10с, original event RMSE — только отказ.

## Low-speed coverage defect и отдельный аудит

В первом H35 PLAN/harness low-speed набор ошибочно был неполным: inclusive1..2м/с, безu≥0, толькоlock5с. Его15сценариев/исходные результаты сохранены в raw low_speed и **не выдаются за canonical suite**. Это недостаток первоначального harness, не новая научная альтернатива.

После уже отрицательного original/common результата проверен точный PR13/R3-H24 код (H24 SHA6b3a11a68b83ee7b680b3b283f4800726c7b84cd, blob2141a444fd72a71277b8e8223c3ec235f6b999e9): strict1<speed<2, u≥0, lock3/5с. audit_pinned_low.py опубликован до дополнительного запуска на **неизменных кандидатах**. Никакие original metrics/параметры/пороги не переписаны, validation не открыт.

Exact suite: **26сценариев/34reference comparisons**; baseline eventRMSE **.368545673306**, ratio0.5 **.349293541908 (−5.223812%)**, ratio2 **.415992445251 (+12.874055%)**. False stops0 и unrecovered6 у всех. Ratio0.5 проходит exactlow, но всё равно проваливает originalgain/common. Ratio2 проваливает и точныйlow. Итог не изменён.

## Activation, регрессии и дистанция

Release-step изменений/changed returned speed ticks: **92979/185484** для0.5, **111192/189859** для2.0, по7групп. Локальный counterfactual шаг сравнивается при одинаковом старом состоянии; дальнейшее распространение эффекта учитывается отдельно. Coverage≥200/≥200/≥3 пройдено.

Original event RMSE ухудшился в31/60пар для0.5 и41/60для2.0 (tolerance1e-12). Например:

| Кандидат / bag / receiver / fault | v8 | H35 | Изменение |
|---|---:|---:|---:|
| 0.5 / 30639_dce52be4 / master / dropout5 | .264680028 | .357679249 | +35.1365% |
| 0.5 / 30639_dce52be4 / rover / dropout5 | .271164375 | .364450295 | +34.4020% |
| 0.5 / 30639_9c362687 / rover / dropout10 | .258670139 | .320281924 | +23.8187% |
| 2.0 / 30639_e4379d7f / rover / dropout10 | .350459468 | .519903345 | +48.3491% |
| 2.0 / 30618_88548b02 / master / dropout10 | .244553348 | .363548433 | +48.6581% |

Clean RMSE хуже в2/19 и17/19пар, но исходный per-bag clean limit не нарушен. Original recovery у0.5 дважды медленнее на.05с; у2.0 дважды на.5с, одинраз на.15с. Полные выигравшие/проигравшие строки не скрыты.

Release diagnostic —24окна/30reference-пар, dropout за.2с до/послеrelease: eventRMSE **.370981671834→.401226573251/.400075445344**, оба хуже. Это отдельный development diagnostic, не замена admission.

Все56originalfaults также проиграны на полных bag. Скалярная distance aggregate втаблице. Локально0.5,30639_9c362687/master/dropout10: **16.411746029→16.974027856м (+3.4261%)**;2.0,30639_dce52be4/master/dropout10: **10.942260671→11.569822948м (+5.7352%)**. Per-bag distance не новый gate;1% относится к агрегату.

Накопленная delta_s не стирается при recovery:0.5,30618_0652866c/dropout10 **+1.075215563м через10с послеfault и+1.273191638м вконцеbag**. Это различие candidate−baseline, не автоматически ошибка кtruth. Все delta_s через1/5/10с иterminal, signed velocity integrals на непрерывных reference spans сохранены. Distance —relative_1d scalar surrogate, неxyz/ENU/полныйdrift.

## Фактические проверки и вычислительная стоимость

Локально156canonicalunit+43integrity+37H35/harness tests PASS; compile PASS. 29mechanism tests —подмножество37. Покрыты8000off exact всех inherited states/Estimate,10000bounded steps,causalprefix/duplicates/stale/future/reset,zero-lock/H11,оба знакаrelease/crossing,drive0/repeatedneutral,lossдо/послеrelease,интегралv/s; независимый solve_ivp tolerance1e-10. Synthetic tests не являются real accuracy.

Первый harness-test доdevelopment имел KeyError:mae дляmissingreference. Исправлен только тест наget, старый errorlog сохранён. Патч приложенных новыхresearchфайлов проверен на отдельной чистой копииbaseline;37tests PASS, generatedruntime bytes совпадают сmeasured. gitapply дал одно trailing-whitespace warning в неизменном PLAN;check/application успешны. Independent stdlib audit rawmetrics:32aggregate fields, maxdelta8.881784197001252e-16,301sourcefiles/10remoteblobs,64train/17devaccesses; no-new-safety clauses PASS. Нового replay/fitting/validation приаудите нет.

Cost: первыйdevelopmentbag10сwarmup+180с,threads1,3AB+3BAдлякаждогоratio/scenario,одинаковыйcollector. **Медиана парного изменения stepCPU** healthy **+4.2752%/+4.8885%**,dropout10 **+3.2427%/+3.6189%** для0.5/2.0. Raw48replays сохранены. Это не отношение отдельных медиан,неROS latency/RSS/worstcase. Для2.0dropout разность отдельных медиан имеет иной знак, чем медиана парных ratios: вариация времени явно сохранена.

## Среда и отсутствующие этапы

Локальный downloader: DNSошибка. Авторизованный Actions datastaging **36230601441 success** скачал exactdataset, проверил SHA256split/каждогобага; SQLне декодировал; извлёк толькоtrain/dev. DatasetSHA256 d0b2483e13990edb8219b0d7bbcafc7ed001cce549a4d3af467069b2472e7d52. Artifact10902188904 expires03.10.2026 08:43:27UTC. Dataset не коммитился/не включён впакет.

**Accuracy эксперименты реально выполнены локально.** Попытка независимого Actionsreproduction **36231958468 failure до шагов**:job108376665007,steps=null,logfetch404BlobNotFound. RootcauseNOT_ESTABLISHED; billing/quota не выдумываются. Этим run **не созданы** reproduction resultartifact/checkpoint. CI measuredsource **36231733554 failure**. Ранний canonicalCI36230601418success не проверяет включённыйH35. Повторных attempts послеблокировки не запускали, платные ресурсы/ACL не меняли. GitHub запись черезconnector доступна, отчёт/evidence коммитятся отдельно.

**Installed enabled H35 ROS обоихclocks offline2CPU/500000000bytes — NOT_RUN_AFTER_REJECTION.** Validation/FREEZE/finaltest не выполнялись. source/data/localexecution доступны; новая независимая проверка обобщения не получена. Общая шкала1/3.6,commonmodeambiguity инеидентифицируемая настоящаяload остаются ограничениями.

## Evidence и воспроизведение

Git: [MEASUREMENTS](MEASUREMENTS.json), [всеcleanстроки17bag](CLEAN_PER_BAG.csv), [все60originaleventсравнений](ORIGINAL_EVENT_RMSE.csv), [source receipt](SOURCE_RECEIPT.json), SUMMARY. Большой **companion ZIP вответечата** содержит полный native results.json, всеper-bag/receiver/fault MAE/bias/p95/recovery/distance,missingreference/masks/hashes,NPZtraces,accessjournals,foundation,exactlowaudit,cost,tests/source/patch,полный301manifest иисполняемый audit. SHA rawфайлов указан вMEASUREMENTS;manifestкаждогофайла вZIP. Это **не существующий Actions evidence artifact**.

Наизолированном checkout measuredSHA, Python3.13.5/pinned requirements:

```bash
python -m pip install -r requirements-research.txt
export PYTHONPATH=src/reserve_odometry
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
export H35_SOURCE_SHA=c75384cda3fb77de508c2d4128f38c17ed24613b
export H35_DATA_ROOT=/absolute/new/H35-data
gh api /repos/jabrailkhalil/hack/actions/artifacts/10902188904/zip > /absolute/H35-data-artifact.zip
python -m unittest discover -s tests -v
python -m unittest discover -s research/tests -v
python -m unittest discover -s research/R4/H35/tests -v
python research/R4/H35/stage_data.py --artifact /absolute/H35-data-artifact.zip --output "$H35_DATA_ROOT" --role train
OUT="$(mktemp -d /tmp/H35-reproduce-XXXXXX)"
python research/R4/H35/foundation.py --output "$OUT/foundation"
# Только при foundation PASS:
python research/R4/H35/stage_data.py --artifact /absolute/H35-data-artifact.zip --output "$H35_DATA_ROOT" --role development
python research/R4/H35/run.py --foundation "$OUT/foundation/results.json" --output "$OUT/development" --workers 2
python research/R4/H35/cost.py --output "$OUT/cost"
# Дополнительный audit_pinned_low.py взять из commit27ea26e; candidate остаётся c753.
python research/R4/H35/audit_pinned_low.py --output "$OUT/pinned-low"
```

Fresh outputs обязательны. Послеистеченияretention нужен новый разрешённый staging техжепроверенных данных; будущаядоступность artifact не обещается. No validation/test CLI. Standalone patch новыхresearchфайлов вZIP работает иповерх проверенногоархива без.git, черезполныйSOURCE_RECEIPT. **Продвижение runtime вmain не предлагается.**
