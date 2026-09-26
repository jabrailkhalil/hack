# R4-H32 — NOT_EVALUATED: кандидат реализован, development заблокирован

**Исследовательский артефакт, не готов к merge.** Основание гипотезы проверено на реальных train-записях; единственный кандидат реализован и прошёл локальные проверки. Парное измерение точности на development не состоялось: GitHub Actions дважды завершил job до выделения runner и до выполнения первого шага. Это **не REJECTED гипотезы** и не положительный результат по точности.

## Версии и последовательность

| Назначение | Значение |
|---|---|
| Полный baseline | `e3b0c9c039d2953fbfcda51231263d38ef9f1024` |
| Git tree baseline | `eae49a504bc59b5c9b408445150bef32e111956f` |
| ZIP SHA256 | `a8e0bfa033e0a02c460c30b02f34a5c64ece85b05003512941387d3cf1f319a2` |
| Исходники реальной baseline-only диагностики | `b25385074e63d7dbf5d0ce7806dd0578f5bec063` |
| Foundation checkpoint | `5c6a80ff12227dacc259da52a35b1399b22075fa` |
| PLAN до реализации/измерений кандидата | `abacda82c1856e921a940894a1c8265b249c06e9` |
| Реализация и локально проверенный код | `3115b66f4faaf6f2327b4427aff54feb6c69d8d7` |
| Measured candidate SHA на реальных данных | **N/A** |
| Validation freeze | **N/A** |
| Ветка | `research/R4-H32` |

ZIP прочитан полностью встроенным verifier из задания: все **301 файл**, исходные bytes, пути и executable bits дали точный pinned tree. 352 файла __MACOSX исключены только как metadata. Отдельный GitHub read подтвердил связь commit→tree. Pristine распакован в новую директорию; candidate — отдельная копия. Полный SOURCE_RECEIPT.json и неизменный исходный ZIP сохранены в пакете. Отсутствие .git не выдаётся за блокировку локального кода; фиктивной Git ancestry не создавалось.

Baseline — настоящий `GuardedReadoutObserver` / `champion_v8.yaml`, gain1/holdoff.5, adaptation.5, time-compensation0, quarantine1.5; 20 Hz/delay0. YAML/JSON совпадают. Семь исполняемых исследовательских файлов и PLAN отдельно сверены с опубликованными Git blob SHA. Source manifests не подменяют реальный development replay.

## Реальное основание на train

[Foundation run 36230458244](https://github.com/jabrailkhalil/hack/actions/runs/36230458244) завершён success. До него опубликован FOUNDATION_PLAN с минимумом 100 material steps и 3 исходных групп, в каждой не менее 10; порог endpoint difference — 1e-6 м/с².

| Показатель baseline-only train | Результат |
|---|---:|
| Train bags / исходные группы | 64 / 27 |
| Vehicle input events | 2 646 426 |
| Output ticks, включая WAITING | 1 370 779 |
| Шаги с наблюдаемой сменой команды | 99 560 |
| Material hypothetical drive endpoint differences | 93 833 |
| Группы с не менее 10 material steps | 25 |
| Медиана абсолютного drive endpoint difference, м/с² | 0.003324629050 |
| p95, м/с² | 0.017798271239 |
| Максимум, м/с² | 0.075026135110 |
| Медиана положения смены внутри шага | 0.57203936 доли шага |
| Ошибки причинности baseline probe | 0 |

**Это расчёт альтернативного endpoint на исходном pre-state baseline без обратного воздействия на baseline.** Это не ошибка относительно ground truth, не measured candidate output и не доказательство physical actuation time. Только три vehicle-топика; train GNSS не читался. Роль train извлечена из проверенного organizer ZIP отдельно; validation/test DB не извлекались и не декодировались. Скачивание общего сжатого ZIP не объявляется отсутствием копирования всех его compressed bytes.

Foundation archive: `R4-H32-foundation-36230458244-1`, artifact10901882920, 2 277 654 bytes, SHA256 `019cf24d0cc0d54a5c997177ac351afcaab8aa7f563483bea3ce93c203dea8bf`, retention30days, expires26.10.2026. Архив скачан, его SHA256 проверен; полные per-bag JSON, access journal и logs сохранены. Отдельный foundation_per_bag.csv содержит64 строки, не 17 фиктивных development метрик.

## Реализация единственного H32_event_time

`factory.py` читает полное verified core и заменяет ровно три строки propagation drive_a на вызов helper в изолированном методе. Через MRO `CommandEventObserver → CommandEventMixin → GuardedReadoutObserver → HookedCore → Observer` этот метод вызывается настоящим guarded readout. Оригинальные классы/файлы не модифицируются. Сохраняются конечное a_model, Euler velocity, resistance, Q/R, disturbance, wheel assimilation, readout, stop и quarantine; H08/H17/H30 не добавлены.

`CommandEventTimeline` содержит только hook после успешного controller ingest. Внутри ограниченной очереди упорядочиваются уже поступившие события; весь bag по будущим stamp не сортируется. Target в substeps зависит от прежней outer-step скорости. Предел —31 pending+1 predecessor, горизонт.5с; equal-value refreshes не дробят constant-command arithmetic. При потере истории/overflow или stale current command — явный legacy fallback и счётчик. Future overflow не воздействует на более ранний output; поздняя команда не переписывает опубликованное прошлое.

В paired driver feature-off фактически проходит через тот же унаследованный Timeline с **no-op delivery hook**, а не через новый временной алгоритм: исходные ingest/advance и их счётчики сохраняются, это проверено exact comparison. Формулировку PLAN про исходный Timeline следует понимать как неизменные temporal semantics, не тождественность Python-типа. Эта деталь раскрыта до любого candidate data measurement; PLAN не переписан.

При событии ровно на правой границе длительность новой команды в прошедшем шаге0: drive совпадает с old-command-only шагом, **не** с legacy whole-step-new-command на этой смене. При постоянной команде и левограничной смене — прежняя арифметика. Интервал потери future history хранится только скалярами; counts имеют фиксированный набор ключей.

SHA256 `event_time.py`: `f916668663e3bb2825b3ff180522715d6c9a415829dbc14b1b7e77bcc5833d56`; `factory.py`: `5bd45fb7442969865d22cc09b7f30a7fcba685f3fc3169983659e393f4d4b62e`; изолированный patched core: `cbb99a186c32e7e2772b6c72285abcc238cd8e71d4022abc3220d516183a1c59`.

**Обычный checkout/штатный ROS launch не включает H32.** Для программного replay нужны оба factory и delivery hook:

```python
import sys
sys.path.insert(0, 'research/R4/H32')
from support import profile
from factory import candidate, CommandEventTimeline
observer = candidate(profile()[0], enabled=True)
timeline = CommandEventTimeline(observer, rate_hz=20.0, delay_s=0.0)
# timeline.ingest(channel, Sample(...)); затем timeline.advance(...)
```

`core_hook.patch` — диагностический diff трёх строк, **не самостоятельный deploy patch**: не применять его к canonical node без helper/factory. Полный candidate patch добавляет исследовательские файлы, сохраняя canonical default.

## Что фактически проверено

Локально, затем повторно на публикуемых исходниках: **156 исходных unit +43 research-integrity +32 H32 tests PASS**, compileall PASS. Python3.13.5, NumPy2.3.5, SciPy1.17.0. Seven-file Git blob audit и точный PLAN blob PASS.

Специальные проверки:6000 feature-off ticks по полному Estimate/всем inherited state;6000 constant-command ticks,1600 probe identity ticks;20000 dense ticks с bounded state; около обеих границ step/impulse, несколько событий, late/duplicate/future, availability-prefix, stale, malformed, overflow/horizon, reset/seek, low-speed zero-lock, quarantine,true-stop, согласованность v/s/a. Отдельный synthetic scorer smoke:3000 input events,620 output ticks, feature-off arrays/counters exact и14 fields независимого canonical driver exact. **Это не реальный development fingerprint.**

План/driver предусматривают все17 development bags, original faults, pinned low-speed/common-mode suites, transition+dropout диагностику, full-faulted-bag distance/residual delta_s, одинаковый scorer/masks/schedule, и6 AB/BA пар стоимости. Они **не были выполнены на реальных development данных**. Не утверждается, что непроверенный полный driver уже прошёл dataset-level end-to-end.

## Точный блокер исполнения

[Development run 36231386474](https://github.com/jabrailkhalil/hack/actions/runs/36231386474), один и тот же source3115b66, две попытки:

| Attempt | Job | Runner ID | Выполненные steps | Conclusion |
|---|---:|---:|---:|---|
| 1 |108375087479|0|0|failure|
| 2 |108375484374|0|0|failure|

Это остановка до выделения runner/checkout; изменение алгоритма не исполнялось. Первый запрос job logs вернул404 BlobNotFound. Текст provider annotation недоступен через текущий GitHub connector (endpoint отклонён400), поэтому **причина вроде исчерпания minutes/billing не установлена и не утверждается**. Сделан ровно один инфраструктурный повтор без изменения source; дальнейших повторов и изменений quota/ACL/платных ресурсов нет. Стандартный source CI36231386447 также имеет failure checks; он не объявляется зелёным.

Локальный штатный downloader остановился с `URLError: [Errno -3] Temporary failure in name resolution`. Альтернативная попытка открыть публичный Yandex share/download API через web также не дала доступа; container download не разрешил URL без успешного просмотра. Локальных db3 нет. Источники, публикация, данные и выполнение — разные статусы: запись в GitHub продолжает работать, source проверен, train foundation измерен, development execution заблокирован.

## Accuracy / runtime: N/A

Clean/fault/pooled/distance RMSE baseline/candidate на R4 development: **N/A**, per-bag accuracy **N/A**, real activation **N/A**, CPU step/replay **N/A**, installed enabled ROS **NOT_RUN_BLOCKED_BEFORE_DEVELOPMENT**. Никаких нулей вместо отсутствующих метрик. Старые v8 development fingerprints в PLAN — только ожидаемый контроль, здесь не результаты нового исполнения.

Validation и final/test не открывались; кандидат перед validation не выбран, freeze не создан. `accuracy_contract_evaluated=false`, `accuracy_contract_passed=null`, `scientific_verdict=NOT_EVALUATED`, `ready_to_merge=false`. Тесты не опровергают всё семейство и не подтверждают выигрыш.

## Математика и прочитанные источники

Для одного переключения через s от начала шага h Wolfram проверил
`d_event - d_legacy = (T0-T1)*(1-exp(-s/tau))*exp(-(h-s)/tau)`, constant-target/left/right/zero-step пределы и отсутствие counterexample для convex combination ограниченных target. Это только первый порядок привода; не теорема устойчивости всего переключаемого observer.

Прочитаны PR30/H17, PR44/H30, PR25/H08. Primary MathWorks c2doptions прочитан на уровне HTML-определения ZOH (piecewise-constant input); MATLAB не исполнялся. Consensus/Scite quota stops не обходились. Inputs/output Wolfram и SOURCES сохранены, physical source-stamp semantics остаётся неизвестной.

## Команды и следующая точка возобновления

Фактически выполнены локальные source verification, три suites и compileall; удалённо stage_data train + baseline-only probe. Development ниже — **подготовленная, но не исполненная успешно команда**:

```bash
git checkout 3115b66f4faaf6f2327b4427aff54feb6c69d8d7
python -m pip install -r requirements-research.txt
PYTHONPATH=src/reserve_odometry python -m unittest discover -s tests -v
python -m unittest discover -s research/tests -v
python research/R4/H32/test_h32.py
python -m compileall -q research/R4/H32
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
python research/R4/H32/stage_data.py --role development
python research/R4/H32/run.py --output /tmp/H32-development-new --workers 2
```

Продолжение начинается с доступности исполнения/данных и **этого же** development, не с нового fitting/отбора вариантов. Foundation и PLAN уже опубликованы, повторять их подбор не требуется. При отрицательном development validation запрещён; при положительном нужен отдельный опубликованный exact freeze до validation. Этот отчёт не обещает фоновых запусков. Merge/auto-merge/main/чужие ветки не менялись.
