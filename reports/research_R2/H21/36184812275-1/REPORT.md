# R2-H21: INCONCLUSIVE — исследовательский артефакт, не готов к merge

## Решение и идентификаторы

Вердикт исследования: **INCONCLUSIVE**. Достаточного покрытия вмешательств по PLAN **нет**. Допуск к validation **не получен**. Готовность к merge: **нет**. Нельзя трактовать прохождение CI как улучшение точности.

Baseline: `65bba39ed05c781f3f69a65c02f69931152cbfd9`, canonical `GuardedReadoutObserver`, `guarded_readout_v7.yaml`. Измеряются опубликованные `Estimate.v/s`, не внутренние `.v/.s`. Gain=1, holdoff=.5 s, inner wheel compensation=0, adaptation_tau=.5, 20 Hz, delay=0. Main не обновлял; H11/v8 и другие R2-кандидаты не включал.

PLAN до экспериментов: `fd7812ae97cf42ee872843ddf0ccca7612ec3b63`, `research/R2/H21/PLAN.md`. Единственный измеренный candidate source: **`93a9955d834fdf5b7b7f3c5342e7368321b0d5a2`**. Ветка: `research/round2-H21`. Run: **36184812275-1**, [Actions](https://github.com/jabrailkhalil/hack/actions/runs/36184812275). Raw checkpoint: **`d5afeb32f507448742102acbf77f95cb006f7bfd`**, [все evidence](https://github.com/jabrailkhalil/hack/tree/d5afeb32f507448742102acbf77f95cb006f7bfd/reports/research_R2/H21/36184812275-1). Позднейший commit этого отчёта не является новой версией алгоритма.

Applied candidate core SHA256: `b3369d61a364f83787a125a8f71a6c20f73434043c2d29416316a171ecded119`. Applied hooks patch SHA256: `8c60854529c5e302f7ddd087ef6a39d4398f594e9cb9cca8f694e53308953895`. Полные source/config/split/evaluator SHA256 — `development/started.json`. Алгоритм и параметры после первого real-data replay не менялись.

## Реальное изменение

`ReachableIntervalObserver` наследует canonical guarded observer. Дополнительные четыре bounds скорости/drive, timestamps и насыщаемые counters задают условную достижимую область от прошлой согласованной пары. Внутри эпохи колёса не сужают интервал и не переякоряют его. Initial drive — полный физический диапазон; additive uncertainty ±0.6 м/с². Включены полные экстремумы нелинейного `drive_target/resistance` по velocity tube, не midpoint.

Supervisor может удалить только уже допустимую слабую коррекцию: residual ≤0.8 м/с и |wheel|>0.25 м/с, measurement вне интервала с возрастным/noise padding. Anchor условный, pair noise не делится на sqrt(2). Maximum epoch 2 s, maximum width 3 м/с, ambiguity release .5 s/cooldown .5 s. При пустом пересечении фиксируется ambiguity, но скорость не прижимается к колесу и не выставляется остановка. Wide/expired interval отключает supervisor.

Основной predict, параметры физики, covariance/adaptation, gates, zero-lock, stop, bounded recovery и readout не заменены. Хук находится после hard gates, перед fusion; default хук — no-op. Runtime не получает GNSS/IMU, bag ID, имена файлов или fault flag. Нет ожидания будущих samples, histories не растут; rejection tuple ≤2, bounds tuple=4, counters ограничены 2^31−1.

**Обычный checkout/канонический ROS launch H21 не включает.** Research driver автоматически создаёт две изолированные копии pinned core и применяет `core-hooks.patch` только к кандидатной копии. Активный `core.py` в checkout не изменяется. Чтобы воспроизвести измерения, следует запускать `research/R2/H21/run.py`, а не вручную менять canonical launch. Constructor H21 без hooks отказывается запускаться. Installed H21 adapter/launch и новый ROS benchmark не заявляются.

## Методика и фактически выполненные стадии

Выполнены все **64 train bags**: 1366299 выходов на метод, train GNSS не читался. Это replay/compatibility, не оценка train accuracy и не fitting. Затем все **17 development bags / 7 исходных групп**, true development role, read-only SQL loader. Ни train, ни validation не переименованы в development.

Один unchanged `evaluate.score/replay/match/metrics/distance_surrogate`, unchanged `fault_windows` и group-macro aggregation. В фабрике подставляются правильные классы, legacy ключи baseline_v2/balanced_physics переименовываются только после подсчёта. Получены 56 original fault-сценариев и 60 original receiver-сравнений с reference. Дополнительные 42 сценариев отдельно: dropout30 s, common ±1.5 м/с² до ±3 м/с (ramp2 s +hold2 s). Anchors прежние, только vehicle signals; extra suite не заменяет original admission.

На каждом baseline tick реально исполнялись canonical module, отдельно восстановленный pinned module и H21-off; сверялись все базовые поля состояния, published Estimate и статусы. `ev.score` отдельно требует одинакового расписания/размера outputs baseline/candidate. Off/каноническая эквивалентность проверялась также на fault replay. Потери reference не скрываются нулями: clean reference доступен в 19 bag/receiver-парах и 6 из 7 групп, 15 пар без reference. На 7 bags нет ни одного receiver, ещё на одной отсутствует master. Access journals и missing pairs сохранены.

**Validation и отдельный validation-freeze не выполнялись из-за prevalidation gate. Final/test DB measurement payloads не открывались.** Никакие исторические validation/final цифры не выданы за новые результаты H21. Download/unpack общего pinned ZIP не является открытием test измерений в loader. Старые release artifacts и тесты их целостности не переписаны.

## Accuracy на development, не validation

| Метрика | R2 v7 | H21 | Δ ошибки |
|---|---:|---:|---:|
| Clean group-macro RMSE, м/с | 0.0926681429828 | 0.0926681429828 | +0% |
| Original fault-event group-macro RMSE, м/с | 0.237548612056 | 0.237548612056 | +0% |
| Pooled RMSE, м/с | 0.129305694477 | 0.129305694477 | +0% |
| Scalar-span distance RMSE, м | 5.3102950048 | 5.3102950048 | +0% |


Причины общего development-gate: `insufficient_gain`. Требование gain≥2% clean ИЛИ ≥5% original fault не смягчалось. Clean/fault/pooled regression ≤.5%, distance≤1%, per-bag clean≤base+max(.005,5%), no coverage loss/extra false stops/new per-case unrecovered/causal errors/resets — прежние. Дополнительные safety причины: `[]`.

| Набор | Показатель | R2 v7 | H21 |
|---|---|---:|---:|
| clean | mae | 0.0349333529046 | 0.0349333529046 |
| clean | bias | 0.00639067742022 | 0.00639067742022 |
| clean | samples | 394221 | 394221 |
| clean | false_stops | 0 | 0 |
| original_fault | mae | 0.153796529331 | 0.153796529331 |
| original_fault | bias | 0.0111703078516 | 0.0111703078516 |
| original_fault | recovery_s | 0.724358284875 | 0.724358284875 |
| original_fault | samples | 17823 | 17823 |
| original_fault | false_stops | 0 | 0 |
| original_fault | unrecovered | 4 | 4 |
| diagnostic_fault | mae | 1.0687848502 | 1.06810107882 |
| diagnostic_fault | bias | 0.125414107229 | 0.124730335847 |
| diagnostic_fault | recovery_s | 2.74854772011 | 2.74854772011 |
| diagnostic_fault | samples | 19238 | 19238 |
| diagnostic_fault | false_stops | 8 | 8 |
| diagnostic_fault | unrecovered | 7 | 7 |


MAE/bias/recovery в этой таблице — group-macro по исходным группам; recovery None не превращается в ноль. `unrecovered` — отдельный счётчик. Distance — переякоренный скалярный surrogate относительно интеграла GNSS speed, **не XYZ/ENU и не полный terminal drift**. Приёмники одной bag не независимые поездки; tick bootstrap не выполнялся, statistical significance не заявляется.

## Активация, coverage и локальные эффекты

| Набор | Active ticks | Anchors | Weak eligible samples | Veto ticks / samples | Wide disables |
|---|---:|---:|---:|---:|---:|
| clean | 135148 | 7327 | 114571 | 2 / 4 | 7323 |
| original_fault | 13039 | 774 | 10668 | 0 / 0 | 736 |
| diagnostic_fault | 10216 | 600 | 8326 | 7 / 13 | 581 |


Predeclared sufficiency: ≥200 active ticks, ≥20 veto ticks, ≥2 исходных групп с veto. Получено **158403 active, 9 veto ticks, 3 групп**. Это суммарные исполнения clean/fault/extra replay, не уникальные независимые наблюдения. Расчёт интервала и реальное вмешательство в коррекцию — разные события.

| Набор | Receiver | Inside / matched active ticks | Доля |
|---|---|---:|---:|
| clean | master | 78857 / 78984 | 0.998392079408 |
| clean | rover | 85613 / 85741 | 0.998507131944 |
| original_fault | master | 8147 / 8190 | 0.99474969475 |
| original_fault | rover | 8624 / 8663 | 0.995498095348 |
| diagnostic_fault | master | 5901 / 6505 | 0.907148347425 |
| diagnostic_fault | rover | 6201 / 6803 | 0.911509628105 |


Coverage интервала — внешний GNSS diagnostic на active ticks, не calibration probability. Full counters рассчитаны на 20 Hz; trace сохраняет каждый20-й output и все veto. Width summary в audit относится к этой подвыборке. Before/during/after trace показывает interval, mode, выходы, disturbance и drive_a. Signed load steps ±.6, genuine stop, common drift, dropout и zero lock отдельно проверены синтетически; они не являются доказательством на реальном трамвае. Отдельной размеченной истины реальной смены нагрузки нет; wheel/model residual нельзя назвать независимой истиной. Обещанный отдельный natural-load residual разрез не реализован; это ограничение диагностики, не скрытый PASS.

External rejection labels: `{'unlabelled': 8, 'accepted_far_from_reference': 1940, 'active_missed_rejection_proxy': 1110, 'fault_consistent_rejection': 9}`. False rejection требует доступного reference рядом с wheel (≤.25 м/с), но вне расширенного интервала; fault-consistent — оба/все доступные references дальше .5 м/с. Остальное ambiguous/unlabelled. Accepted-far/missed — только прокси, reference несовершенен.

Различающихся сохранённых полей: 24. Полный список в audit/audit.json; существенные регрессии не скрываются за агрегатом.

- diagnostic_fault / 30618_073f08d1/master / p95: 2.94465946142 → 2.94465967167, Δ 2.10247269372e-07; {'kind': 'ramp_positive', 'start': 127.60000000000001, 'end': 131.60000000000002}.
- diagnostic_fault / 30618_073f08d1/rover / p95: 2.93018198491 → 2.93018198495, Δ 4.13966638746e-11; {'kind': 'ramp_positive', 'start': 127.60000000000001, 'end': 131.60000000000002}.


### Малый диагностический эффект не заменяет общий контракт

На original suite veto отсутствуют. Два clean veto-такта приходятся на `30618_117c2d02` и `30618_46e21b9b`, одну исходную группу, без GNSS reference; точность этих вмешательств неизвестна. Диагностический ramp_positive дал ещё 7 veto-тактов: 4 на `30618_073f08d1`, 1 на `30639_c31df386`, 2 на `30618_74559c73` без reference. Итого независимая оценка по reference доступна только для 5 veto-тактов / 9 wheel samples в двух группах, ещё 4 такта / 8 samples не размечены.

Extra-suite group-macro event RMSE: **1.95367999200215 → 1.95082929355026 м/с (−0.1459143%)**. На `30618_073f08d1`, positive ramp, master event RMSE 2.294307854269278→2.2474555412732755 (-2.042111%), rover 1.9011270843606203→1.8151955066460883 (-4.520033%). Это один bag с двумя receivers, не две независимые поездки. На `30639_c31df386` улучшение event RMSE около0.777%. На отрицательном ramp и dropout30 эффекта нет. Ни эти локальные улучшения, ни extra aggregate не учитываются вместо original admission.

В original suite остаются4 baseline unrecovered cases, H21 их не исправил и новых не добавил. В extra suite у обоих методов8 false-stop samples и7 unrecovered cases. Сохранённые регрессии — две крайне малые p95 дельты, вплоть до +2.10247e−7 м/с; они перечислены выше. Существенная эксплуатационная регрессия — вычислительная стоимость.

Медиана ширины по сохранённой clean trace-подвыборке2.2173 м/с, cap3 м/с;7323 clean epochs прекращены по ширине,0 по2-секундному lifetime. Это описательная локализация ограниченной активности, не доказанная ablation-причинность. Coverage истинной скорости не гарантируется: extra GNSS coverage интервала лишь90.71%/91.15%. Подтверждённых false veto по объявленному внешнему правилу0, однако8 unlabelled samples не позволяют заявлять доказанную безопасность этих коррекций.

## Стоимость

На первых60s первого development bag `30618_0652866c`: одна warmup-пара и пять измеренных AB/BA пар, threads=1, одинаковый collector внутри каждого режима. Step и replay измерены отдельно; benchmark не включает expensive off-equivalence/diagnostic wrappers.

| Измерение | R2 v7, мкс/выход | H21, мкс/выход | Δ |
|---|---:|---:|---:|
| step / cpu_us_per_output | 31.4095716667 | 46.3524733333 | +47.574357% |
| step / wall_us_per_output | 31.42411 | 46.3942008333 | +47.638870% |
| replay / cpu_us_per_output | 50.9057758929 | 68.5466723214 | +34.654017% |
| replay / wall_us_per_output | 50.9083053571 | 68.7555098215 | +35.057550% |


Это Python CPU/wall на данный поток, **не installed ROS p95/p99**. Peak RSS из benchmark относится ко всему offline evaluator с NumPy/данными, не к ROS node. Свежий включённый H21 под2CPU/500000000 bytes с двумя clock modes не запускался: prevalidation/accuracy gate не дал основания к promotion. Обычный ROS/offline CI касается canonical profile, а не H21; старый v4 benchmark ему не приписан.

## Проверки, математика и источники

В Actions прошли144 baseline unit tests,43 research-integrity tests,11 H21 tests (внутри последнего повторены24 исходных ObserverTests; это не отдельные35 уникальных tests). Проверены7000 ticks exact off,10000 ticks bounded memory/NaN/dropout, future/duplicate/reset/prefix,160 small-step trajectory inclusions,400 signed target intervals, empty-intersection release и zero/strong bypass. Compileall и git apply --check пройдены. Полные логи в evidence. После скачивания artifacts локально снова прошли11 H21 tests именно source93a9955; проверены все manifest SHA256, точное соответствие generated hooks файлу patch и совпадение заново рассчитанного admission с сохранённым decision.

Обычный CI measured commit: [36184812333](https://github.com/jabrailkhalil/hack/actions/runs/36184812333), все4 jobs success, без удаления historical checks. Исследовательский Actions success означает завершение измерений, не accuracy PASS. Первоначальный локальный test fixture release ошибочно сохранял stale timestamp; исправлен до данных без изменения алгоритма. Локальная диагностика пустого tape тоже исправлена до data. Локальный сетевой доступ недоступен (DNS); реальные данные и исполнение обеспечены GitHub Actions.

Wolfram фактически проверил observability rank2 и nullspace span(-1,0,1): v→v+k,b_common→b_common−k неразличимы. Проверены exp convex coefficients, clipping order, resistance/braking signs, power cap monotonicity и interval propagation inequalities; worksheet и actual outputs сохранены; `audit/wolfram-standalone.wl` использует фактически распознанные сервисом Quantity bindings и запускается обычным WL kernel без FreeformPrompt. Условный математический bound не доказывает истинность wheel anchor, 3σ-error bound, D=.6 или intra-step command-hull assumptions. 3σ без распределительных предпосылок не означает99.7% coverage. Детали — `audit/BOUND_DERIVATION.md`.

Научный ориентир: Huang, *Application of interval state estimation in vehicle control*, AEJ61(1),911–916(2022), DOI10.1016/j.aej.2021.04.074. [Publisher abstract](https://www.sciencedirect.com/science/article/pii/S1110016821003173). Consensus search/fetch выполнены: search abstract и metadata, fetch abstract unavailable. Полный текст не прочитан. Scite реально вызван, но вернул monthly MCP limit25/reset2026-10-01; citation context/fulltext не получены. Другая LPV модель и симуляции не доказывают точность этого wheel-only кандидата. `SOURCES.md` фиксирует глубину чтения и относящиеся R1/v6/PR14/23/26 материалы. Данных других validation R2 для выбора не использовано.

## Воспроизведение

```bash
git checkout 93a9955d834fdf5b7b7f3c5342e7368321b0d5a2
python3.13 -m venv .venv-h21
. .venv-h21/bin/activate
python -m pip install -r requirements-research.txt
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
python tools/get_dataset.py
OUT=$(mktemp -d /tmp/H21.XXXXXX)
PYTHONPATH=src/reserve_odometry python -m unittest discover -s tests -v
python -m unittest discover -s research/tests -v
python research/R2/H21/tests.py -v
python research/R2/H21/tests.py --diagnostics "$OUT/synthetic"
python research/R2/H21/run.py --stage train --output "$OUT/train"
python research/R2/H21/run.py --stage development --output "$OUT/development"
cat "$OUT/development/decision.json"
```

Каждая стадия отказывается перезаписывать output. Повтор использует ровно этот source/PLAN; старые результаты сохраняются. Freeze/validation-команды существуют в PLAN/workflow, но в данном выполнении **не запускались**. Patch/checksum, полный source archive, actual commands в workflow/logs, raw per-bag JSON/CSV, access и before/during/after traces приложены. Raw bags, секреты и кэши в Git не коммитились.

## Границы вывода

Один фиксированный кандидат и development, не независимый final test. Результат не распространяется на всё семейство интервальных методов. Из-за недостаточного intervention coverage нельзя объявить метод подтверждённым; приёмочный контракт сам по себе тоже не пройден. Units1/3.6 и relative1D ограничения baseline сохраняются. Ветка/PR — исследовательский артефакт, не готов к merge; main/чужие ветки не изменены, merge/auto-merge не выполнялись.
