# R4-H39 — NOT_EVALUATED: проверка train-квантизации не выполнена

**Исследовательский артефакт, не готов к merge. Гипотеза не подтверждена и не отвергнута.** Реализован и локально протестирован prerequisite driver, но train-измерения не получены. Runtime interval observer не создавался. Candidate SHA, q, candidate accuracy и validation — N/A, не нули.

## Baseline и фиксация

Baseline `e3b0c9c039d2953fbfcda51231263d38ef9f1024`, tree `eae49a504bc59b5c9b408445150bef32e111956f`; GuardedReadoutObserver / champion_v8, 20 Hz, delay0, readout gain1/holdoff.5, adaptation_tau.5, compensation0, quarantine1.5. Все параметры из полного профиля, не Config defaults.

Пользовательский ZIP SHA256 `a8e0bfa033e0a02c460c30b02f34a5c64ece85b05003512941387d3cf1f319a2`, 3831196 bytes. Встроенный verifier проверил все301 source files, original paths/bytes/executable bits: полный tree совпал;352 Mac metadata entries исключены. GitHub отдельно подтвердил commit→tree. Полный SOURCE_RECEIPT.json, исходный ZIP и verifier сохранены в downloadable evidence; compact receipt в Git. .git и measurement DB в ZIP нет; это не препятствовало локальным тестам/replay.

Ветка `research/R4-H39` создана от baseline после проверки ID. PLAN до train IO: **28afa1e554d71093164145b250b11e47fff95d22**, 26.09.2026 08:45:02 UTC. Prerequisite source **8ce1a1b708aa72e6f2126c77c023647f6febf247**: шесть Git blobs точно совпали с локальными bytes, четыре SHA256 проходят manifest. Это код диагностики, не измеренный runtime candidate. Поздние report/checkpoint SHA указаны отдельно в PUBLICATION.json и PR. Другие ветки, moving main, опубликованные отчёты и dataset не изменялись; merge/auto-merge отсутствуют.

## Реальная реализация и заранее заданное правило

Добавлены foundation.py, selective stage.py,22 diagnostic tests, source manifest и отдельный train-only workflow. Core/readout/Timeline/ROS/default/physics/scorer/masks/fault placement не менялись. Checkout/launch **не включает интервальную ассимиляцию**.

Все64 train /27 групп должны быть проверены; sorted group IDs делятся18 fitting/9 check, wire-дубликаты исключаются только из статистики. Новизна sample определяется timestamp. Для основания нужны меняющиеся ненулевые binary CDR float64 speeds со свежей causal командой; постоянная скорость/нулевой plateau и округлённый CSV не служат доказательством.

Фиксированный offline lattice estimator: q∈[10⁻⁶;0.5]м/с, shift∈[0,q), fit-only proposals/coherence и ровно3 trimmed OLS refinements; full-sample error≤max(10⁻¹⁰,.001q),≥99% group-balanced support и≥80% qualified groups, отдельные traction/coast/brake checks. Наибольший прошедший fitting q фиксируется до check, без check-refit. Минимум8 fit/4 check групп на канал, каждая≥1000 samples/100 levels/span≥1м/с. Полный неизменный метод — research/R4/H39/PLAN.md.

Практический порог заранее: **q²/(12σw²)≥.01**, σw=.1м/с, то есть **q≥0.0346410161514м/с**. Дополнительно реализован exact interval sweep необходимого shift-invariant условия на continuous practical q-range по disjoint pairs. Эти пороги не подстраивались: train ещё не читался. При неразличимом/микроскопическом q предусмотрен INCONCLUSIVE, не accuracy REJECTED. Сейчас даже этот scientific prerequisite не измерен: **train bags0/64, q_front=q_rear=null**.

При будущем prerequisite PASS допускается только один interval-conditioned scalar Gaussian candidate, с raw hard gates/d learning/stop/zero-lock/quarantine и correlated pair floor. Этот кандидат, actual-gain hook и finite float64 tail fallback здесь **не реализованы**.

## Свежий локальный baseline replay — не H39 accuracy

Обработаны все17 development bags /7 групп и56 исходных fault-сценариев через неизменные evaluate.score/replay/match/distance и v6 group-macro summary. Factory создаёт полный v8 и использует returned Estimate.v/s. Оба legacy labels создают v8; второй — повторный baseline, не H39.

Проверенный development-export: run36174399106/1, ZIP SHA256 `5a840289a44b90d118847b33cdab2d3820ede3d92678bef350ed475f40c47fce`. До NumPy IO проверены роль, состав17 bags, group/bag hashes по R4 split и каждый export payload hash. Вложенный OLD baseline source не использован. Это replay проверенного экспорта, не новый локальный SQLite replay и не замена train.

| Метрика, development | Исполненный v8 | H39 |
|---|---:|---:|
| Clean group-macro RMSE, м/с |0.09266814298282507|N/A|
| Original fault-event RMSE, м/с |0.2375486120563008|N/A|
| Pooled clean RMSE, м/с |0.1293056944774334|N/A|
| Scalar-span distance RMSE, м |5.310295004801444|N/A|
| Matched clean samples |394221|N/A|
| False stops clean/fault |0/0|N/A|
| Original unrecovered comparisons |4|N/A|
| Causal errors / unexpected resets |0/0|N/A|

Пять fingerprint-полей совпали **точно, delta=0.0**. Два baseline replay дали одинаковые metrics/counters,358906 output ticks на модель. Reference:19 clean и60 fault bag/receiver comparisons; missing=null, не0. Полные результаты,17 per-bag checkpoints, access/hashes и146 строк per-bag/receiver/case CSV находятся в evidence. Wall13.652965с — offline replay, не ROS latency. Distance scalar/reanchored, не XYZ/ENU/полный terminal drift. **Выигрыша/регрессии H39 не измерено.**

## Математика и выполненные тесты

При x~N(μ,P), analog y=x+ε, ε~N(0,R), bin[z−q/2,z+q/2], S=P+R, λ и Vt — mean/variance standardized truncated normal:

`μpost=μ+P*λ/sqrt(S)`; `Ppost=P−P²*(1−Vt)/S`.

Wolfram explicit worksheet проверил q→0 Gaussian point-update, variance bounds и frozen-R sensitivity **K_eff=P*(1−Vt)/S**. Здесь до variance floors **1−Ppost/P=K_eff**, но это не secant gain и не производная по residual-dependent R. Fully correlated pair retains R, not R/2. **Power::infy/Infinity::indet warnings сохранены**; нерелевантный semantic WolframContext не использован.

Независимая mpmath quadrature/differentiation: **42 случая,80 digits**, standardized centers−40…40, widths10⁻⁸…3; maximum difference<2.52×10⁻⁶⁹. Это проверка формул, не float64 runtime/tail fallback и не доказательство точности switched observer.

Локально реально PASS: **156 baseline tests +43 research-integrity +22 H39 diagnostic tests**, compileall. Synthetic shifted lattice/constant/continuous/no-signal, timestamp/duplicate/stale/future/prefix/input immutability и interval-sweep checks — только проверки diagnostic implementation. Runtime feature-off/slow-start-stop/zero-lock H39 tests не заявляются: нет кандидата.

## Реальный недоступный этап

Локальный selective stage.py вызван: URLError `[Errno −3] Temporary failure in name resolution` на public download API, до dataset download/SQL. Web/direct-download пути тоже не получили bytes. В доступном локальном наборе есть development, но нет64 exact train inputs.

Собственный [Actions run36231320102](https://github.com/jabrailkhalil/hack/actions/runs/36231320102), job108374897353: completed/**failure**, steps=null, artifacts=[]. Job log endpoint вернул404 BlobNotFound. Check run сообщает одну annotation, но connector отвергает endpoint её чтения: **первопричина не установлена**. Billing/quota failure не объявляется доказанным. Повторный run не запускался. Обычный CI36231320061 тоже failure по всем4 jobs, без выполненных steps. Локальные tests не делают CI зелёным.

Не выполнены: train lattice/check/posterior-effect, runtime candidate, candidate development/safety/regressions, validation freeze/run, installed enabled ROS2CPU/500MB/оба clocks/latency/RSS и candidate CPU benchmark. Final/test payloads не открывались. No data/execution — **NOT_EVALUATED**, не научный REJECTED и не INCONCLUSIVE по измеренной решётке.

## Статусы и воспроизведение

source_status=VERIFIED; data_status=PARTIAL; execution_status=BLOCKED; scientific_verdict=NOT_EVALUATED; candidate_implemented=false; measured_source_sha=null; accuracy_contract_evaluated=false; accuracy_contract_passed=false; validation_opened=false; test_opened=false; enabled_runtime_verified=false; ready_to_merge=false. Публикация независима: checkpoint/draft фиксируют незавершённое исследование. Report commits с [skip ci] не меняют CI guards и не имитируют успешный run.

```bash
git fetch origin research/R4-H39
git switch --detach 8ce1a1b708aa72e6f2126c77c023647f6febf247
python -m pip install -r requirements-research.txt
sha256sum -c research/R4/H39/MEASURED_CODE.sha256
python -m unittest discover -s research/R4/H39 -p 'test_*.py' -v
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
python research/R4/H39/stage.py --output /tmp/h39-train-input-new
python research/R4/H39/foundation.py --data-root /tmp/h39-train-input-new/data --output /tmp/h39-foundation-new
```

Следующий незавершённый этап — получение exact train inputs и запуск **неизменного** foundation.py, не новый подбор и не validation. Новые output directories обязательны. Поздний reproduce_baseline.py и математический diagnostic code реально исполнялись локально до публикации; связь через hashes/исходники, не выдуманный pre-run commit.

Источники: H25/PR41 и H26/PR42 прочитаны; DOI10.1016/j.amc.2021.125960 — metadata/abstract (logarithmic quantization/packet disorder, не доказательство uniform grid); Sukhavasi/Hassibi arXiv0909.0996 — HTML abstract, не full text. Consensus/Scite не вызывались после известного quota stop. Подробнее — SOURCES.md и REPORT_EXTENDED.md в downloadable evidence.
