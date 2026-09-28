# R5-H46 — DEPENDENCY_PENDING / NOT_EVALUATED

**Исследовательский checkpoint, не готов к merge.** Подготовлены интерфейс выбора профиля, ограниченные математические примитивы и проверки. Калибровка H46 не выполнялась, полного fitting/evaluation runner кандидата пока нет. Это не REJECTED и не INCONCLUSIVE по научному основанию: обязательные входные компоненты недоступны для чтения байтов. Фактически завершён только baseline-only preflight.

## Конкретный блокер

В Library найдены оба требуемых артефакта: `R5_H42_teacher_component.zip` (28190115 байт) и `R5_H43_atlas_handoff.zip` (1076521 байт). Одна попытка получить оба файла через Files завершилась для каждого сообщением:

> This Project file does not have an authorized raw-byte materialization path.

Это не отсутствие записей в Library и не недоступность исходного dataset. GitHub receipts прочитаны: они явно называют ZIP отдельными conversation attachments, не Actions artifacts; receipt не заменяет полный manifest и массивы. Обход ограничения, перезапуск H42/H43 или регенерация teacher не выполнялись. В launch-пакете есть ожидаемые pins и договорённости, а не 85+53 payload files.

Точные ожидаемые ZIP SHA256:

- teacher: `2ee08edb32343350bf6ae6202836644de4fb309640f2d140a1eb9d5791af28b8`;
- atlas: `6a759f4bafe4ece014e9dd4f25b201549e317f2ca9db7b47b6c15d4443d9b011`.

Не выполнены native payload verifiers, bridge по фактическим producer folds и создание `DEPENDENCIES.lock.json`. `DEPENDENCIES.expected.json` не выдаётся за такой lock. Вызов собственного dependency_probe вернул ожидаемый exit 3, training_authorized=false. Transport-success также не авторизует fitting.

## Baseline, план и версии

Baseline: `b2783206000091ab11a1c11ac3ff79082188a4fb`; полный tree `973d50d288e050325ee1c71a90fa8d81f2a099af`. Удалённый commit/tree прочитан через GitHub. Ветка `research/R5-H46` создана от этого commit после поиска точного ID: предыдущего H46 не найдено.

Полные 320 исходных файлов, их bytes и executable bits сверены неизменным verifier. SHA256 пользовательского ZIP: `4823fbdbbb979d7b561841e2831e68f2f7d9d8ec0d14e970f09a38cd51dff4c4`. Dataset ZIP: `d0b2483e13990edb8219b0d7bbcafc7ed001cce549a4d3af467069b2472e7d52`; извлечены и проверены 64 train и 17 development DB, без validation/test DB.

PLAN опубликован до измерений коммитом `58a016757701c689647dfb0429638516c1b7d00b`. Интерфейсный source опубликован как `cbb50a41f48c0f92e51ff5098fb23e18522756cc`. Локальный измеренный baseline-preflight source: `a54438a74c7f169daf6761a13a3210d36a55db72`. Его родитель — локальный снимок с проверенным tree, НЕ удалённый baseline commit. Эти две истории не подменяются друг другом. Шесть опубликованных PLAN/code/test/verifier blobs сверены с локальными bytes — совпадают.

**Candidate SHA=N/A; fitted parameters=N/A; validation freeze SHA=N/A.** Interface source SHA не является SHA обученного кандидата. Более поздний report commit не является новым измерением.

## Механизм и реализованная часть

Гипотеза: общая и отдельная F/P/B калибровка для metadata labels 30618/30639 с одним фиксированным shrinkage может уменьшить межмашинное смещение. Физическое соответствие labels не подтверждено; это будущая CONDITIONAL_ON_CONFIG оценка, не автоматическое распознавание машины.

`runtime_profile.py` читает полный pinned champion_v8.yaml. Выбор производится один раз из явного vehicle_profile. Unknown/disabled возвращают точный v8, включая Estimate, readout, quarantine и состояние; имя bag не разбирается. Known enabled profile без полного artifact явно отклоняется. Меняться разрешено только total_motor_torque_nm, max_power_w, max_brake_force_n; наследованный GuardedReadoutObserver не получает новых входов или динамических состояний. Неправильный известный профиль автоматически не распознаётся — тест проверяет, что его последствия не скрыты.

Артефакт допускает ровно global и два label-вектора, без per-bag полей, с hashes training/dependency manifests. Проверка схемы не доказывает происхождение: native dependency verification и связь с настоящим fitting обязательны. Числа в synthetic_artifact() — только unit fixture с фиктивными hash-заглушками; файла global_and_vehicle_parameters.json нет. Checkout, текущий YAML и canonical ROS launch НЕ включают H46.

`calibration_spec.py`: fixed lambda=0.1; аналитическое исключение общей средней из равного quadratic shrinkage; soft_l1 data-only residual, сохраняющий prior квадратичным; общий счётчик <=1000 residual invocations. Запланированы один joint fit и один matched global-only control, max_nfev=80 каждый, без restarts. Выполненных real-data objective calls: **0**. Полный потребитель teacher, выбор окон, rank и fitting ещё не реализованы/не исполнены; формулы и ограничения заранее закреплены в PLAN, а не выдаются за пройденные этапы.

## Реально исполненный baseline-only replay

Использовались неизменные `evaluate.replay/score`, matching/distance и `research_v6.summary`. Временная factory подставляет canonical GuardedReadoutObserver, не старый v5, без изменения файлов evaluator. Legacy aliases baseline_v2 и balanced_physics означают два независимых экземпляра v8, НЕ кандидата или новую калибровку.

Read-only loader допускает только исходный development, проверяя роль до hash/SQL. GNSS-поля передаются внешнему scorer, но не observer; runtime получает только controller/front/rear. Fault anchors, masks, output 20 Hz/delay0 и crop windows сохранены. Все 320 исходных файлов повторно сверены после replay. Отдельно выполнена exact array/counter parity canonical против feature-off на каждой из 17 clean-записей.

| Метрика — только заново исполненный v8 | Значение |
|---|---:|
| Clean group-macro RMSE, м/с | 0.09266814298282507 |
| Original fault-event group-macro RMSE, м/с | 0.2375486120563008 |
| Pooled clean RMSE, м/с | 0.1293056944774334 |
| Scalar-span distance group-macro RMSE, м | 5.310295004801444 |
| Matched receiver-time comparisons | 394221 |
| False stops clean / fault | 0 / 0 |
| Неподтверждённые recovery original scorer | 4 |

17 bags /7 source groups; 19 clean reference pairs; 56 original fault scenarios /60 reference comparisons. В clean replay каждого варианта 318865 выходных моментов, включая записи без reference. Два GNSS receiver не считаются независимыми поездками. Все пять fingerprint-полей совпали с ожидаемым baseline с delta=0.0. Это воспроизведение стенда, не независимое обобщение или результат H46. Per-bag/receiver/fault и per-label/group baseline значения сохранены, missing reference остаётся null.

**H46 clean/fault/distance, per-label gain, coverage/rank и регрессии — N/A.** Подмена этих полей нулём или чужими результатами H36 запрещена. Candidate full-faulted-bag/low-speed/common-mode проверки не запускались.

## Выполненные проверки

| Набор | Результат |
|---|---:|
| Исходные runtime unit tests | 161 PASS |
| Исходные research-integrity | 43 PASS |
| H46 interface/optimization primitives | 25 PASS |
| Baseline-only loader/fault/overwrite adapter | 5 PASS |
| Неизменные launch transport/fold helper tests | 13 PASS |
| compileall | PASS |

Дополнительно: отключённый путь сравнен по всем базовым полям и Estimate на 2000 синтетических шагах; unknown-profile cases не делают filename inference; проверены future/stale/duplicates/reset/bounds и защитные случаи на тестовых коэффициентах. Budget tests используют фиктивную функцию и не означают расход research fitting budget. Тесты transport helpers не являются проверкой недоступных payload файлов.

Wolfram фактически подтвердил центр (theta1+theta2)/2, penalty lambda*(theta1-theta2)^2/(2*s^2), нулевое общее направление Hessian и равенство преобразованного residual soft-L1 loss. Shrinkage не доказывает идентифицируемость данных; известный профиль не становится достоверным физическим ID. Worksheet/вывод и допущения включены в локальную поставку. Предшествующий semantic запрос не дал конкретного алгебраического решения и не использован. Новые Consensus/Scite запросы/покупки не выполнялись.

Python 3.13.5, NumPy 2.3.5, SciPy 1.17.0; OPENBLAS/OMP=1. Baseline replay wall=75.709317569 с — это offline вычисление, НЕ runtime latency. ROS build, enabled H46 deployment в обоих clock modes, node RSS и latency под 2CPU/500000000bytes НЕ выполнялись. Все перечисленные tests/replay выполнены локально. GitHub CI success не заявляется; новых workflow или ручного запуска Actions нет.

## Воспроизведение и поставка

Из опубликованной ветки непосредственно повторяются 25 H46 interface tests:

```bash
PYTHONPATH=src/reserve_odometry:research/R5/H46 python -m unittest discover -s research/R5/H46 -p test_h46.py -v
```

Полный архив checkpoint в разговоре дополнительно содержит baseline_preflight.py, PINNED_FILES.json, source/data receipts, первоначальные contracts/tools, 5 adapter tests, per-bag JSON/CSV, access и логи. Они сохраняются отдельно от upstream payloads. Нативных H42/H43 массивов, raw DB, нового teacher, candidate coefficients или validation результатов в поставке нет. Это не Actions artifact; retention разговора не гарантирован. Минимальный исполнимый интерфейс, PLAN и отчёт сохранены в GitHub.

Полный source-only patch применять к чистому точному baseline b278..., не повторно поверх Git-ветки с уже добавленными файлами. В полном локальном checkout/после такого patch:

```bash
python -m pip install -r requirements-research.txt
export PYTHONPATH=src/reserve_odometry:research/R5/H46
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
python -m unittest discover -s research/R5/H46 -p 'test_*.py' -v
python research/R5/H46/baseline_preflight.py --data-root "$DATA" --output "/tmp/H46-baseline-$(date +%s)-$$"
```

Следующий разрешённый этап: получить именно два pinned component ZIP, выполнить transport + оба producer-native verifiers + bridge на фактических folds, создать dependency lock. Затем реализовать и выполнить заранее описанные teacher coverage/rank и ограниченный fit. До этого обучения/выбора кандидата нет. Параметры, роли и gates не меняются. Validation допускается только после положительного candidate development и отдельного опубликованного freeze; final test остаётся закрытым.

**Итог: NOT_EVALUATED, а не отрицательный эксперимент H46.** main, чужие ветки, прошлые отчёты, маски и runtime default не изменялись; merge/auto-merge не выполнялись.
