# R4-H41 — NOT_EVALUATED: источник проверен, train-диагностика заблокирована

**Исследовательский артефакт, не готов к merge. Совместный runtime-observer [v, drive_a] НЕ реализован.** Проверены полный исходный снимок, неизменённые baseline-тесты, пассивная диагностика и математические формулы. Ни одного реального train/development replay в этом исследовании не завершено. Поэтому нельзя объявлять H41 ни подтверждённой, ни отвергнутой, ни имеющей нулевой эффект.

## 1. Точные версии и независимые статусы

- Baseline commit: `e3b0c9c039d2953fbfcda51231263d38ef9f1024`.
- Baseline tree: `eae49a504bc59b5c9b408445150bef32e111956f`.
- ZIP SHA256: `a8e0bfa033e0a02c460c30b02f34a5c64ece85b05003512941387d3cf1f319a2`, 3 831 196 байт.
- Полностью проверены **301 файл проекта, пути, bytes, executable bits**; 352 служебных файла macOS исключены. Снимок не реконструирован по excerpts. `.git` и bag DB в ZIP отсутствуют.
- Канонический `GuardedReadoutObserver`, профиль `champion_v8`, опубликованные `Estimate.v/s`, 20 Hz, alignment=0, readout=1/.5, adaptation=.5, wheel_time_compensation=0, common quarantine=1.5. Эффективные model-параметры взяты из YAML и сверены с JSON.
- Собственная ветка: `research/R4-H41`, создана от точного baseline после пустых поисков полного scientific ID в ветках/PR/checkpoint.
- [PLAN](../../../../research/R4/H41/PLAN.md) опубликован **до измерений** коммитом `40acde8b32ecceac5cb4b9099ef6ba22ff5740d1`.
- Исходник диагностического workflow: `d9b41ab16a44db9793408faabf9b33479141e861`. Это **attempted diagnostic source**, не measured candidate SHA.
- **Candidate/measured-source SHA = N/A. Freeze SHA = N/A.** Поздний report SHA указывается отдельно в SUMMARY/PR; он не является измеренным алгоритмом.

| Поле | Значение |
|---|---|
| source_status | VERIFIED |
| data_status | UNAVAILABLE |
| execution_status | BLOCKED |
| scientific_verdict | NOT_EVALUATED |
| candidate_implemented | false |
| accuracy_contract_evaluated / passed | false / false |
| enabled_runtime_verified / ready_to_merge | false / false |

Запись GitHub фактически работала: создана ветка, опубликованы PLAN, диагностический код и workflow. Publication не является причиной отсутствия измерений. Состояние публикации итогового PR фиксируется отдельной поздней метаданной, после ответа GitHub.

## 2. Где действительно остановилось выполнение

### Локальная среда

В `/mnt/data` не найдено `.db3`, `.mcap` или архива `dataset.zip`; в выделенном data root отсутствуют все **64 train** и **17 development** bags. Это результат проверки рабочей среды, не утверждение о содержимом личной Library.

Фактический запрос к закреплённому Yandex download API завершился `URLError(gaierror(-3, 'Temporary failure in name resolution'))`. GitHub DNS также недоступен локально, хотя авторизованный connector работает. Дополнительный путь через web/download не получил payload. Локальный запуск `--stage foundation` проверил источник, записал started.json и завершился **exit 1** на отсутствующем `30618_0259fe53_0.db3`, до SQLite/декодирования. Это **не результат Foundation INCONCLUSIVE**, а отсутствие выполненной научной проверки.

### GitHub Actions

[Run 36231187948, attempt 1](https://github.com/jabrailkhalil/hack/actions/runs/36231187948) действительно создан и завершился **failure**. [Job 108374529866](https://github.com/jabrailkhalil/hack/actions/runs/36231187948/job/108374529866):

```text
created/started: 2026-09-26T08:54:36Z
completed:      2026-09-26T08:54:37Z
runner_id: 0
runner_name: ""
steps: []
artifacts: []
```

Runner не назначен; checkout, установка зависимостей, tests и data download **не выполнялись**. Получение лога вернуло **404 BlobNotFound**. Check-run annotations недоступны через разрешённые endpoint текущего connector. **Причина отсутствия runner не установлена**: нельзя выдавать догадку о billing/quota/permissions за обнаруженный факт. Новый автоматический retry не запускался; чужие jobs и настройки не менялись, вычисления не покупались.

Поздняя workflow-версия сделана **manual-only**. Добавлены только рекурсивное копирование вложенных math-файлов и явная SymPy-зависимость/проверка; это инфраструктурная подготовка следующего явного запуска, не новый эксперимент и не изменение scientific PLAN. Исторический workflow исходного неудавшегося run доступен по его SHA. Общий `ci.yml` и его guards не переписаны.

## 3. Что является реальным кодом этого этапа

`research/R4/H41/foundation.py` — пассивный train-only probe. Он исполняет canonical v8 и вне его состояния запускает три коротких shadow forecast с начальным A, A+.1 и A−.1 м/с², одним и тем же прошлым v/d, реально получаемыми командами и неизменной схемой drive-before-Euler. Колёсные endpoints используются только после завершения горизонта как псевдоразметка, не как состояние рекурсивного прогноза.

Ограничены один активный shadow-эпизод и частота якорей; таблицы/массивы для последующего анализа накапливает **offline collector**, а не runtime-нода. Сам probe **не изменяет опубликованную скорость, дистанцию, d, A, covariance или guards канонического наблюдателя**. Функция его прогнозирования проверена на равенство исходному MODEL_ONLY predictor.

Loader проверяет original role и checksum перед measurement IO, train допускает только controller/front/rear, development — reference только внешнему scorer. Вызовы validation/test запрещены. Downloader использует исходный pinned dataset hash и извлекает только train/development DB members; локально и удалённо до успешного скачивания он не дошёл. Распаковку/размеры/CRC/хеши реального датасета этим запуском **нельзя считать проверенными**.

Предзарегистрированная foundation требует ≥100 transient pairs в ≥5 группах; ≥30 завершённых эпизодов в ≥5 группах; ≥50% эпизодов с чувствительностью ≥.01 м/с; transient innovation RMS≥.01 м/с в ≥5 группах. **Фактические значения — N/A**, не 0. Правила не менялись после сбоя.

Совместная коррекция `[v,A]`, effective constrained Ka, covariance reset/clipping и actual-prior/Kv/a readout hook остаются **не реализованными**. Нельзя назвать новый файл с математикой реализацией всего наблюдателя или считать исходный ROS launch включённым H41.

## 4. Фактически выполненные проверки

| Проверка | Результат и объём |
|---|---|
| Полный source verifier | 301/301, exact tree/modes |
| Неизменённый unit suite v8 | 156/156 PASS локально |
| Неизменённый research-integrity suite | 43/43 PASS локально |
| Foundation unit tests | 8/8 PASS локально |
| Oracle parity пассивного predictor | 200 произвольных допустимых MODEL_ONLY шагов, exact |
| Пассивный synthetic replay before/after | outputs и runtime-счётчики совпали |
| Jacobian finite differences | 808 случаев, max abs delta 9.07199870781028e−10 |
| Joseph scalar vs независимое matrix multiplication | 5000 PSD случаев, max abs delta 1.7763568394002505e−15 |
| PSD minimum eigenvalue в этой выборке | 1.7749393284097192e−6 |
| SymPy identities / units | PASS |
| Wolfram worksheet | Фактически исполнен, output сохранён |
| compileall | PASS |

Jacobian включает оба направления, тягу/торможение, отдельные ветви saturation/no-reversal вдали от недифференцируемых точек. Joseph-проверка включает Ka=0, исходный gain и ограниченный effective gain. **Это algebra-only helper, не проверка covariance внутри включённого H41.** Полные журналы локальных тестов включены в пакет evidence. Поднаборы не суммируются как независимые научные эксперименты.

Среда: Python 3.13.5, NumPy 2.3.5, SciPy 1.17.0, SymPy 1.14.0. Локально отсутствуют ROS/rclpy и Docker. Это не утверждение о недоступности ROS на всех возможных удалённых средах.

## 5. Математика и существенные ограничения

Для точной дискретной схемы вне clipping:

```text
rho = exp(-h/tau)
A_next = rho*A + (1-rho)*T(u,v)
v_next = v + h*(A_next-R(v)+d)
F = [[1+h*((1-rho)*T_v-R_v), h*rho],
     [(1-rho)*T_v,             rho]]
```

Wolfram/SymPy подтвердили этот Jacobian. При frozen target и постоянном resistance детерминант наблюдаемости `h*rho`; он не доказывает наблюдаемость произвольного общего wheel bias и неизвестного d вместе. При неотрицательном noise и PSD prior полная Joseph-форма остаётся PSD для произвольного конечного **фактически применённого** K, включая Ka=0/ограничение.

Проверенный пример важности actual-prior hook: при реальном Pvv−=.2 и R=.01 получаем **Kv=20/21≈.952381**. Подстановка legacy prior .105 в восстановление gain из Ppost даёт **401/441≈.909297**, другую величину. Это численный контрпример формулы, **не измеренный defect rate на bags**.

PLAN фиксирует S_A=.09 (м/с²)² как инженерную априорную, не identified covariance. Предусмотренное h²S_d учитывает лишь независимую step-local ошибку d. При неизвестном постоянном d дисперсия интегрированной ошибки растёт как T², не hT: на n шагах toy-отношение равно n. Поэтому это не гарантированная оболочка истинной ошибки и не доказательство calibrated CI. Никакая из этих проверок не заменяет эксперимент и safety probes полного переключаемого observer.

## 6. Что НЕ выполнено

Реальные foundation coverage/excitation/residuals; full-v8 development reproduction; joint candidate implementation; candidate feature-off/state equality; actual gain hook test; nonlinear load/false-return/ramp candidate probes; paired clean/original/low-speed/common suites; full-faulted-bag distance и остаточная delta_s; healthy/active step/replay CPU AB/BA; positive-development freeze; validation; enabled installed ROS benchmark. **Все численные метрики этих этапов null/N/A.** Historические H10/H18/v8 цифры не подставлены вместо результата H41.

Validation и final/test measurement payloads не открывались. Никаких новых коэффициентов после просмотра validation, дополнительных вариантов или скрытого rescore не было; `variants_tested=0`. Статус `NOT_RUN_AFTER_REJECTION` неприменим: rejection кандидата не происходил.

Изучены результаты PR18/H10, PR37 и PR38/H18, PR42/R3-H26, machine-readable SUMMARY PR37 и источник low-speed suite PR13. Наблюдаемые там риски мотивируют PLAN, но не являются новыми измерениями H41. Полный код low-speed helper ещё не перенесён в новый development runner, который также не реализован. Consensus/Scite повторно не опрашивались после известного quota stop; внешняя публикация для элементарных формул не выдумана. Уровень чтения перечислен в SOURCES.md.

## 7. Воспроизведение и точка продолжения

В полном checkout исследовательской ветки, с доступным исходным baseline object:

```bash
python3.13 -m venv .venv-h41
. .venv-h41/bin/activate
python -m pip install -r requirements-research.txt -r research/R4/H41/requirements-math.txt
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
OUT=$(mktemp -d /tmp/H41-replay.XXXXXX)
PYTHONPATH=src/reserve_odometry python -m unittest discover -s tests -v
python -m unittest discover -s research/tests -v
python -m unittest discover -s research/R4/H41 -p test_foundation.py -v
python research/R4/H41/math/check.py --output "$OUT/algebra.json"
python research/R4/H41/foundation.py --stage source --output "$OUT/source.json"
# Следующие команды требуют данных/сети и в текущем проходе НЕ завершены.
python research/R4/H41/foundation.py --stage data --output "$OUT/input"
python research/R4/H41/foundation.py --stage foundation \
  --data-root "$OUT/input/data" --output "$OUT/foundation"
```

При работе из ZIP без Git: сначала выполнить приложенный `verify_source.py <archive> --report <new-receipt.json> --extract <new-pristine>`, применить диагностический patch в отдельной копии, затем передавать `--source-receipt <new-receipt.json>` в стадии source/foundation. Локальный snapshot commit не выдаётся за remote baseline SHA. Existing output не перезаписывается.

**Следующий этап — ровно существующая train-only foundation на доступном checksum-identical датасете или после восстановления runner.** Только после её допуска допустима реализация единственного зарегистрированного кандидата. Для этого не нужно менять baseline, создавать второй scientific ID или открывать validation. Main/чужие ветки/опубликованные отчёты не изменены; merge/auto-merge не выполнялись.
