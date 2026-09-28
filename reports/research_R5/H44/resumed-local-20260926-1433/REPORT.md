# R5-H44 — REJECTED после проверки teacher/atlas и matched GNSS/wheel fitting

**Исследование завершено. Отрицательный результат, не готов к merge.** Прежний DEPENDENCY_PENDING снят. G — единственный GNSS-кандидат; W — matched wheel-target control, не запасной кандидат. G улучшает original fault RMSE на 9.705190%, но нарушает distance/check gates. Преимущество G над W ниже зарегистрированного attribution threshold. Validation/final test не открывались, validation-freeze не создавался. Никакого подбора после результатов.

## Версии и исполнение

Baseline `b2783206000091ab11a1c11ac3ff79082188a4fb`, tree `973d50d288e050325ee1c71a90fa8d81f2a099af`, полный verified ZIP из 320 файлов. ZIP SHA256 `4823fbdbbb979d7b561841e2831e68f2f7d9d8ec0d14e970f09a38cd51dff4c4`. Исходные source paths/bytes/modes проверены до и после эксперимента.

Новый FIT_PLAN опубликован ДО train IO/fitting: `353f5657b32c331f792cb164400db940c16686ea`, 26.09.2026 14:35:43 UTC. Exact measured source/config commit: **`0ca93500d4d305c21c998bfd8d2a2e78c98b90ad`**. Он опубликован ПОСЛЕ локального исполнения и проверен по Git blob SHA, не выдаётся за предварительный freeze. PLAN, прежний preflight, upstream и исторические отчёты сохранены. Ветка `research/R5-H44`, тот же draft PR57; merge/auto-merge/force-push не выполнялись.

Все новые численные прогоны локальные, Python3.13.5/NumPy2.3.5/SciPy1.17.0. Нет нового Actions accuracy-run или заявления о зелёном CI. Полный DETAILS, raw results, source/receipts/logs/patch переданы в evidence ZIP; это не Actions artifact.

## Реальный dependency preflight

Exact teacher ZIP SHA256 `2ee08edb32343350bf6ae6202836644de4fb309640f2d140a1eb9d5791af28b8`, atlas ZIP `6a759f4bafe4ece014e9dd4f25b201549e317f2ca9db7b47b6c15d4443d9b011`: size/SHA/CRC/manifest PASS. Штатные verifiers проверили **85 teacher files / 64 arrays и 53 atlas files**. Folds bridge всех64 назначений совпал:50fit bags/20groups,14check bags/7groups. Разные producer JSON сохранены, не переписаны. DEPENDENCIES.lock создан до train и связывает оба manifests, native locks, bridge, source/split/folds, policy и reference contract.

Teacher не пересоздавался. Его модуль скорости и некаузальная quality используются только для offline target selection/loss. Нет teacher initialization/runtime features. Atlas development errors не участвуют в fitting.

## Реальное изменение и matched-протокол

Меняются только effective F/m,P/m,B/m через прежние torque/power/brake. Canonical GuardedReadoutObserver, readout, Q/R, d-adaptation, сопротивление, numerical scheme, gates, low-speed lock, common quarantine, Timeline и частота неизменны. Полный v8 профиль:20Hz/delay0,readout1/.5,adaptation_tau.5,compensation0,quarantine1.5; измеряются returned Estimate.v/s. Только controller/front/rear в runtime, без новых зависимостей/истории.

| Effective coefficient | v8 | G | W |
|---|---:|---:|---:|
|F/m, м/с²|1.188434318103|1.288533445120|1.231281064868|
|P/m, м²/с³|7.021838337152|10.728192862271|9.653188616604|
|B/m, м/с²|1.139220235088|.822119506444|.822120186521|

Это не паспортные характеристики. Обычный checkout не включает H44: явная factory берёт config/readout из fitted JSON; research YAML численно эквивалентны. Canonical default не переключён. Старый fail-closed training_entrypoint принадлежит phase0; завершённый entrypoint — fit.py.

64 train DB прочитаны штатным vehicle-only loader, без train GNSS SQL; GNSS labels уже в frozen H42 arrays. Exact-wire duplicates не получают отдельный вес. Одинаковые пригодные окна G/W: **195, из них141fit/15groups и54check/5groups**, тяга/торможение в14/14fit и5/5check groups. Порог coverage пройден. Никаких новых folds. Teacher не интерполируется через masked row/gap>.2s и не заполняется колёсами.

Каждый objective call: собственный полный scalar observer/config на5с прошлого warmup, затем5с command-only forecast. Horizons .5/2/5s; abs(v) и prefix integral abs(v), поскольку знак teacher неизвестен. Runtime signed s не меняется. Обе цели имеют одни окна/timestamps/group weights, нормированные scales и prior .01*mean(logratio²), одинаковые bounds/start/TRF/max_nfev80. Ровно два fit без restarts: G nfev15/njev7/**36 actual residual calls**, W30/19/**87 calls**, всего123 из1000. Обе остановки ftol; global optimum не заявляется.

Первый window-builder был прерван внешним20с timeout ДО optimizer; неизменённое построение повторено в новом каталоге. Неполный префикс/лог сохранён. Это не дополнительный fit. Поэтому64 — число DB полного train прохода, не сумма opens с прерванным префиксом.

## Check prerequisite

G на GNSS check: velocity RMS .423671869765→.427913081730м/с (**+1.001061%**, допуск.5%), integral .824036139327→.793870786389м (−3.660683%). Три check groups нарушают5% velocity/integral guard, худшая velocity +36.40%. W также нарушает три group guards. Check-coast G5s .898667905→.936343209м/с. Это physical-unit group-balanced RMS без prior; normalized fitting loss хранится отдельно.

Полный descriptive development после check FAIL был заранее разрешён; validation запрещён. Все check/phase/horizon результаты сохранены, не использовались для переобучения.

## Реальные development метрики

Все17bags/7groups;19clean reference pairs/6groups. Original cropped56events/60reference comparisons, те же56full faulted bags. Low-speed26/34, common28/30. Scorer/masks/anchors/schedule/aggregation неизменны; missing=null. Независимый official baseline точно совпал на17clean bags и по всем5fingerprint fields. Full prefault outputs равны clean outputs того же профиля.

| Метрика | v8 | G | G к v8 | W |
|---|---:|---:|---:|---:|
|Clean macro RMSE,м/с|.092668142983|.092444346136|−.241504%|.092451004917|
|Original event RMSE,м/с|.237548612056|.214494068273|**−9.705190%**|.223379994112|
|Pooled clean RMSE,м/с|.129305694477|.128915547471|−.301725%|.128939625900|
|Clean scalar distance,м|5.310295004801|5.368194375188|**+1.090323%**|5.356119424069|
|Full-faulted distance,м|6.269376947281|6.509833186783|**+3.835409%**|6.477325266910|

394221matched points; false stops clean/original0/0; original unrecovered4 у всех. Нет новых индивидуальных невосстановлений/coverage/causal/reset failures. G меняет219387 outputs в6reference-bearing groups — activation PASS.

**L-gate G FAIL:** две distance-регрессии выше1%. Original gain5% не отменяет эти veto. W original event −5.964513%, но full-distance +3.316890%, также FAIL. **Attribution G/W:** original event −3.977942%, clean −.007202%, clean-distance +.225442%; gain2%clean/5%fault не достигнут. W не выбирается вместо G. Пороги не смягчались.

## Существенные регрессии и ограничения выигрыша

G ухудшает31/60original event и33/60full-distance comparisons. 30639_9c362687/rover/dropout10: .258670138631→.604332385778м/с (**+133.6305%**); 30618_27e994fc/rover/dropout10: .245154505465→.480493544390 (**+95.9962%**). Полная distance30639_c31df386/rover/dropout10:24.093163480→27.104923767м. Recovery медленнее в7случаях, максимум+.5с. Все локальные ухудшения, p95/MAE/bias и group metrics в CSV.

Без исходной группы8269991eafa82c45 original fault gain превращается в **+20.194830% regression**. Все7leave-one-group-out сохранены только как sensitivity, primary benchmark не меняется.

Накопленный интеграл не стирается: 30639_9c362687/dropout10, end+10=156.0s, s_faulted−s_clean: v8 .452806009м, G3.312145387м. Остатки сохраняются вконце1359.4s. Это эффект fault внутри профиля, не абсолютная ошибка XYZ.168signed delta_s identities проверены независимо, maxerror7.53e−12м. Recorder landmarks используют last<=boundary; поле prefault может включать граничный fault tick. Строгий pre-fault assert отдельно использует t<start, истинную предшествующую строку можно взять из near-trace.

Signed bias: clean .006390677→.007217454м/с; fault+recovery .011170308→.063287856. Улучшение MAE/recovery-агрегата не означает отсутствия этих смещений.

Low-speed event .368545673306→.340805236250; common .100632272301→.083596133653, новых failures нет. Их gain не заменяет L-gate; исходные6low/2common unrecovered сохранены. Для4original unresolved отдельно проверен reference:78/200finite postticks, максимум2подряд вместо требуемых20. Primary unrecovered остаётся4, маски не очищены.

## Проверки и стоимость

161canonical tests,43research-integrity,13launch fixtures PASS. H44:26до fit,30сcollector/gate tests доdevelopment, затем34собоими fitted profiles PASS; это пересекающиеся наборы. 2000tick disabled fullstate parity, masked-neighbor/gap/zero, target isolation, own-config warmup, independent Timeline fixture, finite/bounded12000ticks/profile, future/reset/YAML exact38fields. Compileall PASS. После результатов повторены195окон каждого из3профилей, maxdelta0; macros/gates воспроизведены из raw. SymPy1.14 выполнил7algebra checks; worksheet/output сохранены. Wolfram/Consensus/Scite в этом проходе не запускались.

24steady AB/BA replay,10s warmup+180s,threads1: G/v8 step12.745532→12.588087мкс(−1.235%), replayCPU19.777054→19.550738(−1.144%). W/v8 step+6.511%, replayCPU+5.462%. Только описательная offline стоимость, не гарантия ускорения; shared high-water RSS166879232B не nodeRSS. **Enabled installed ROS offline2CPU/500000000B,обаclockmodes,latency/RSS/params/import: NOT_RUN_AFTER_REJECTION.**

## Воспроизведение и evidence

В полном checkout0ca9350..., после requirements и подготовки verified320file receipt/разрешённыхDB через исходный bootstrap_r5:

```bash
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
FIT_ROOT="$PWD/research/R5/H44/fitted" python -m unittest discover -s research/R5/H44/tests -v
OUT=$(mktemp -d)
python research/R5/H44/develop.py --fit research/R5/H44/fitted --data-root /verified/data --source-receipt /verified/SOURCE_RECEIPT.json --output "$OUT/development" --workers 2
python research/R5/H44/cost.py --fit research/R5/H44/fitted --data-root /verified/data --source-receipt /verified/SOURCE_RECEIPT.json --output "$OUT/cost"
```

Это replay без нового fitting. Exact fitting reproduction: `python research/R5/H44/fit.py fit --windows /delivery/evidence/train_windows_complete --output /new/fit`. Native dependencies/build commands, исходный FIT_PLAN, обаfit/logs/predictions, fullraw metrics/traces, receipts, audit/science scripts и DETAILS в evidenceZIP безDB. Крупные файлы, перечисленные в FIT_LOCK, находятся в delivery, не все вGit. Runtime patch содержит только research YAML, не teacher arrays. Перед повторным build создать новый локальный dependency lock, не переписать исходный.

Teacher и raw GNSS — несовершенные unsigned proxies, не official combined XYZ; общие ошибки GNSS, extrinsics/origin и неизвестные остановки не решены. Development reused, independent finaltest отсутствует. Результат относится к одному фиксированному G/W-протоколу, не опровергает всё семейство GNSS-supervised calibration. **G не продвигать; PR остаётся draft.**
