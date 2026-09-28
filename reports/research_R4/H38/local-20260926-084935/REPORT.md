# R4-H38 — Student-t-подобная коррекция: INCONCLUSIVE на этапе основания

**Исследовательский артефакт, не готов к merge. Улучшение одометрии не установлено.** Проверка остановлена по заранее опубликованному foundation-условию: найдено 59 подходящих принятых sub-hard-gate innovations при минимуме 100. Числа степеней свободы ν=4 и ν=8 проверены только как скалярные prospective weights на сохранённом baseline-потоке. Включённый runtime-кандидат не реализован; его RMSE, gain по точности, регрессии и ресурсная стоимость — **N/A**, не ноль.

Это не REJECTED Student-t-подхода и не техническая недоступность данных. Source, train/development и локальное исполнение доступны. Статистического основания для утверждения «Student-t не работает» нет; не выполнен конкретный зарегистрированный порог покрытия этой задачи. Пороги не понижались после подсчёта.

## 1. Baseline, исходники и версии

- Общий R4 baseline: `e3b0c9c039d2953fbfcda51231263d38ef9f1024`.
- Полный tree: `eae49a504bc59b5c9b408445150bef32e111956f`.
- ZIP пользователя: `hack-main-2(20260926-083849).zip`, 3 831 196 байт, SHA256 `a8e0bfa033e0a02c460c30b02f34a5c64ece85b05003512941387d3cf1f319a2`.
- Проверены все **301** путь/файл/исходные bytes/executable bits; 352 metadata-файла `__MACOSX` исключены. Совпал весь tree, не только набор ключевых файлов. Привязка remote commit → tree отдельно прочитана через GitHub.
- Класс `GuardedReadoutObserver`, полный `champion_v8.yaml`: output 20 Hz, delay 0, readout 1/.5, adaptation .5, inner compensation 0, quarantine 1.5. Используются возвращаемые `Estimate.v/s`.
- Своя ветка: `research/R4-H38`. До создания точная ветка/PR этого ID не найдены. H28 — другая незавершённая задача, здесь не перезапускалась.

Пререгистрация PLAN: **`0ef87ffc830dab9401128b927c183bda9a53b397`**, 26.09.2026 08:45:15 UTC — до train-диагностики. Локальная копия PLAN сверена с blob `7558ffea7145ff2c5fc1d1f342e90e70cd45fc9b`.

**Код фактически выполненной пассивной диагностики:** `f6cf247d92bc85ffd79ee63a2033d7365fddb798`. Этот commit опубликован после локального исполнения; совпадение bytes подтверждено отдельным воспроизведением полного tree `b455d2e3e06c457fd2efe1e199fd0076ec2ce532` — 312 файлов с новыми research-файлами и data workflow. Он не выдаётся за предэкспериментальный candidate freeze. `measured_source_sha`/`candidate_sha` для нового observer = **null**; diagnostic source указан отдельно.

Remote reproduction workflow добавлен commit `787dd45a8e19c83755df5c65f38c51c247552f0c`, без изменения diagnostic code. Report/checkpoint SHA находятся в отдельном SUMMARY/commit index; их нельзя подменять SHA алгоритма. Все 301 исходный файл baseline сохранены. Main, чужие ветки, старые отчёты, FREEZE и evaluator не изменены; merge/auto-merge/force push не выполнялись.

## 2. Проверяемая модель и границы математики

Прочитаны полные PR15/H02, PR17/H05 и PR35/R2-H20. Их отрицательные эвристические веса — источник контрпримеров, а не математическое опровержение нового likelihood. Межзнаковый trade-off H20 учтён в заранее объявленных отдельных diagnostic veto. Новый механизм не объединён со старой residual penalty.

Для принятой пары `R0=wheel_sigma²`; при исходной меньшей уверенности одиночного канала `R0=4*wheel_sigma²`. Деления R на число согласованных колёс нет. В Student-t смеси scale matrix `S=R0*(ν−2)/ν`, с размерностью дисперсии; обычный скалярный scale равен `sqrt(S)`. Для неограниченного t распределения `Var=ν*S/(ν−2)=R0`. Gamma здесь задана через **shape/rate**, не shape/scale.

При prior `N(m,P)`, исходном residual `r=z−m`, начальных `e=r`, `C=P` выполняются ровно три offline coordinate updates:

```text
Rraw = ((nu - 2)*R0 + e² + C) / (nu + 1)
Reff = clip(Rraw, R0, 100*R0)
K    = P / (P + Reff)
e    = (1-K)*r
C    = (1-K)²*P + K²*Reff
```

Во всех трёх итерациях используется один исходный prior, а не три ассимиляции наблюдения. Неконечный результат скалярной функции возвращает `None`; это контракт для возможного baseline fallback, но runtime-hook не создавался и не объявляется проверенным.

Wolfram реально проверил scale/variance, формулу Reff, Joseph identity, positive scalar covariance, small-residual floor condition `e²+C<=3R0`, Gaussian limit и bounds gain. Worksheet и фактический JSON сохранены, warnings в algebra response отсутствуют. Для фиксированного Reff без дополнительного floor выполняется `Ppost=P*Reff/(P+Reff)`, `1−Ppost/P=K`. Дополнительный floor 1e−8 может нарушать последнюю реконструкцию; отдельный тест это демонстрирует. **Actual-gain/readout parity включённого Student-t observer не заявляется**, так как такого observer нет.

Три итерации и clipping — инженерная аппроксимация, не точный Student posterior и не полная реализация статьи. Прочитан издательский abstract/excerpts Zhu, Leung, He (2013), DOI `10.1016/j.ins.2012.09.017`, не полный текст. Статья мотивирует likelihood, не доказывает результат на этих записях. Consensus/Scite не запрашивались повторно после известных quota-stop предыдущих раундов; новых citation-context проверок через них нет.

## 3. Данные, изоляция и реальная диагностика train

Локальный HTTP downloader сначала получил DNS error. Авторизованный GitHub Actions data-stage **36230600455** затем успешно скачал точный pinned organizer archive и распаковал только **64 train + 17 development DB**. SHA256 исходного dataset.zip `d0b2483e13990edb8219b0d7bbcafc7ed001cce549a4d3af467069b2472e7d52`; проверены split и checksum каждого bag. Validation/test DB не распакованы. Train SQL выбирает только controller/front/rear; наличие других topics внутри DB не означает их чтение.

Data artifact `10902173801`, SHA256 `f1ba92d01faf93c15a495543f403447c3fd7c9b9c55002d3b22f860747dc822a`; срок хранения 7 дней, expires `2026-10-03T08:43:20Z`. Данные в source commits и исследовательский evidence ZIP не включены.

`Probe` вызывает неизменённый canonical observer и после шага пассивно восстанавливает pre-update residual/prior/R0. Равенство восстановленной коррекции фактической inner velocity проверяется assertion. Offline prospective Reff никуда не возвращается в фильтр. Сохраняются возраст принятых samples, режим и длительность неизменной команды, model acceleration и per-group strata. Innovations содержат динамику, возраст, model mismatch и ошибки колёс, а не только чистый measurement noise.

Полный завершённый train-проход начался `2026-09-26T08:49:35.308224+00:00`, обработал все **64 bag / 27 исходных групп** и **483 819** принятых обновлений при валидной команде. Первый локальный baseline-only запуск был прерван тайм-аутом инструмента после 46 сохранённых bag-файлов; его log/manifest сохранены. Второй запуск использовал тот же код и новые output paths, без изменения правил/параметров; массивы всех 46 завершённых bag совпали с полным проходом. Это не второй поиск кандидата и не validation retry.

## 4. Основание недостаточно: зарегистрированный gate

До measurements задано: минимум **100** принятых cases с `abs(residual)>3*sqrt(R0)`, age<=0.1 с, валидной командой без изменения >=0.5 с, минимум в трёх source groups. Для каждого ν необходимо хотя бы 100 случаев, где prospective Reff отличается от legacy R не меньше чем на 1%, также в трёх группах.

| Условие | Требование | Измерено |
|---|---:|---:|
| Подходящие sub-hard-gate cases | >=100 | **59** |
| Исходные группы с такими cases | >=3 | 10 |
| ν=4: prospective R changes >=1% | >=100 | **54** |
| ν=8: prospective R changes >=1% | >=100 | **56** |
| Группы с изменением, каждый ν | >=3 | 10 |

**Группы покрыты, количества случаев не хватает.** Всего до дополнительных условий найдено 158 confidence-tail cases, после age-фильтра — 140, после неизменной команды — 59. Эти counts относятся к уже принятым фильтром innovations, не ко всем raw wheel values и не ко всему noise-распределению.

59 случаев — около 0.0122% сохранённых accepted updates. На свежих/stable обновлениях p95/p99 абсолютного residual равны приблизительно 0.052768/0.113089 м/с; максимальный residual подходящих cases 0.881775 м/с. Это описательная выборка с сильной временной зависимостью, не независимые испытания и не статистическая значимость.

После фиксации результата выполнен read-only audit NPZ: ν=4 уменьшает R относительно legacy минимум на 1% в 43 случаях и увеличивает в 11; ν=8 — в 52 и 4 соответственно. Следовательно, замена soft penalty не означает безусловного дополнительного подавления: часто она дала бы **больший** вес, чем legacy. Без включённого observer это не доказанный прирост ошибок или false attenuation. Raw/centered tails и все strata по group/mode/age/acceleration сохранены, пороги заново не выбирались.

На этой точке PLAN требует **INCONCLUSIVE и отсутствие enabled candidate**. Не запускались candidate development/его low-speed/common-mode/sign counterexamples/full-faulted-bag distance, не создавался candidate freeze, не открывались validation/test, не измерялся enabled ROS runtime. Значения этих проверок N/A, не PASS.

## 5. Отдельный baseline-only audit development

Чтобы отделить scientific stop от ошибки профиля/измерителя, дополнительно выполнен настоящий v8 на всех **17 development-bag / 7 группах** и исходных **56 fault scenarios**. Неизменный scorer получил два экземпляра канонического v8: прямой и обёрнутый пассивной Probe. Исторические labels `baseline_v2` и `balanced_physics` — только API aliases; оба фактически v8, ни один не Student-t candidate.

| Development baseline | Заново измерено | Разница с заданным fingerprint |
|---|---:|---:|
| Clean group-macro RMSE, м/с | 0.09266814298282507 | 0.0 |
| Original fault-event RMSE, м/с | 0.2375486120563008 | 0.0 |
| Pooled RMSE, м/с | 0.1293056944774334 | 0.0 |
| Scalar-span distance RMSE, м | 5.310295004801444 | 0.0 |
| Matched reference samples | 394221 | 0 |

На 73 clean/original-fault replay проверены **359 956** тактов: равны все исходные state fields, каждый `Estimate`, полные output arrays и runtime counters. Это проверка пассивности диагностики и правильного baseline, **не accuracy A/B нового алгоритма**. Исходный baseline имеет 4 неподтверждённых recovery, false-stop counts 0/0; эти существующие случаи не скрыты и не выданы за регрессии H38. Полные RMSE/MAE/p95/bias/distance/recovery per-bag/receiver/fault находятся в CSV/JSON; N/A reference не превращён в ноль.

## 6. Что выполнено и что не подтверждено

Локально: **156/156 baseline unit**, **43/43 research integrity**, **14/14 scalar/diagnostic tests**, compile PASS. Специальные тесты проверяют scale/variance, ровно три итерации и один original prior, оба знака residual, confidence floor и upper bound, конечность/Joseph, Gaussian limit, numeric failure, 12 000 synthetic steps exact passive equality, stale/future/duplicate/reset, transactional bad timestamp и role denial до file/SQLite IO. Это не 14 тестов enabled H38.

Research patch применён к отдельной чистой baseline-копии: `git apply --check`, фактический apply и bytes всех добавленных файлов совпали. Runtime/default/guards и весь исходный tree не переписывались.

Ранний стандартный [CI 36230600457](https://github.com/jabrailkhalil/hack/actions/runs/36230600457) на data-stage commit прошёл 4/4 jobs, включая canonical ROS/offline; это не новая H38 runtime-проверка. Поздняя попытка удалённого воспроизведения [36231632634](https://github.com/jabrailkhalil/hack/actions/runs/36231632634), job108375766266, завершилась **failure со steps=null**; запрос лога вернул **404 BlobNotFound**. Стандартный CI того же commit **36231632671** также имеет failure. Причина отсутствия старта доступными ответами не установлена — billing/quota/ошибка workflow не выдумываются. Повторные запуски не предпринимались; удалённый reproduction не засчитан.

Это отдельное ограничение удалённого повторения/создания большого GitHub artifact, **не отмена завершённых локальных measurements и не scientific REJECTED**. Raw результаты доступны в передаваемом с ответом сжатом evidence ZIP с SHA256 и manifest. Срок хранения sandbox-архива этим исследованием не гарантируется. Его стоит сохранить вместе с исходным ZIP. Никаких p95/p99 latency, incremental node RSS, enabled runtime certification или runtime CPU gain для отсутствующего кандидата не заявляется.

## 7. Воспроизведение и артефакты

Нужен доступ к private repo и полный stage данных. Пока исходный data artifact доступен:

```bash
git fetch origin research/R4-H38
git worktree add --detach /tmp/r4-h38-repro f6cf247d92bc85ffd79ee63a2033d7365fddb798
cd /tmp/r4-h38-repro
python3.13 -m venv .venv-research
. .venv-research/bin/activate
python -m pip install -r requirements-research.txt
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1

gh run download 36230600455 --repo jabrailkhalil/hack \
  --name R4-H38-data-36230600455-1 --dir dataset

PYTHONPATH=src/reserve_odometry python -m unittest discover \
  -s research/R4/H38 -p test_foundation.py -v
python research/R4/H38/foundation.py \
  --data-root dataset/data --output /tmp/h38-fresh-foundation
python research/R4/H38/audit_saved.py \
  --source /tmp/h38-fresh-foundation --output /tmp/h38-fresh-audit
python research/R4/H38/audit_baseline.py \
  --data-root dataset/data --output /tmp/h38-fresh-baseline
```

После истечения data-artifact можно отдельно выполнить существующий `r4-h38-data.yml` на своей ветке через Actions и скачать его новый run artifact; научные параметры не меняются. Не использовать historical final-test evaluator. Output-каталоги должны быть новыми. Эта команда повторяет **диагностику**, не запускает Student-t observer. `audit_saved.py` ничего не переобучает и не делает replay.

В пакете: исходные foundation.json/64 NPZ, baseline-only results/per-bag CSV, raw source manifests, полные логи и журнал прерванной попытки, exact research code, PLAN, Wolfram, source-reading scope, команды и проверенный `research.patch`. Dataset не включён. В Git — читаемые code, компактные отчёт/статусы/таблицы; большой локальный raw archive не выдаётся за созданный Actions artifact.

**Итог:** INCONCLUSIVE по покрытию основания. Подтверждено исполнение диагностики и воспроизводимость baseline; не подтверждена точность H38. `candidate_implemented=false`, `accuracy_contract_evaluated=false`, `accuracy_contract_passed=false`, `ready_to_merge=false`. Изменять пороги и продолжать validation в рамках этого же протокола нельзя; иное исследование потребовало бы отдельной предварительной постановки.
