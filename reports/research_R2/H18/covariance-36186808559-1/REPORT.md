# R2 H18 — REJECTED: covariance при удерживаемом disturbance

**Исследовательский отрицательный результат, не готов к merge.** Механизм активен и меняет scalar gain и траекторию после возврата колёс. Минимальный выигрыш общего контракта не достигнут: clean RMSE лучше только на 0.000361704%, original fault RMSE не изменился. Численные пороги не смягчались, параметры после validation не менялись. Default и canonical launch не переключены на H18. Не merge/auto-merge.

## Версии и последовательность

- Round: R2-v7-fixed. Baseline `65bba39ed05c781f3f69a65c02f69931152cbfd9`, **GuardedReadoutObserver**, профиль `guarded_readout_v7.yaml`, readout gain=1/holdoff=0.5, wheel_time_compensation=0, adaptation_tau_s=0.5; 20 Hz, alignment delay=0.
- Предварительный PLAN: `49c1dc325e16fda09404e639f46eba820f54a6f7`, до экспериментов.
- Измеренный код/driver: `9ff728d0a06b25b5a4c2da86a2337aa1157e8ce9`.
- Отдельный опубликованный freeze ДО validation: `fa2d27962c2858b69a7ed68a86dccafe24bfc145`. FREEZE создан 2026-09-25 20:41:35 UTC; validation started 20:41:40 UTC, после commit/push.
- Полные raw evidence: `149d175f310d9062309bd690b7bdbff23d15bf31`, checkpoint `checkpoint/R2-H18-covariance-36186808559-1`.
- Ветка: `research/round2-H18-covariance-20260925`. Запрошенное имя `research/round2-H18` уже существовало на `2ddf918ec990085f070caed003e24b616ce27fe8`; оно не перезаписывалось, его результаты не читались и не использовались для настройки.

[Исследовательский run 36186808559](https://github.com/jabrailkhalil/hack/actions/runs/36186808559) завершён успешно как исполнение эксперимента, **не как приёмка гипотезы**. Этот отчёт добавлен позднее измеренного кода; source/config/evaluator не изменены после freeze. Все сравнения относятся к закреплённому R2 baseline, не к движущемуся main и не к старому adaptive_v5 без guarded readout.

## Изменение алгоритма

Добавлен отдельный `OutageCovarianceObserver` (105 строк); старые core, guarded_readout, Timeline, ROS node, профили и физические коэффициенты не переписаны. Runtime импортирует только math и существующие runtime-модули; нет NumPy/SciPy, GNSS/IMU, bag ID, reference, fault oracle или будущих samples. Память — фиксированное число скаляров плюс прежние ограниченные истории.

После более max_age_s=0.25 с без нового ACCEPTED wheel update включается covariance-эпизод. При неизвестной начальной корреляции применяется PSD-envelope diag(2*Pvv,2*Vd), затем Pvv дополнительно получает 2*dt*Pvd+dt^2*Pdd, а Pvd — dt*Pdd. Прежний Qv*dt и stale multiplier остаются. Qd random walk не добавлен. Это не arbitrary Q×2/×4.

После velocity correction применяется Schmidt/Joseph cross update Pvd+=(1-K)*Pvd-, Pdd не уменьшается. На реально выполненной legacy d adaptation или STOPPED nuisance-эпизод маргинализируется **без снижения накопленного Pvv**. Следующее удерживание начинает новый эпизод. Explicit reset очищает lifecycle. Формулы среднего d, его target/tau, mean prediction и интегрирования неизменны; численные значения v/d после коррекции могут отличаться через новый K. До первой активации и при feature-off проверена точная эквивалентность.

Добавка Pvv вводится до вызова неизменного guarded readout: его реконструкция scalar gain видит фактический prior. Hard innovation cap, raw rate/range/zero-lock и bounded reacquisition не расширены. Мягкий covariance-dependent gate может реагировать на Pvv; common-mode проверки обязательны.

## Train, development и freeze

Бюджет — **один** заранее объявленный фиксированный train-calibrated вариант. 64 train-bag открыты только по controller/front/rear; 60 дали 441264 допустимых причинных residual в 25 группах. Residual — ошибка legacy adaptation target относительно d до обновления. Квадраты ограничены (2*disturbance_limit)^2; ограничены 1697 точек. Взята 90-я процентиль средних квадратов по группам и заранее заданный диапазон [0.0025,0.36]:

`Vd = 0.07771769350669397 (м/с²)²`; initial episode `Pdd = 0.15543538701338794`.

Это колёсная псевдоразметка и bounded second-moment proxy, не независимая истина и не гарантированная дисперсия реальной ошибки d. Общая ошибка колёс может быть невидима; selection по trusted residual и clipping ограничивают интерпретацию.

Настоящий development: 17 bag / 7 групп, 56 original и 56 дополнительных диагностических сценариев. 73 clean/original replay сравнения подтвердили canonical factory и exact feature-off (возвращаемые Estimate и runtime counters; unit дополнительно сравнивает все baseline state fields). Coverage/reference masks не менялись. Активация: 178 эпизодов, 6301 active ticks, 7 групп — выше предзаданных 10/100/3. Это счётчики replay, не независимые поездки.

Development clean RMSE 0.092668142983 → 0.092667586390; fault 0.237548612056 → 0.237548612056. Safety-rejections отсутствовали; original unrecovered остались 4/4, diagnostic 4/4. Протокол заранее разрешал единственную validation-проверку фиксированного варианта без достаточного development gain при пройденных safety/activation. Подбор по validation не выполнялся.

## Один paired validation

19 bag / 10 групп, reference в 9 группах и 30 bag/receiver-парах. 76 original fault scenarios / 120 сравнений с reference. Оба приёмника сохранены. Четыре bag без reference не превращены в нулевую ошибку. Output — опубликованные Estimate.v/s, не внутренние v/s.

Неизменные score/metrics/matching/distance из pinned `tools/finalization/evaluate.py` и `tools/research_v3/experiment.py`; original anchors и group aggregation импортированы из pinned guarded compare. Его устаревшая factory main=v5 НЕ используется. Новый driver создаёт canonical v7 для baseline и подкласс для candidate. Хеши старых файлов проверены относительно общего SHA; те же хеши проверены после скачивания evidence.

Заново исполненный baseline воспроизводит опубликованные v7 clean/fault/distance aggregates без расхождения; 698891 matched samples. Исторические цифры не подставлялись вместо исполнения. Для off/canonical отдельно выполнены реальные development replay.

| Метрика | R2 baseline | H18 | Изменение |
|---|---:|---:|---:|
| Clean group-macro RMSE, м/с | 0.114549861317 | 0.114549446986 | −0.000361704% |
| Original fault-event group-macro RMSE, м/с | 0.538286782601 | 0.538286782601 | 0% |
| Pooled clean RMSE, м/с | 0.216406794155 | 0.216406614432 | −0.000083049% |
| Scalar-span distance RMSE, м | 4.595480653018 | 4.595481307472 | +0.000014241% |
| Clean group-macro MAE, м/с | 0.047549651404 | 0.047549280758 | −0.000779492% |
| Signed group-macro bias, м/с | −0.015975155952 | −0.015975649734 | Δ −0.000000493782 |
| Group-macro p95 abs error, м/с | 0.131696583956 | 0.131694059929 | −0.001916547% |
| Среднее recovery, с | 0.254840173467 | 0.254840173467 | без изменения |
| Matched samples | 698891 | 698891 | без потери |
| False stop samples clean / fault | 18 / 0 | 18 / 0 | без роста |
| Original unrecovered | 0 | 0 | без новых случаев |

Все original recovery значения, включая missingness, совпадают. Original per-bag/receiver event RMSE расходятся максимум на 6.04e-16 м/с, то есть только на уровне float. Coverage совпадает для каждой пары; causal errors и unexpected resets — 0/0. Приёмка: единственная основная причина отказа `insufficient_gain`; не достигнуты 2% clean ИЛИ 5% original fault. Остальные заданные численные ограничения не нарушены.

По original fault-типам group-macro RMSE одинаковы: bias 5 с — 0.414421398312; dropout 5 с — 0.558804079207; dropout 10 с — 0.723733997082; lock 3 с — 0.456187655803 м/с.

[Сводка всех 19 bag](per_bag_summary.csv) усредняет доступных receiver внутри bag только для удобства чтения; основной group-macro контракт и per-receiver проверки сохраняются. [Полные per-bag/per-receiver/per-fault CSV](https://github.com/jabrailkhalil/hack/blob/149d175f310d9062309bd690b7bdbff23d15bf31/reports/research_R2/H18/covariance-36186808559-1/validation/per_bag_receiver_fault.csv).

## Механизм, локальные регрессии и common-mode

Validation: 198 covariance-эпизодов, 8078 active ticks по 10 группам в clean/original replay. Это не неактивная заглушка: в 58 из 76 original fault replay траектория после возврата колёс различается. Post-hoc анализ сохранённых CSV, без повторной настройки: 7233 active trace points original-suite не показали отрицательного PSD determinant. Это конечная проверка, не глобальное доказательство нелинейной covariance.

Пример genuine recovery: `30618_0686195f`, dropout 10 с. Первые три здоровых update gains: baseline 0.981469 / 0.795223 / 0.642247; H18 0.998812 / 0.821783 / 0.645614. Первое различие скорости — после конца outage, t=138.799960237. Прежний threshold recovery уже выполнялся; его время не улучшилось. Рост gain не выдаётся за прирост original event accuracy.

Максимальная clean per-receiver регрессия по абсолютной дельте: `30618_437e855c/master`, 0.032729584705 → 0.032731225776 м/с (+0.005014%). Маленькая положительная distance aggregate delta и более отрицательный signed bias также не скрыты.

Дополнительные diagnostics — отдельный заранее зарегистрированный suite, не подмена original admission:

| Сценарий | Baseline event RMSE | H18 event RMSE | Изменение | Принятия искажённых каналов, B/C |
|---|---:|---:|---:|---:|
| Common +5 м/с, 0.7 с | 0.059511444220 | 0.059511444220 | 0% | 0 / 0 |
| Common +5 м/с, 1.2 с | 0.125364419412 | 0.125364419412 | 0% | 94 / 94 |
| Ramp +1 м/с за 1 с, hold до 2 с | 0.842367717269 | 0.842367717269 | 0% | 732 / 732 |
| Dropout 5 с, затем false pair +2 м/с на 1 с | 1.124793400886 | 1.131782097321 | **+0.621332%** | 361 / 361 |

Последняя RMSE относится ко всему 6-секундному событию, не только к последней секунде. Всего 1187/1187 corrupted channel-status acceptances: **отсутствие роста не означает абсолютную защиту от общей ошибки**. Счётчик использует ACCEPTED/REACQUIRE_ACCEPTED и timestamp искажённого канала, не дублируется по GNSS receiver. Новых false stops или unrecovered в diagnostics нет.

Худший диагностический случай по абсолютной дельте: `30618_2dbce472/rover`, dropout+false pair, RMSE 0.760654567933 → 0.776384769357 м/с (**+2.067982%**), хотя recovery сокращается 1.068067 → 0.718067 с. В первой принятой ложной паре t=164.818066806 gain 0.877819 → 0.983038, опубликованная v 6.823983 → 7.048573; d в этот момент одинаков −0.199063. Более сильная коррекция увеличила влияние уже принятой ложной пары. Это наблюдение контролируемого replay, не доказательство всех возможных причин реальных ошибок.

## Стоимость и фактические проверки

Первый лексикографический development-bag `30618_0652866c`, 10 с warmup, 29287 outputs всего / 29087 после warmup. Три AB/BA пары, по шесть повторов каждого алгоритма, отдельно step-loop и replay; OMP/OPENBLAS=1. Сбор outputs одинаков. Медианы включают сбор outputs, не только арифметику фильтра:

| Измерение | Baseline CPU / wall, с | H18 CPU / wall, с | CPU Δ |
|---|---:|---:|---:|
| Step-loop | 0.977253 / 0.977346 | 1.065588 / 1.066134 | +9.0390% |
| Replay с Timeline | 1.325042 / 1.325208 | 1.432437 / 1.432913 | +8.1050% |

Step-loop: 33.598 → 36.634 мкс CPU на postwarm output. RSS peak **всего offline-процесса** 165933056 байт, включая NumPy/SciPy и данные. Это НЕ installed ROS RSS, publisher latency, p95/p99, hard-real-time или сертификация 500 MB.

- H18 mechanism/driver **18/18 PASS**: 6000 exact-off шагов со всеми baseline fields; 20000 шагов PSD/finite/constant-memory; Joseph/envelope, finite difference, prefix/future/stale/duplicate/reset, test-role prohibition, неизменный scorer, pooled и zero-baseline guards.
- Полный неизменный unit suite **144/144 PASS**; research integrity **43/43 PASS**; compile PASS. Исторические release-hash tests/pins не удалялись.
- [Обычный CI 36186808289](https://github.com/jabrailkhalil/hack/actions/runs/36186808289): все 4 jobs success, включая ROS и offline limited. Это проверка прежнего canonical v7, **не включённого H18**.
- Train/development/freeze/validation выполнены один раз. Access journal: 64 train / 17 development / 19 validation; train GNSS закрыт, test SQLite не открывался. Baseline reproduction и freeze/source hash проверки PASS.
- Локально проверены SHA256 скачанного ZIP, source hashes, `git apply --check`, применение минимального patch и совпадение полученного module SHA256 с измеренным.
- **Свежий установленный enabled-H18 ROS real-bag benchmark в обоих clock mode НЕ выполнен**: accuracy gate уже REJECTED, поэтому разрешённый протоколом полный ROS этап пропущен. Не заявляется unavailable environment; этап именно не выполнялся.

## Как включить и воспроизвести

Checkout сам по себе НЕ включает кандидат. В исследовательском driver baseline factory создаёт GuardedReadoutObserver; candidate factory создаёт:

```python
OutageCovarianceObserver(
    Config(**profile['config']),
    readout=ReadoutConfig(**profile['readout']),
    enabled=True,
    disturbance_variance=0.07771769350669397,
)
```

Timeline передаётся rate_hz=20, delay_s=0. Feature-off enabled=False совпадает с canonical baseline. Выбранные параметры: [H18-config.json](H18-config.json). Минимальный runtime patch: [algorithm.patch](algorithm.patch); проверенный SHA256 `adc163a98677f574e175841ff51f6b5297c113e3a18c53c1fff21e9eb67921a9`. Он добавляет класс, не меняет canonical executable и не является рекомендацией развёртывания.

Фактически выполнено в Python 3.13.5, NumPy 2.3.5, SciPy 1.17.0:

```bash
python -m pip install -r requirements-research.txt
python tools/get_dataset.py
PYTHONPATH=src/reserve_odometry python -m unittest discover -s research/R2/H18 -p 'test_*.py' -v
R=reports/research_R2/H18/covariance-36186808559-1
python research/R2/H18/run.py --stage train --output "$R/train"
python research/R2/H18/run.py --stage development --training "$R/train" --output "$R/development"
python research/R2/H18/run.py --stage freeze --training "$R/train" --development "$R/development" --output "$R/freeze"
# Отдельный commit/push fa2d2796... ДО следующей команды.
python research/R2/H18/run.py --stage validation --freeze "$R/freeze/FREEZE.json" \
  --freeze-commit fa2d27962c2858b69a7ed68a86dccafe24bfc145 --output "$R/validation"
```

Для точного повтора взять отдельный worktree freeze-коммита `fa2d27962c2858b69a7ed68a86dccafe24bfc145`, установить те же зависимости/датасет и выполнить последнюю команду с новым output (например `/tmp/h18-validation-repeat-unique`). Runner запрещает перезапись и проверяет committed freeze/source. Это инструкция повторения, не заявление о втором выполненном прогоне.

## Evidence, источники и ограничения

[Неизменяемый полный checkpoint](https://github.com/jabrailkhalil/hack/tree/149d175f310d9062309bd690b7bdbff23d15bf31/reports/research_R2/H18/covariance-36186808559-1): PLAN, source/config/patch, training/per-bag stats, FREEZE, access journals, commands/logs, raw JSON и полные CSV до/во время/после original и diagnostic faults. [Raw validation](https://github.com/jabrailkhalil/hack/blob/149d175f310d9062309bd690b7bdbff23d15bf31/reports/research_R2/H18/covariance-36186808559-1/validation/results.json). ZIP artifact `H18-covariance-36186808559-1`, SHA256 `787e69d78e446b8781a91e89024af00ffdedc0056a6040821b9fac976b1b4e3e`. В PR помещены компактные производные сводки; большие traces остаются checkpoint evidence, не дублируются в diff.

Consensus: Zanetti/Bishop, Kalman Filters with Uncompensated Biases (2012), DOI 10.2514/1.55120 — реально прочитаны metadata и вступительный extract, не вся статья. Primary author bibliography подтверждает DOI/страницы. Scite фактически ответил monthly MCP quota exceeded; citation-context/full-text проверка недоступна и не выдумывается. Покупки/изменение прав не выполнялись. [Источники и область применимости](../../../../research/R2/H18/SOURCES.md).

Wolfram реально проверил FPF'+Q, Pvv(T)=Pvv0+2T*Pvd0+T²*Pdd0+Qv*T, Qd*T³/3 и cross terms, Joseph, PSD-envelope determinant, zero-time, semigroup и ideal observability. [Исполнимый worksheet](https://github.com/jabrailkhalil/hack/blob/9ff728d0a06b25b5a4c2da86a2337aa1157e8ce9/research/R2/H18/wolfram.wl), [фактический вывод](https://github.com/jabrailkhalil/hack/blob/9ff728d0a06b25b5a4c2da86a2337aa1157e8ce9/research/R2/H18/wolfram-output.txt). Qd в runtime отсутствует.

Covariance — episode-local approximation, не точная uncertainty нелинейного clipped observer и не calibrated confidence intervals. Variance/error ratios сохранены как diagnostics, не как сертификат. Скалярная distance — не XYZ/ENU и не полный terminal drift. Два GNSS receiver одной записи не объявлены независимыми поездками; group aggregation сохранена, tick-bootstrap не использован. Повторно используемый validation не является независимым final test; test-payloads не декодировались.

**Итог:** проверенный вариант REJECTED; mechanism ACTIVE, merge-ready false. Отрицательный результат не опровергает всё семейство covariance-моделей. Он показывает, что здесь увеличение confidence uncertainty почти не меняет основную ошибку, не улучшает original recovery и усиливает некоторые ложные коррекции при дополнительной стоимости.
