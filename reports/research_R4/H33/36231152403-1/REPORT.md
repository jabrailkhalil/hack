# R4-H33 — NOT_EVALUATED: проверка основания заблокирована до train

**Исследовательский артефакт, не готов к merge.** Нет измеренного улучшения и нет отрицательного результата H33 на реальных записях. Достигнут этап source verification + пререгистрация + локальные математические/implementation проверки. Train foundation не выполнен: GitHub Actions завершился failure до назначения runner, а локальная загрузка датасета недоступна. Не переименовывать этот блокер в REJECTED или в INCONCLUSIVE после якобы выполненной диагностики.

## Идентичность

| Назначение | Значение |
|---|---|
| Гипотеза / раунд | R4-H33 / R4-v8-fixed |
| Baseline commit | e3b0c9c039d2953fbfcda51231263d38ef9f1024 |
| Полный baseline tree | eae49a504bc59b5c9b408445150bef32e111956f |
| Ветка | research/R4-H33 |
| PLAN до measurements | 2d27233cf3bea27c8343cc42ed3c6ece4c4477a6 |
| Исходники неисполненного Actions run | d4837cc66e09321e3104cc3e8f7387f8628fb7fd |
| Последний локально проверенный диагностический source | 5c6571789b1c6ca45f9efc74861dc34920e6e308 |
| Measured runtime candidate SHA | N/A — runtime-кандидата нет |
| Freeze / measurement checkpoint | N/A — не создавались |

Все параметры читаются из champion_v8.yaml. Baseline — полный GuardedReadoutObserver, включая readout и common-mode quarantine, а не Observer(Config()). 20 Hz, alignment_delay=0, readout gain=1/holdoff=.5, adaptation_tau=.5, wheel_time_compensation=0, common_mode_quarantine=1.5. H32 и более поздний main не подмешаны.

## Полный ZIP, не восемь выбранных файлов

Приложенный hack-main-2(20260926-083617).zip прочитан встроенным stdlib verifier карточки. Все **301 путь, bytes и executable bits** дают закреплённый tree. SHA256 ZIP: **a8e0bfa033e0a02c460c30b02f34a5c64ece85b05003512941387d3cf1f319a2**, размер 3831196 байт; root hack-main-2/; 352 записи __MACOSX исключены. В ZIP нет .git и .db3. Полный SOURCE_RECEIPT с per-file hashes сохранён отдельно, его SHA256: **76b91651dbd368bb4ffef360cac573189e753b7b951833817a3f278c682a331d**. Компактный receipt лежит в research/R4/H33/SOURCE_RECEIPT.json.

Программа снова проверила все301 baseline-файлы в candidate-копии: изменённых исходных файлов0. Remote GitHub commit отдельно подтвердил связь baseline SHA с tree; локальный snapshot commit с выдуманной ancestry не создавался. Pristine baseline и исходный пользовательский ZIP не переписаны.

## Что реализовано

Реализованы **диагностические**, а не управляющие оценкой скорости, компоненты:

- passive Probe над исходным v8: новые доверенные raw wheel-пары, native timestamps, ограниченная история pre-correction g=drive_a−resistance(old_v), интервальные residuals и контроль режима;
- stdlib tridiagonal solve размера1..6; GLS и unweighted диагностические цели для окон .20/.40s; один floor1e-6 от sigma², без перебора шума/tau;
- проверка train-роли до IO, SQL read-only с тремя vehicle-топиками, selective extraction только разрешённой роли и SHA256 каждого bag;
- машинный foundation gate, per-bag/per-group диагностические таблицы и сжатые массивы, если данные будут доступны;
- workflow без шага validation, immutable checkpoint/artifact при фактическом исполнении;
- источник можно проверить как через Git, так и через полный receipt из ZIP; в последнем случае заново вычисляются все301 hashes/modes и Git tree.

Probe возвращает неизменный Estimate и не подаёт GLS-target обратно в disturbance/velocity/covariance/readout. Основной scorer, core, Timeline, ROS adapter, config и canonical launch не изменены. Длинный список диагностических строк — внешний offline collector, не новая runtime-очередь.

**Runtime-кандидат H33, заменяющий цель EMA, НЕ реализован.** Его создание по карточке/PLAN разрешено только после достаточного основания. Существующий solver и пассивный расчёт целей не выдаются за внедрённое улучшение одометрии. Оба окна пока являются диагностическими, `variants_tested=[]` относится к accuracy-кандидатам.

## Пререгистрированное основание и возможный следующий этап

PLAN опубликован до доступа к measurements. На всех64 train bags предполагается проверить остаточные приращения в контролируемом режиме: исходная eligibility, согласованность колёс<=.15m/s, skew<=.05s, dt_pair в [.08,.12]s, |z|>.5; валидная команда за прошлые2s с range<=.02, |drive_target−drive_a|<=.1m/s². Непрерывные сегменты от30 increments; между разрывами/bags корреляция не считается. Из каждого сегмента вычитается только постоянное среднее acceleration residual. Это контроль, а не истинная ошибка измерения.

Prospective foundation: >=3 исходные группы по>=200 соседних пар, суммарно>=1000; в>=2/3 qualifying групп lag1 в[-.75,-.10] и sigma_proxy>=.001m/s; медиана lag1 в том же диапазоне, медиана |lag2|<=.25. Для окна.40:>=100 действительных отличий GLS от unweighted >1e-6m/s² в>=3 группах. Пока ни один из этих показателей на реальных данных не измерен.

Это консервативный operational gate, не универсальный тест белого шума. После data-access block он не был изменён. При foundation PASS разрешены только окна .20/.40, исходная bounded EMA tau=.5, baseline fallback на плохой истории/condition/clipping, без изменения fusion/R/guards. Контроль unweighted не выбирается как кандидат. Общий R4 development contract сохранён: >=2%clean ИЛИ >=5%original fault gain, ограничения aggregate/per-bag/coverage/safety, отдельные low-speed/common suites. Validation возможен только после положительного development и опубликованного freeze. Сейчас этих этапов нет.

## Математика и фактические тесты

WolframLanguageEvaluator действительно исполнил worksheet. При iid endpoint error с дисперсией sigma² проверена C=sigma² D Dᵀ: диагональ2sigma², соседние элементы−sigma². Для uneven dt acceleration covariance получается через diag(1/h) C diag(1/h), а GLS по raw increments использует design h. Проверены положительные ведущие миноры2,3,4,5,6,7, scale cancellation и точная affine-цель. Condition для n=6 без floor около19.19566936. Worksheet и настоящий output опубликованы; неудачные semantic snippets WolframContext не используются.

Для **двух одинаковых интервалов GLS и unweighted дают одну цель**. Для четырёх равных интервалов h веса raw increments равны [0.2,0.3,0.3,0.2]/h. В идеальной модели дисперсии: GLS sigma²/(10h²), unweighted sigma²/(8h²), последняя двухточечная производная2sigma²/h². Это условная формула, **не измеренный gain скорости/дистанции** и не подтверждение iid noise реальных колёс.

Последние локальные прогоны, Python3.13.5/NumPy2.3.5/SciPy1.17.0:

| Проверка | Фактически выполнено |
|---|---|
| Legacy runtime tests | **156/156 PASS**, 0.746s |
| Research-integrity tests | **43/43 PASS**, 0.439s |
| H33 diagnostic tests, включая полный ZIP receipt | **19/19 PASS**, 0.464s |
| compileall src/research H33 | PASS |
| All301 исходных файлов candidate против ZIP receipt | PASS,0 изменений |

Покрытие H33-тестов: 180 сравнений stdlib solve с dense NumPy, 100000 сгенерированных iid endpoint-наборов для covariance sanity, variable dt/affine slope, scale cancellation, n2/n4 пределы, дробные границы интеграла, no extrapolation, stale/clipped/gap, bounded history на15000 шагах, synthetic4000-step all-state/Estimate parity с v8, causal prefix/duplicates/future/reset, запрет test-роли до IO, receipt integrity и foundation gate.

Первый локальный запуск имел16pass/1fail: Python list equality на соответствующих NaN диагностического массива. Исправлен только assertion через np.testing.assert_array_equal; исходный лог сохранён. После этого17tests прошли; после добавления ZIP portability —19. Корректировки перечислены в BUGFIX_LOG. Ни один тест или синтетическая covariance не заменяет реальную accuracy.

## Конкретный недоступный этап

**GitHub Actions run36231152403, attempt1**, source d4837cc66e09321e3104cc3e8f7387f8628fb7fd:
https://github.com/jabrailkhalil/hack/actions/runs/36231152403

Job108374429777 имеет conclusion=failure, runner_id=0, runner_name="", steps=[]; создан08:53:50Z, завершён08:53:53Z 26.09.2026. Логи: API404 BlobNotFound. Artifacts: пустой список. Значит checkout/dependencies/tests/download/train не исполнялись в этом run. Это не упавший алгоритм и не прошедший/проваленный foundation на measurements. Обычный CI36231152334 также failure; зелёный CI не заявляется.

Причина, по которой GitHub не назначил runner, через доступный connector не установлена. GET check-run annotations не входит в разрешённые fetch endpoints; нельзя без доказательства объявить причиной billing/quota/YAML. Автоматический цикл retries не запускался, квоты/ACL/оплаты не менялись. Последующий portable-source и report commits содержат [skip ci], чтобы не создавать новые невыполняемые запуски; это явно **не** CI PASS.

В локальном runtime нет train DB или dataset.zip/data.zip. Прямой запрос pinned Yandex API завершился URLError(gaierror(-3, Temporary failure in name resolution)). Web-путь API и public folder также недоступен; container.download не получил разрешённого просмотренного URL и не скачал файл. Существующие архивы прошлых H10/H13/H23 — отчёты/исходники/трассы, не полный разрешённый train. Они не переименованы в новый train и не использованы как новые измерения.

Итого: source VERIFIED; data UNAVAILABLE в доступной среде этого прохода; execution BLOCKED до train; GitHub read/write работают, draft publication является отдельным действием.

## Метрики, которые отсутствуют

Реальная serial covariance, sigma_proxy, qualifying groups, activation targets, training replay: **N/A**. Candidate clean/fault/pooled/distance RMSE, per-bag/per-group accuracy, MAE/p95/signed bias/recovery, regressions: **N/A**, не0. Canonical v8 не был заново проигран на development, поэтому исторические fingerprint-цифры не выдаются за новое исполнение. Per-bag accuracy CSV с нулевыми/выдуманными значениями не создаётся.

Development, выбор окна, runtime implementation, freeze, validation и final/test: **не выполнялись**. CPU AB/BA candidate и installed ENABLED ROS latency/RSS/frequency под2CPU/500000000bytes в двух clock modes: **NOT_RUN_NO_CANDIDATE**. Контрпример реальной смены нагрузки до dropout также не проверен на новом candidate. Известные H03/H13/H26 результаты — основания для осторожности, не новая метрика H33.

## Команды возобновления без изменения протокола

Из клона репозитория, на последнем локально проверенном diagnostic source:

```bash
git fetch origin research/R4-H33
git worktree add --detach ../hack-R4-H33 5c6571789b1c6ca45f9efc74861dc34920e6e308
cd ../hack-R4-H33
python3.13 -m venv .venv-research
. .venv-research/bin/activate
python -m pip install -r requirements-research.txt
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
PYTHONPATH=src/reserve_odometry python -m unittest discover -s tests -v
python -m unittest discover -s research/tests -v
python research/R4/H33/test_foundation.py
OUT="$(mktemp -d /tmp/R4-H33-foundation-XXXXXX)"
python research/R4/H33/prepare_data.py --roles train --journal "$OUT/extraction.json"
python research/R4/H33/foundation.py --output "$OUT/foundation"
```

В Git-only варианте один тест локального receipt будет SKIP; остальные18 должны пройти. Для ZIP-only варианта применить diagnostic.patch к новой verified baseline-копии и выставить `H33_SOURCE_RECEIPT` на **полный** receipt с301 entries, не компактный файл research/R4/H33/SOURCE_RECEIPT.json. Полный receipt и verifier входят в локальный пакет. При уже доступных проверяемых DB в dataset/data штатный loader заново проверит каждый SHA; менять split/roles не требуется.

После FOUNDATION_PASSED только условный следующий этап PLAN. После INCONCLUSIVE — не запускать development accuracy/validation. Сейчас нет результата foundation и нет задания выполнить всё это в фоне.

## Итог и границы

**NOT_EVALUATED** из-за недоступного выполнения на train, `candidate_implemented=false`, `measured_source_sha=null`, `accuracy_contract_evaluated=false`, `validation_opened=false`, `test_opened=false`, `enabled_runtime_verified=false`, `ready_to_merge=false`. Математические и локальные implementation проверки завершены, но не подтверждают и не отвергают полезность H33. Main, чужие ветки/отчёты и canonical default сохранены. Merge/auto-merge не выполнялись.
