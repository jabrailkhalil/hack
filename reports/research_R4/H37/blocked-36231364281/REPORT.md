# R4-H37 — NOT_EVALUATED: кандидат подготовлен, accuracy execution заблокировано

**Исследовательский артефакт, не готов к merge.** Основание на train достаточно, минимальный runtime-кандидат реализован и проверен локально. Но парное сравнение на реальных development-записях не исполнилось: GitHub Actions дважды завершил job до шагов, а локальная загрузка датасета недоступна из-за DNS. Это **NOT_EVALUATED**, не REJECTED и не подтверждение улучшения. Порог и единственный вариант не менялись. Validation/final test не открывались.

PR: https://github.com/jabrailkhalil/hack/pull/46 . Ветка `research/R4-H37`. Merge, auto-merge, force-push не выполнялись; чужие ветки, main и прежние отчёты не изменены.

## 1. Четыре независимых статуса

| Область | Статус | Что подтверждено |
|---|---|---|
| Source | VERIFIED | Все 301 исходный файл, bytes и executable bits; полный tree совпал |
| Data | PARTIAL | Train64 реально обработан в Actions; extraction train64+development17 проверен там же. В текущем локальном runtime DB нет |
| Execution | BLOCKED | Foundation complete; implementation/tests local complete; candidate development/CPU не исполнились |
| Publication | DRAFT_PR_CREATED | Код и протокол опубликованы; PR46 существует и остаётся draft |

Data PARTIAL описывает достигнутый этап и отсутствие локального measurement payload, а не неполный train: **train обработан полностью**. Успешный foundation job не делает датасет автоматически доступным следующему runner.

## 2. Версии и источник

| Назначение | SHA |
|---|---|
| Baseline R4 | `e3b0c9c039d2953fbfcda51231263d38ef9f1024` |
| Полный baseline tree | `eae49a504bc59b5c9b408445150bef32e111956f` |
| PLAN до измерений | `8d14f9177271a258d1ad280352c61241e4b17e76` |
| **Реально измеренный foundation source** | **`921828787d1c6ee1c79702ee6e1805e330848298`** |
| Первоначальная публикация candidate/driver | `8886578a35b2153136be6a7535dbaed8f67c12d7` |
| **Окончательный candidate source, совпадающий с локально протестированными bytes** | **`14a9aa29a87a9b8e6d33c6b063bed1dac696bde7`** |
| Measured candidate accuracy SHA | **N/A — реальный accuracy replay не выполнен** |
| Foundation checkpoint | `eeb33182e0e2942f7e35fcb6dd55ed9577e01d53` |
| Validation freeze | **N/A** |

ZIP `hack-main-2(20260926-083832).zip`, 3 831 196 байт, SHA256 `a8e0bfa033e0a02c460c30b02f34a5c64ece85b05003512941387d3cf1f319a2`. Встроенный verifier карточки прочитал весь архив и получил ожидаемые301файл/tree; 352 служебных файла __MACOSX исключены. Не просто сравнение нескольких ключевых файлов. Исходный ZIP не изменён, pristine и candidate распакованы в разные каталоги. Remote commit/tree отдельно прочитан через GitHub. .git и .db3 в пользовательском source ZIP отсутствуют; это не мешало локальному импорту, тестам и патчу.

`SOURCE_RECEIPT.json` содержит хеш каждого файла, режим, размер и Git blob. Remote bootstrap дополнительно сверяет все301bytes/modes с Git object перед IO. Не создавался локальный commit с поддельным SHA baseline.

Baseline — настоящий `GuardedReadoutObserver`, полный `champion_v8.yaml` сверяется с JSON и полным набором полей Config. Quarantine1.5, gain1/holdoff.5, adaptation_tau.5, wheel_time_compensation0, 20Hz/alignment0. Не Config defaults/v5/v7. Обычный `guarded_odometry_node` остаётся каноническим.

## 3. Единственная гипотеза и минимальный patch

Пусть F=efficiency*gear*torque/radius, w=max(|v|,1), q — неизменная степенная карта команды.

```text
baseline traction = direction * q * min(F, P/w) / mass
H37 traction      = direction * min(q*F, P/w) / mass
```

Только положительная ветвь `drive_target`. Новый `TractionPowerObserver` наследует исходный guarded observer. Отрицательная/нулевая команда и feature-off делегируются `super().drive_target`; force-limited ветвь сохраняет исходный порядок арифметики. q, deadband, exponent, физика, braking, tau, d-update, фильтр, readout, Timeline и guards не редактируются. Память O(1): одно дополнительное поле enable, без новой истории. Только исходные controller/front/rear; нет GNSS/IMU/future samples/bag IDs/injection flags в runtime.

Это две конкурирующие интерпретации controller, **ни одна не объявлена паспортной**. Изменение target может изменить траекторию и обученное d, хотя уравнение адаптации прежнее. Большая тяга сама по себе не доказывает лучшее предсказание; при неверной интерпретации возможна значительная ошибка model-only.

Чтение предыдущего результата: доступный полный body R3-H24 PR45, fixed-v8 статические q-карты и отрицательный development. H37 не использует его fitted узлы: меняется порядок ограничения, не q-карта. Его метрики не приписываются H37.

Как включить: `TractionPowerObserver(config, readout=readout, enabled=True)`, где config/readout загружены из точного v8-профиля. Один YAML или обычный checkout/launch H37 не активирует. Driver явно создаёт этот класс; class/module path/эффективный config предусмотрены в started.json. Сам checkout candidate уже содержит модуль — повторно применять patch не надо.

SHA256 runtime `traction_power.py`: `0bc92ac6c4b5d5a4804f9e44be8475c7dbe00b2d166f3358f5d4b40b439aeed1`. Git blob `86305053d6c7deb7520cff759e49fdc1648f69e4`. Все4 candidate/runner/test blobs сверены с локальными bytes; связь в REMOTE_SOURCE_BINDING.json.

## 4. Математика и проверка основания

Wolfram реально проверил piecewise-разницу, нулевую разницу при q0/q1, force-limited equality, непрерывность насыщения, неотрицательность разницы для forward direction и верхнюю границу F/(4m). При F>P/w разница равна q(F−P/w)/m до qF=P/w и (1−q)P/(mw) после. Это формулы **на одинаковом состоянии до динамики и clipping**, не теорема устойчивости полного observer. Для reverse direction знак меняется, ограничение относится к модулю.

Worksheet и фактический output с INFO/ambiguity parser для kilogram сохранены. Вывод units N/kg и N записан как получен; паспортные единицы/семантика команды не установлены. Предварительный WolframContext не нашёл результатов по формуле, его нерелевантные snippets не используются. Независимый численный piecewise/bound oracle есть в специальных тестах. Новых Consensus/Scite запросов после известного quota stop не делалось, публикации для элементарной формулы не придуманы.

На точном профиле F=47537.37272411767N, P=280873.5334860941W, граница F=P/w при w≈5.908478264м/с, теоретический максимум разницы target≈0.297108580м/с². Это числа заданной модели, не независимо измеренные характеристики машины.

Foundation до реализации candidate: baseline-only replay на всех64train-bag/27исходных группах. На каждом положительном dt и валидной текущей команде обе формулы вычислялись при **одной и той же native pre-prediction скорости**; возвращались исходные target/Estimate. Все поля состояния и каждый Estimate сравнивались с независимым canonical v8.

Предварительный порог: 0<q<1, power-limited F>P/w, |delta target|>0.02м/с²; минимум200тактов/10с, минимум3группы с20тактов/1с каждая.

| Фактическое train-измерение | Результат |
|---|---:|
| Полные train-bag / исходные группы | 64 / 27 |
| Canonical outputs | 1 366 299 |
| Positive-command ticks | 488 277 |
| Power-limited partial-command ticks | 212 824 |
| Значимые target ticks >0.02м/с² | **209 248** |
| Суммарная длительность значимых ticks | **10 462.4с** |
| Группы, прошедшие локальный coverage threshold | **23** |
| Максимальная разница target | **0.296144857м/с²** |
| Causal errors / resets | 0 / 0 |
| Native state / Estimate equality | Exact на всём train replay |

Покрытие **SUFFICIENT для реализации и следующего сравнения**. Это не 209248 независимых поездок и не gain скорости. Train reference не читался; истинная ошибка ускорения/семантика controller не определялась. Не было fitting или выбора из дополнительных формул. Полные64per-bag строки и все27групп в CSV; оригинал — train/SUMMARY.json foundation artifact.

## 5. Что подготовлено, но НЕ измерено

Development driver использует неизменные score/replay, masks, match/metrics, distance, original fault_windows и group aggregation; заменяется только Observer factory. Legacy aliases сразу переименовываются в full v8/H37/off. Оцениваются опубликованные Estimate.v/s, а не innerv/s. Role loader проверяет настоящую development-роль и DB SHA до read-only SQL. Feature-off дополнительно сверяет каждый базовый state/Estimate. Сравнение synthetic data прошло как проверка реализации, **не real-data accuracy**.

Предусмотрены все17development-bag, штатные4fault-типа, pinned low-speed3/5s и H11 common jumps. Оригинальные anchors/warmup не меняются. Отдельная traction→coast dropout диагностика не заменяет original gain. Каждый original/diagnostic fault повторяется на **полном bag**, сохраняются unchanged scalar distance и signed delta_s на recovery/+10s/end. Это реализовано и проверено на synthetic input, но реальные результаты не получены.

Registered admission: >=2%clean ИЛИ>=5%originalfault gain; clean/fault/pooled regression<=0.5%, clean distance<=1%, per-bag clean<=base+max(.005м/с,5%), одинаковые n/coverage/schedule и отсутствие новых stops/unrecovered/causal/reset. Low-speed/common-mode отдельные veto<=.5%. Full-original-faulted group distance<=1%. Activation>=200изменённыхclean ticks в>=3reference-bearing группах. Ни один gate не смягчён.

| Метрика H37 на реальных development | Значение |
|---|---|
| Clean/fault/pooled RMSE | **N/A** |
| Distance и остаточная delta_s после recovery | **N/A** |
| MAE/p95/bias/recovery и per-bag регрессии | **N/A** |
| Реальные low-speed/common-mode veto | **NOT_EVALUATED** |
| Реальные AB/BA step/replay CPU | **NOT_RUN** |
| Validation / validation-freeze / final test | **NOT_RUN / N/A / NOT_OPENED** |
| Enabled installed ROS, оба clocks, 2CPU/500MB, latency/RSS | **NOT_RUN_EXECUTION_BLOCK** |

Исторические ожидаемые v8 development fingerprints в driver — только будущая проверка воспроизведения. Они **не являются измерением baseline этого candidate-run** и здесь не выданы как новая таблица точности. Отсутствующие результаты не записаны как0.

## 6. Фактические проверки и блокирующий этап

Локально выполнены156originalunit,43research-integrity,22foundation/H37tests — PASS; compile PASS. После публикационного аудита повторены156/43. Отдельный synthetic true-stop probe600шагов дал543STOPPED samples и exact equality baseline. Специальные тесты охватывают q0/q1/force-limited/braking equality, high-speed partial command, continuity/monotonicity/bounds, обе travel directions, off state/Estimate, prefix/future/stale/duplicate/reset/clock/bounded-state, quarantine/zero-lock и интеграл опубликованной скорости на recovery. Наборы пересекаются; повторные прогоны не суммируются как новые независимые тесты.

Foundation [run36230785305](https://github.com/jabrailkhalil/hack/actions/runs/36230785305), attempt1/job108373419925: все шаги success. Там успешно скачан/проверен оригинальный organizerZIP SHA256 `d0b2483e13990edb8219b0d7bbcafc7ed001cce549a4d3af467069b2472e7d52`, извлечены только81train/development DB. На train SQL — только3vehicle-топика. Индивидуальные validation/test DB не извлекались/не открывались.

Development [run36231364281](https://github.com/jabrailkhalil/hack/actions/runs/36231364281): attempt1/job108375024216 и attempt2/job108375241192 — **failure до исполнения шагов**. У первого runner_id=0; steps пусты/null в обоих. Повтор был один, того же job/commit, без изменений кода или параметров. Artifact list пуст. Job logs API вернул404 BlobNotFound; annotations endpoint не поддержан connector. Поэтому конкретная административная причина (quota/billing/runner policy) **не установлена и не объявляется фактом**.

Стандартный CI этого исходного candidate commit, run36231364260:4jobs failure без шагов. Он не объявлен зелёным. Локальные tests и прошлый foundation CI не подменяют failed/неисполненный candidate-run или enabledROS.

Локальный pinned downloader остановился на `URLError: [Errno -3] Temporary failure in name resolution`. Альтернативный browser/container-download маршрут также не получил payload. Поскольку Actions-прогон до этого успешно получил датасет, не утверждается, что данные вообще отсутствуют: **заблокирован доступный путь исполнения candidate-development в этой сессии**. ACL, лимиты и платные ресурсы не менялись.

### Журнал публикационных исправлений до любых candidate measurements

Первоначально при переносе runtime-файла в GitHub была пропущена одна пустая строка после import: семантика совпадала, но bytes не соответствовали локальному CANDIDATE_PINS. Аудит Git blob выявил это. При первом восстановлении строки в9fdfc7a… случайно попал лишний `:` после raise, немедленно исправленный в14a9aa29…. Окончательный blob точно совпадает с исходным локально протестированным модулем. Ни один из этих вариантов не запускался на real data. Это исправления переноса, не дополнительные научные гипотезы/ретюнинг; история не переписана. Коммиты помечены skip-ci, чтобы не изображать очередной старт runner. Первичные failures произошли до любых шагов, поэтому их нельзя приписывать неисполненному SHA-check или syntax-check.

## 7. Артефакты и точное возобновление

Foundation checkpoint: https://github.com/jabrailkhalil/hack/tree/eeb33182e0e2942f7e35fcb6dd55ed9577e01d53/reports/research_R4/H37/foundation-36230785305-1

Artifact `R4-H37-foundation-36230785305-1`, ID10902488452, ZIP SHA256 `f3d1f5fc8324f7f4d9ec0a0ae03583abb4caee7326791d255d581f888b27904c`,155374байта, retention до2026-10-26 08:48:47UTC. Checkpoint не зависит от artifact retention. Локальный пакет сохраняет неизменённый ZIP, source receipt/verifier, patch, exact code/config/PLAN, raw foundation, CSV, логи и блокировку.

**Следующий разрешённый этап — первый candidate development**, не повтор fitting/train, не validation. Команды ниже — рецепт возобновления после восстановления execution/data path; строки development/cost **не выдаются за уже выполненные**:

```bash
git fetch origin research/R4-H37 checkpoint/R4-H37-foundation-36230785305-1
git worktree add --detach ../hack-R4-H37 14a9aa29a87a9b8e6d33c6b063bed1dac696bde7
cd ../hack-R4-H37
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-research.txt
export PYTHONPATH=src/reserve_odometry
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
export H37_MEASURED_SHA=$(git rev-parse HEAD)
python research/R4/H37/bootstrap.py
OUT=$(mktemp -d /tmp/R4-H37-resume-XXXXXX)
git show eeb33182e0e2942f7e35fcb6dd55ed9577e01d53:reports/research_R4/H37/foundation-36230785305-1/train/SUMMARY.json > "$OUT/FOUNDATION.json"
echo "b45b188bcfd2e321fe107759de78b8935993b6c69371d02edf49a417bc520591  $OUT/FOUNDATION.json" | sha256sum -c -
python -m unittest discover -s research/R4/H37/tests -v
python research/R4/H37/prepare.py --output "$OUT/preparation"
python research/R4/H37/development.py --foundation "$OUT/FOUNDATION.json" --output "$OUT/development" --workers 2
python research/R4/H37/cost.py --development "$OUT/development" --output "$OUT/cost"
```

Output dirs новые; raw source/profile/scorer неизменны. Python3.13.5/NumPy2.3.5/SciPy1.17.0 использованы локально и в foundation. Отрицательный development закрывает допуск; положительный требует отдельного опубликованного freeze до единственного validation. Workflow не запускает validation автоматически. Никаких фоновых будущих измерений не обещается.

**Итог: baseline сохранить. Foundation достаточен, патч есть, но научный accuracy verdict — NOT_EVALUATED из-за execution block; merge readiness=false.**
