# R5-H45 — NOT_EVALUATED / DEPENDENCY_PENDING

**Исследовательский checkpoint, не готов к merge.** Выполнена только H45: остаточная калибровка колёс после перевода км/ч → м/с. H35 не продолжалась. Создан [draft PR №60](https://github.com/jabrailkhalil/hack/pull/60). Реализован и проверен неоткалиброванный runtime-прототип; обученной калибровки и сравнения точности на реальных записях нет. Это не REJECTED гипотезы и не подтверждённое улучшение.

## Версии и исходники

Baseline `b2783206000091ab11a1c11ac3ff79082188a4fb`, полный Git tree `973d50d288e050325ee1c71a90fa8d81f2a099af`. Проверены все **320 файлов**, пути, bytes и executable bits нового source ZIP; remote commit→tree binding прочитан отдельно через GitHub. ZIP SHA256 `4823fbdbbb979d7b561841e2831e68f2f7d9d8ec0d14e970f09a38cd51dff4c4`. Старый R4 snapshot не подмешивался. Все исходные 320 файлов остались неизменными.

PLAN опубликован до реализации: `1ffef5ff428b2d17578f46589b1f37f3c9eb1ee8`. Протестированный source прототипа: **`d17aeb632a1dc79a3b7369317d5380879d25e97b`**, tree `a24f2d315feb307d7e2c3fc0acb68caaf1d7d559`. Локальный tree точно совпал с созданным через API. Локальный snapshot commit не выдаётся за remote ancestry. Source проверялся локально до публикации кода; real-data experiments не было.

`measured_candidate_sha`, `calibration.json`, `freeze_sha` и `DEPENDENCIES.lock.json`: **N/A, не созданы**. Report-only commit указан отдельно в PR/DELIVERY, не подменяет tested prototype source. Ветка `research/R5-H45`; main, другие ветки, старые отчёты и guards не менялись. Merge, auto-merge и force-push не выполнялись.

## Точный блокер

В Library найдены реальные записи обоих обязательных компонентов, а не только ссылки из сообщений:

| Компонент | Ожидаемый размер | Результат получения bytes |
|---|---:|---|
| `R5_H42_teacher_component.zip` | 28 190 115 байт | Materialization отказала |
| `R5_H43_atlas_handoff.zip` | 1 076 521 байт | Materialization отказала |

Для каждого `files.materialize` вернул: **`This Project file does not have an authorized raw-byte materialization path.`** Ошибка не обходилась. Нельзя утверждать, что записи отсутствуют: они найдены; недоступны именно bytes. PR56/H42 и H43 DELIVERY прочитаны, но receipt и описание не заменяют полный manifest/NPZ. Producer components заново не генерировались.

Dataset получен отдельным успешным элементом той же операции: 256 294 592 байта, SHA256 `d0b2483e13990edb8219b0d7bbcafc7ed001cce549a4d3af467069b2472e7d52` проверен полностью. Это hash архива, не отдельная проверка DB: базы **не распаковывались и не открывались**.

Оригинальный wave2 `precheck_components.py` запущен с ожидаемыми путями и вернул exit 2: `COMPONENT_TRANSPORT_FAILED: ZIP missing or wrong byte length: .../R5_H42_teacher_component.zip`. Не созданы ложные transport receipt, extraction directory или dependency lock. Native teacher verifier, native atlas verifier и bridge фактических producer folds не выполнены. Копия coordinator folds не выдавалась за actual payload verification.

Ожидаемые ZIP hashes: teacher `2ee08edb32343350bf6ae6202836644de4fb309640f2d140a1eb9d5791af28b8`; atlas `6a759f4bafe4ece014e9dd4f25b201549e317f2ca9db7b47b6c15d4443d9b011`. Остальные source/manifest/fold pins сохранены без изменений в `research/R5/H45/DEPENDENCIES.expected.json`; этот файл **не lock**.

## Что именно реализовано

`research/R5/H45/runtime.py` содержит `ResidualScaleObserver`, subclass полного `GuardedReadoutObserver`. Положительные постоянные cf/cr в диапазоне [0.97,1.03] умножают уже приведённые к м/с скорости. Перевод 1/3.6 остаётся в прежнем adapter/loader. Нет additive offset, bag-specific parameters, online learning, GNSS/IMU либо fault-oracle.

Масштабированные held samples передаются согласованно core и readout. Controller и timestamps не меняются. Исходный raw `_wheel` gate вызывается дополнительно на малом gate-state: это не второй фильтр движения. Уменьшение масштаба не устраняет raw range/rate rejection; исправленные значения также проходят исходные проверки. Raw H11 quarantine распространяется на observer. Disabled и enabled identity делегируют прямо canonical v8. Дополнительные структуры фиксированного размера; новые длинные очереди отсутствуют.

`factory.py` загружает **все** параметры `champion_v8.yaml`, сверяет hash и полноту полей, проверяет 20 Гц, delay 0, исходные единицы. Не используются Config defaults. Обычный checkout/ROS launch **не включает H45**. Только явная research factory создаёт прототип; значения в tests — синтетические fixtures, не подобранные параметры. Не доставлены обученный профиль, teacher-to-interval fitting adapter, solver и real paired comparison runner: до проверяемого payload schema они не реализовывались.

Протокол ограничивает будущий fitting двумя структурами: общий c и cf/cr с единственным фиксированным prior к общему. Фolds, solver budget, check rule, L-gates, full-faulted-bag distance, запрет менять маски и условия допуска к validation уже записаны в PLAN. Это план, а не выполненные измерения.

## Фактически выполненные проверки — LOCAL

| Проверка | Фактический результат |
|---|---:|
| Канонические unit tests | 161 PASS, 0 FAIL |
| Research integrity | 43 PASS, 0 FAIL |
| H45 synthetic tests | 32 PASS, 0 FAIL |
| Компиляция Python | PASS |
| SymPy identities | 8 PASS + численный counterexample |
| Применение патча на чистом baseline | PASS, те же 32 tests повторены |
| Сохранение исходных файлов | 320/320 неизменны |

Off и identity сравнивались по всем inherited fields/Estimate на 6000 шагах каждый. Прототип сравнивался с независимым canonical observer на отдельно масштабированном чистом потоке, 1000 шагов. Проверены raw/corrected range/rate, H11, stale/future/duplicates/reset, reverse bootstrap, true zero stop, common zero-lock, causal prefix. Структура состояния проверена на 10000 шагах. Published v, a и интеграл s согласованы на синтетических потоках с отказами; накопленная delta_s не обнуляется при recovery. Повтор тестов не считается дополнительными независимыми экспериментами.

SymPy 1.14.0 использован как разрешённый независимый oracle, не Wolfram. Исполнены нулевой/знаковый инварианты, масштабирование трапецеидального интеграла входной скорости, stationary formula weighted OLS и common-gauge ambiguity. OLS — только математическая проверка, не реализация будущего Huber fitting. Один и тот же observed pair (10,10.2) совместим как с истинной скоростью 10 и GNSS gain1.02, так и со скоростью10.2 и wheel gain1/1.02. Поправка к GNSS proxy не является доказанной аппаратной шкалой. Bounded c не доказывает устойчивость переключаемой нелинейной системы; sign teacher остаётся неизвестным.

Среда: Python3.13.5, NumPy2.3.5, SciPy1.17.0, SymPy1.14.0, Linux x86_64. Научные библиотеки отсутствуют в runtime imports. Выполнение локальное; GitHub Actions не используется как доказательство. Нет утверждений о новом successful CI, installed enabled ROS, CPU/latency/RSS benchmark.

## Непроведённые стадии и честные метрики

`fit_objective_calls=0`, `variants_tested=[]`, `real_bag_replays=0`. Calibration source и validation FREEZE отсутствуют. Все реальные RMSE, MAE, bias, distance, recovery, false-stop и per-bag/group результаты — **N/A**, не0. Исторические цифры v8/H42/H43 не переписаны как H45 measurements. Научных real-data регрессий или выигрышей пока не измерено. Canonical tests могут проверять исторические артефакты, но новые measurement payloads/DB не читались.

Статусы: `source_status=VERIFIED`; `data_status=PARTIAL`; `dependency_status=DEPENDENCY_PENDING`; `execution_status=CHECKPOINTED`; `publication_status=DRAFT_PR_CREATED`; `scientific_verdict=NOT_EVALUATED`; `runtime_prototype_implemented=true`; `candidate_implemented=false` (нет обученного кандидата); `accuracy_contract_evaluated=false`; `enabled_runtime_verified=false`; `ready_to_merge=false`.

## Воспроизведение доступного этапа

```bash
git fetch origin research/R5-H45
git worktree add --detach ../hack-H45 d17aeb632a1dc79a3b7369317d5380879d25e97b
cd ../hack-H45
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-research.txt 'sympy==1.14.0'
export PYTHONPATH=src/reserve_odometry
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
python -m unittest discover -s tests -v
python -m unittest discover -s research/tests -v
python -m unittest discover -s research/R5/H45/tests -v
python -m compileall -q src research/R5/H45
python research/R5/H45/math_check.py
```

Для source ZIP вместо Git: применить `H45-prototype.patch` к verified pristine baseline, затем выполнить команды tests. Патч добавляет только research-файлы, не заменяет core. Native payload preflight нужно продолжить с оригинальным launch packet и реальными двумя ZIP, используя его команды. Не угадывать пути folds внутри компонентов; установить их по полным producer manifests. После transport, обоих native verifiers и фактического folds bridge создать новый DEPENDENCIES.lock, только затем реализовать schema-bound adapter и выполнить два предусмотренных fitting. Новый PLAN/новые варианты из-за транспортного сбоя не нужны.

Полные журналы, исходный SOURCE_RECEIPT на320файлов, CHECKS, MATH, EXECUTED_CONFIGURATION, DEPENDENCY_STATUS и проверка патча переданы в conversation package. Ни dataset, ни teacher arrays, ни чужие raw traces в пакет не входят. В Git — compact REPORT/SUMMARY/проверки; срок доступности conversation artifacts не гарантируется.
