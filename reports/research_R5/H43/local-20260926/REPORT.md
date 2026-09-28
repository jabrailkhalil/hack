# R5-H43 — AUDIT_COMPLETE

**Готов компонент atlas, не runtime-кандидат. H36 не продвигать.** Один локальный аудит без fitting: 17 clean development bags, 56 исходных fault crops и 56 полных faulted-bag. Validation/test не открывались. Основные scorer/masks/timestamps/anchors/aggregation сохранены.

## Версии

Baseline `b2783206000091ab11a1c11ac3ff79082188a4fb`, tree `973d50d288e050325ee1c71a90fa8d81f2a099af`. Полный ZIP: 320 файлов, SHA256 `4823fbdbbb979d7b561841e2831e68f2f7d9d8ec0d14e970f09a38cd51dff4c4`. Dataset SHA256 `d0b2483e13990edb8219b0d7bbcafc7ed001cce549a4d3af467069b2472e7d52`, извлечены/прочитаны только17 development DB.

План до измерений: `84d37559f91ed69a3d3a02de608ac411e2bdc143`. Измеренный audit source: **`2e3268714bf229e3a0292ca69b8102f7bddde832`**. Ветка `research/R5-H43`. Нового runtime source/freeze нет.

H36: только source **`4bd4908821e55e08195f08bd88eb7cfab17dc3c7`**, exact profiled.yaml blob **`daf4877655dbf0716c0fb1e4f17d331c84becf64`**. Тот же GuardedReadoutObserver, три изменённых коэффициента: torque3527.671834180356, power341583.68059829343, brake31188.934796194353. Остальной runtime/profile неизменен. Отдельный chat-source `3a1843b1bac229797982b352961f8af879854be9` исключён: связь версий не установлена, метрики не смешивались. Первичный optimizer H36 не повторялся.

## Основные измерения

| Development metric | v8 | H36 | Изменение ошибки |
|---|---:|---:|---:|
| Clean macro RMSE, м/с |0.09266814298282507|0.09248988094018253|−0.192366%|
| Original fault-event macro RMSE, м/с |0.2375486120563008|0.19330671305745648|−18.624356%|
| Pooled clean RMSE, м/с |0.1293056944774334|0.12887189815219607|−0.335481%|
| Clean scalar-span distance RMSE, м |5.310295004801444|5.409728932108304|**+1.872475%**|
| Full original-faulted-bag distance RMSE, м |6.269376947281123|6.614371763068372|**+5.502856%**|

Пять baseline fingerprint-полей совпали точно, H36 — до всех опубликованных знаков четырёх основных агрегатов. 394221 matched receiver-time comparisons; 7 source groups, clean reference6groups/19пар, original reference5groups/60пар. Missing reference семи bags сохранён как null. False stops clean/original0/0 у обоих, original unrecovered4/4.

### 1. Выигрыш зависит от одной группы

Без `8269991eafa82c45` original RMSE **0.191996→0.204429 м/с**, то есть **+6.4753%**, а не −18.62%. Эта группа содержит30618_0652866c/073f08d1/1551d0a9 (у последнего original anchor отсутствует). Выполнены все7 leave-one-group-out, не выбран новый удобный primary subset. Группа даёт122.48% чистой суммы group-RMSE улучшений, другие группы частично компенсируют его регрессиями.

### 2. Интервенции: важна предыстория, а не только три коэффициента

Две предзарегистрированные ablations не являются кандидатами. `coherent`: до fault.start работает v8; на первом output>=start только config заменяется H36, всё прежнее состояние/история/s сохранены. `hold_d`: тот же coherent start плюс удержание его исходного d в event; STOPPED приоритетен, после end обычная адаптация, distance не стирается.

| Original event RMSE | м/с |
|---|---:|
| v8 |0.237548612|
| H36 со своей предысторией |0.193306713|
| H36 с coherent v8 state |**0.329792408**|
| Coherent + hold d |**0.362441733**|

Смена предыстории ухудшила H36 на70.606%; удержание d добавило9.900% относительно coherent. Это причинные наблюдения именно для объявленных вмешательств, не доказательство отдельной роли каждого параметра. Границы инъекции известны только offline wrapper: такого oracle нет в допустимом runtime. Нельзя выдавать переключение H36 только при outage за проверенное улучшение.

### 3. Full distance и конкретные регрессии

Full dropout10-distance **6.332766496217→7.180289421013 м, +13.383139%**. Ухудшились33/60 original event,31/60 full-distance и6/19 clean сравнений. На30639_9c362687/rover dropout10 event **0.258670139→0.715098345 м/с**, full distance **19.581277723→23.039691469 м**. На master event signed integral при полном покрытии **+1.238018→+4.814696 м**, event+10 **+1.563048→+5.187168 м**.

На30618_073f08d1 H36 улучшает событие, но дельта s(H36−v8) сохраняется после recovery и достигает **+21.594596 м** к концу. Это разность алгоритмов, не истинная ошибка H36: нельзя объявлять её21.6м XYZ drift. Reference integral при пропусках сохранён как covered-edge integral с duration; full_integral=null, без мостиков через gaps.

Уточнён timestamp старой трассы: H36 берёт first t>=end+10, H43 last t<=query. Старые20.883858м воспроизводятся при147.65с; наша отметка147.60с даёт20.883729619м. Разница0.000127928м объясняется selector, алгоритм не менялся. Семь recovery медленнее, максимум+0.5с.

### 4. Reference confounding и ненаблюдаемое recovery

Предзаданный abs(master−rover)>.5м/с: **312 receiver-time comparisons /156 output ticks**, 0.07914% clean matched samples, дают **71.75362% pooled SSE v8**. Вложенный zero-versus-moving subset160comparisons даёт69.43748% SSE; доли не складываются. Виновный receiver не установлен, НИКАКИЕ точки не удалены из primary scorer. Agreement sensitivity — отдельная совокупность, не новый benchmark.

В original event mask **0 disagreement samples**;6154сравнения с согласованными двумя GNSS,301с missing peer. На agreement event slice H36 также улучшает RMSE0.239361→0.199415. Значит clean-reference проблема не объясняет автоматически весь original fault gain; group dependence — отдельный эффект.

Все4original unrecovered принадлежат30639_e4379d7f/rover. В каждом post10 есть78/200finite matched outputs, максимальная непрерывная серия2, а scorer требует20. Recovery не может быть подтверждён даже идеальным прогнозом при этой маске. Primary unrecovered остаётся4: дополнительная классификация — ненаблюдаемость, не доказанное физическое невосстановление.

В17DB нет /localization/kinematic_state. Полная Q&A описывает официальный reference как fused локализацию и Cartesian XYZ, не raw GNSS. Все наши speed/distance — proxies, не официальный XYZ результат. Teacher/карта/антенные плечи/ENU->MGRS здесь не создавались.

## Проверки и границы

**161legacy+43research-integrity+15H43 tests PASS** до measurement IO. 129exact schedules,17clean direct parity checks обоих профилей (34replays),112prefault-state checks обеих ablations.482инструментированные trajectories,5861782output rows. Два дополнительных состояния/профиля не выбирались по результатам.

Независимо из NPZ:2756reference integrals,max delta1.4211e−14м;482delta_s identities,max error7.6476e−11м. После переносимости путей/кэширования decompression20аналитических output-файлов повторились побайтно; нового DB replay/fit не было. Все320source files и17DB неизменны. Никаких train/validation/test IO. Все per-case/group/phase/time/reference slices,unrecovered,regressions,integrals и trace excerpts сохранены.

Локальный measurement wall104.64с,userCPU195.49с,system1.84с,2workers; maxRSS288704KiB — process accounting, не nodeRSS. **Actions и enabled ROS benchmark не запускались.** Никакого нового runtime-кандидата; accuracy-gain gate не критерий AUDIT_COMPLETE. Старый check-loss отказ H36 остаётся опубликованным ограничением, не пересчитан здесь.

Полный handoff содержит DETAILS.md,ERROR_ATLAS.json,COUNTEREXAMPLES.json,H36_VERSION_BINDINGS.json,таблицы,скрипты анализа,patch,receipts,tests и R5_HANDOFF.json(kind=atlas). Raw evidence451139115bytes,SHA256 **339841acf3144c7dc253d037c118b311f90d258e873655f1dbad8fe556a2c7bc**; это локальная выдача, не Actions artifact, без DB. Retention sandbox не гарантирован. Команды — README.md в handoff; исходный replay:

```bash
python research/R5/H43/test_audit.py
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python research/R5/H43/audit.py \
  --data-root /verified/development/data --output /new/H43-results --workers 2 \
  --source-sha 2e3268714bf229e3a0292ca69b8102f7bddde832
```

Статус H43: **AUDIT_COMPLETE, atlas component_ready=true, runtime_candidate_implemented=false, ready_to_merge=false**. Main, чужие branches/reports и H36 не изменены. Merge/auto-merge не выполнять.
