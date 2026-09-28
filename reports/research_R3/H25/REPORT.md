# R3-H25 — INCONCLUSIVE: относительная калибровка front/rear

## Решение и граница выполненной работы

**Исследовательский артефакт, не готов к merge.** На полном train обнаружено достаточно подходящих пар, но не установлено устойчивое, отличимое от предзаданного порога относительное multiplicative mismatch. По опубликованному до данных PLAN исследование остановлено на prerequisite. Runtime-калибровка не внедрялась; development, validation и final/test measurement payloads не открывались. Это **не** измеренное отсутствие выигрыша всех относительных калибровок и **не** REJECTED по RMSE.

| Поле | Значение |
|---|---|
| `mechanism_status` | `TRAIN_RATIO_DIAGNOSED_RUNTIME_NOT_IMPLEMENTED` |
| `coverage_status` | `SUFFICIENT_TRAIN_PAIRS` — только покрытие диагностики, не вмешательства |
| `scientific_verdict` | `INCONCLUSIVE` |
| `accuracy_contract_passed` | `false`; accuracy не оценивалась |
| `runtime_verified` | `false`; включённого H25 runtime нет |
| `ready_to_merge` | `false` |

## Версии и хронология

- Round: `R3-v8-fixed`.
- Baseline: `e3b0c9c039d2953fbfcda51231263d38ef9f1024`.
- Observer: **полный canonical `GuardedReadoutObserver` v8**, включая low-speed zero-lock и H11 quarantine; не v5/v7 и не `Config()` defaults.
- Профиль: `src/reserve_odometry/config/champion_v8.yaml`. Все поля Config явно загружены из YAML: 20 Hz, delay 0, readout gain 1 / holdoff 0.5, adaptation tau 0.5, wheel_time_compensation 0, quarantine 1.5.
- Ветка: `research/R3-H25`. Перед созданием проверены точный scientific ID в ветках и PR — совпадений не было.
- **PLAN до ratios/fitting:** `afac5e28dad27c792b7974b8a41662c8ed89a13b`, `research/R3/H25/PLAN.md`.
- **Измеренный diagnostic source SHA:** `e5427c7cdeed85184f472a37db03091f2b413593`, опубликован 26.09.2026 05:20:54 UTC.
- Начало train prerequisite: **26.09.2026 05:21:51.517157 UTC**, после source/PLAN и unit/integrity checks.
- Run/attempt: `36220532038 / 1`; [исследовательский workflow](https://github.com/jabrailkhalil/hack/actions/runs/36220532038) — success.
- Неизменный checkpoint: `7be9c33d7c690aeb75c46b4794c5f7b7a795a64f`, `checkpoint/R3-H25-prerequisite-36220532038-1`.
- **Measured runtime candidate SHA: N/A. Validation FREEZE SHA: N/A.** Условия перехода к реализации/validation не выполнены. Поздний commit REPORT/evidence указан отдельно в PR, не подменяет измеренный source.

Движущийся main, чужие ветки/результаты R3 и ранее опубликованные отчёты не изменялись. Merge/auto-merge/force-push не выполнялись.

## Механизм, математика и прежние результаты

Единственная разрешённая оценка: `c_front=c0*exp(delta)`, `c_rear=c0*exp(-delta)`, `c0=1/3.6`; `abs(delta)<=0.01`. Для одновременной ненулевой пары одного знака `delta_i=0.5*log(rear/front)`. Геометрическое среднее остаётся c0, но истинная общая шкала не наблюдается. Никакой GNSS-калибровки, индивидуальных bag constants или выбора «истинного колеса» нет.

Wolfram реально подтвердил product `c0^2`, равенство скорректированной идеальной пары и невидимость общего множителя k. Чувствительности равны `-1/(2*front)` и `1/(2*rear)` и расходятся около нуля. При малом skew h на разгоне ложная ratio-поправка имеет первый член `a*h/(2*v)`. Даже для равных исходных readings арифметическое среднее после ненулевой поправки меняется на `v*(cosh(delta)-1)`: инвариант произведения не является инвариантом истинной скорости. Worksheet и настоящий output, включая `Power::infy`, сохранены в `research/R3/H25/math.wl` и `math-output.txt`. Это не доказательство устойчивости нелинейного observer.

Прочитаны требуемые предшественники: PR15 — **H02**, увеличение R по возрасту/skew; PR17 — **H05**, история надёжности; R2-H20, source `130c964...`, отчёт `c8b83980...`, — асимметричные веса. Их конкретные реализации не достигли достаточного общего gain; H20 показал trade-off между знаками slip. Их цифры не перенесены на H25. Здесь вместо изменения weighting проверялось наличие постоянной относительной ошибки масштаба.

## Предрегистрация и отбор train-пар

Полностью replay всех **64 train bag**, 27 исходных связанных групп. По sorted group IDs до данных назначены 18 fitting и 9 check групп (каждый третий индекс — check). Роли исходного split не менялись. `Store.load(bag,'train')` читает только controller/front/rear; GNSS train закрыт. Пары являются wheel-derived proxy, не независимой истиной.

Только FUSED-такты с двумя новыми ACCEPTED readings, свежей командой, одинаковым знаком, скоростью каждого колеса 2–30 м/с, возрастом <=0.10 с и skew <=0.025 с. Backward rate каждого канала <=0.20 м/с² при отдельном dt 0.05–0.25 с. Предыдущие пары не заменяются удобными более старыми точками; projection/interpolation/future samples нет. Выдержка допустимых пар 0.50 с; hard rejections обрывают историю и включают блокировку 0.50 с. Дубликаты не добавляют новую информацию.

Каждый bag проигран и описан. В fitting исключены только точные `vehicle_wire_sha256` дубликаты внутри исходной группы: представитель выбирается лексикографически до анализа ratios. Осталось **48 уникальных vehicle-потоков**, не 64 независимые поездки. Для bag median нужны >=30 пар, для группы >=100. Group value — median bag medians; **одна итоговая delta — median fitting-group values**. Check и режимы не переобучают её.

Порог покрытия: >=1000 пар, >=8 квалифицированных групп, в том числе >=5 fit и >=3 check. Порог различимого эффекта `epsilon=max(0.0001,2*B)`, где B — заранее определённая групповая медиана описательного timing proxy. Sign agreement >=80% отдельно на fit/check; допуск значений `max(0.0005,0.5*abs(delta))`; согласованность покрытых срезов скорости/режима. Пороги опубликованы до вычисления delta и не изменялись после результата.

## Фактический train-результат

| Показатель | Значение |
|---|---:|
| Полностью обработанные train bag | 64 |
| Исходные группы / уникальные vehicle-потоки | 27 / 48 |
| Все выбранные пары, включая дубликаты bag | 16 720 |
| Уникальные пары квалифицированных групп для группового анализа | **12 635** |
| Квалифицированные группы | **23: 15 fit + 8 check** |
| `delta_raw`, cap не активирован | **0.0000527887939016801** |
| `epsilon` | **0.0001** |
| Групповая медиана описательного B | 0.0 |
| Fit groups с тем же знаком | **11/15 = 73.33%**, требуется >=80% |
| Check groups с тем же знаком | **4/8 = 50%**, требуется >=80% |
| Fit/check groups в допуске по величине | 100% / 100% |
| Размах групповых medians q90−q10 | 0.000244760468367697 |
| Минимальная / максимальная group delta | −0.000110933416944627 / +0.000208038039075891 |

Описательные коэффициенты, **не активированный профиль**: `exp(delta)=1.000052790187255`, `exp(-delta)=0.999947212599402` — примерно ±0.005279% на канал. Это меньше предзаданного effect floor; перестановка знака между группами дополнительно не поддерживает единую поправку. B=0 — медиана proxy, не доказательство отсутствия задержек/шума/неопределённости.

Причины исходного machine decision: `NO_RESOLVED_RELATIVE_MISMATCH`, `GROUP_UNSTABLE:fit`, `GROUP_UNSTABLE:check`, `REGIME_DEPENDENT:regime:traction`. По величине и spread допуски пройдены; слово unstable здесь относится прежде всего к **знаку**, а не к огромным разбросам. Check-proxy gain не вычислялся после остановки; его значение `null`, не 0.

### Скорость, режимы и область покрытия

| Срез | Квалифицированные группы | Group-balanced delta | Покрытие среза |
|---|---:|---:|---|
| 2–5 м/с | 19 | +0.0000664269356083313 | Да |
| 5–10 м/с | 22 | +0.0000105216194046343 | Да |
| 10–20 м/с | 2 | +0.0000329806394219094 | Нет: нужно >=3 групп |
| 20–30 м/с | 0 | N/A | Нет |
| Тяга | 20 | **−0.0000271110380253028** | Да, знак противоположен fitted delta |
| Выбег | 21 | +0.0000390536175615829 | Да |
| Торможение | 12 | +0.0000261581244364807 | Да |
| Положительное движение | 23 | +0.0000260154438929724 | Да |
| Отрицательное движение | 0 | N/A | Нет |

Количество срезов/пар не является количеством независимых поездок. Для скорости >10 м/с и отрицательного движения вывод не переносится. Зависимость proxy от режима может быть связана с квантованием, slip, timing, геометрией движения или шумом; ни одна из этих причин этим прогоном не идентифицирована.

## Реальные проверки и стоимость

Перед train в том же run: **156 штатных unit tests + 43 research-integrity + 20 H25 diagnostic tests PASS**, compile PASS. Новые тесты проверяют формулу на обоих знаках, нулевые/нечисловые значения, общий масштаб и multiplicative-slip counterexamples, product/mean distinction, skew, causality/prefix/future, near-zero, дубликаты, reset, metadata pins, правила группового допуска и невлияние wire duplicates. На синтетическом потоке проверены равенство возвращаемого Estimate и всех исходных полей canonical observer у read-only Probe.

В реальных replay оригинальный `evaluate.replay` исполнен отдельно с каноническим v8 и с Probe. **Все массивы official evaluator и runtime counters совпали точно на каждом из 64 bag** (NaN wheel columns сравниваются equal_nan). `Estimate.v/s` берутся из возвращённого объекта. Итого **1 370 779 вызовов step**, включая 4 480 WAITING; **1 366 299 выходов evaluator** после их исключения. Causal errors и resets — 0. Это воспроизведение inference, **не** воспроизведение reference-RMSE на train.

Получено 478 569 новых FUSED-пар с валидной командой; 395 448 отклонены фиксированными pair predicates, 66 401 — выдержкой, 16 720 допущены. Простой подсчёт пар не выдаётся за полезное изменение outputs: runtime intervention не было.

CPU полного offline replay: canonical **33.370419 с**, read-only Probe с дополнительным сбором данных **39.552419 с**. Порядок AB/BA чередовался между bag. Это **диагностическая стоимость**, а не цена scalar runtime-калибровки; здесь нет warmup-normalized повторных измерений step кандидата. Runtime step/replay overhead H25 — **N/A**.

[Обычный CI `36220531992`](https://github.com/jabrailkhalil/hack/actions/runs/36220531992) также success: core, integrity, ROS Humble, offline 2 CPU / 500 MB. Он проверяет **неизменённый v8**, а не включённую H25-калибровку.

После получения artifact выполнен независимый локальный пересчёт group/fit medians из исходного `selected_pairs.npz`, проверены ratio formula, зарегистрированные bounds, 64 train-only access records и SHA256. Все проверки прошли; `AUDIT.json` и скрипт сохраняются отдельно. Этот аудит не переоткрывал bag, не менял отбор и не добавлял варианты.

## Непроведённые этапы, регрессии и ограничения

- Runtime patch относительной калибровки, selected runtime config и guard probes включённой H25: **NOT_IMPLEMENTED_AFTER_PREREQUISITE**. Сохранён исследовательский patch диагностики, не patch улучшения одометрии.
- Full development/original faults, оба знака single-channel faults, отдельные low-speed/H11 suites: **NOT_RUN_AFTER_PREREQUISITE**.
- Validation, validation FREEZE, per-receiver/per-fault RMSE/MAE/bias/distance/recovery кандидата: **N/A / NOT_RUN_AFTER_PREREQUISITE**. Ни регрессия, ни улучшение accuracy не измерены.
- Enabled ROS replay обоих clock modes, latency/RSS, GetParameters кандидата, 3AB+3BA CPU step/replay: **NOT_RUN_AFTER_PREREQUISITE**. Standard CI не заменяет этот этап.
- Final/test payloads и train GNSS не читались; development/validation/test SQLite не распаковывались. Проверка SHA train DB читает файл как bytes для целостности, но SQL query ограничен vehicle-топиками; reference payloads не декодируются.
- Согласие двух колёс не устанавливает истинную скорость или общий scale. Произвольный common-mode mismatch остаётся ненаблюдаемым. Нет независимой разметки slip/кривизны, высокие скорости и отрицательное движение не покрыты.
- Ограниченный режимный отбор может не выявить другой тип mismatch; INCONCLUSIVE не отрицает всё семейство методов. Порог 0.0001 — предзаданный engineering floor, не статистический confidence interval. Статистическая значимость и nonlinear stability не заявляются.

## Источники и доступ

В R3-карточке сообщён известный quota stop Consensus/Scite; новые вызовы не повторялись и лимит не обходился. Через обычный web прочитаны только publisher metadata/abstract Jung & Chung (2011), DOI10.5772/50906, и авторская HTML-инструкция CVRA о разделении wheel ratio и общей шкалы. Их методы используют внешнюю геометрию/heading и не перенесены в разрешённый интерфейс. Полный текст статьи не заявляется прочитанным. Полный журнал уровня чтения и ссылки — `research/R3/H25/SOURCES.md`.

Локальный DNS не позволял скачать bags; GitHub Actions фактически получил checksum-pinned архив и выполнил все заявленные train-проверки. Запись в GitHub и среда исполнения были доступны. Промежуточный транспортный base64-файл не использовался для измерений и удалён до data-run; читаемые исходники сопоставлены с локально проверенными Git blob hashes. Реальный data-run ровно один.

## Evidence и воспроизведение

В `reports/research_R3/H25/36220532038-1/`: исходные `SUMMARY.json` (все qualified group/slice результаты), `per_bag.json` (все 64 записи, включая не прошедшие количество пар и дубликаты), `started.json`, `access.json`, `pairs_manifest.json`, test/replay logs и artifact metadata. Checkpoint скопирован Git tree object без пересчёта исходных результатов. Все 27 исходных групп дополнительно перечислены в компактной таблице `GROUP_COVERAGE.csv`; это описательный coverage, не новый estimator.

Полные выбранные пары находятся только в одном сжатом artifact: **`R3-H25-prerequisite-36220532038-1`**, ID **10898372712**, ZIP SHA256 **`59dcfb06ca891a4a60d6a4697f65017cf927bd55f7ad5d75a8b006227a118edb`**, 547049 bytes. Retention **30 дней**, expiration **26.10.2026 05:23:13 UTC**. У raw NPZ свой SHA256 в pairs_manifest; таблицы/журналы в Git не зависят от retention. Сырые bags, giant JSON traces и копии raw pairs в нескольких форматах в Git не добавлены.

Воспроизведение именно train-only исследования в новой рабочей копии:

```bash
git fetch origin research/R3-H25
git worktree add --detach ../hack-R3-H25 \
  e5427c7cdeed85184f472a37db03091f2b413593
cd ../hack-R3-H25
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-research.txt
export PYTHONPATH=src/reserve_odometry
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
export GITHUB_SHA=e5427c7cdeed85184f472a37db03091f2b413593
python -m unittest discover -s tests -v
python -m unittest discover -s research/tests -v
python -m unittest discover -s research/R3/H25/tests -v
python -m compileall -q src research/R3/H25
python research/R3/H25/stage_train.py
OUT="$(mktemp -d /tmp/R3-H25-replay-XXXXXX)"
python research/R3/H25/prerequisite.py --output "$OUT/train"
```

Исполнение: Python3.13.5, NumPy2.3.5, SciPy1.17.0 (offline). Stage script отказывается перезаписывать уже staged DB; output должен быть новым. У driver нет development/validation/test entry point. Не запускать чужой final-test workflow. Исследовательский patch добавляет диагностику и проверки, **не активирует относительную калибровку в ROS**.
