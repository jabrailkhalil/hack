# H16 / R2-v7-fixed — REJECTED на development

**Исследовательский артефакт, не готов к merge.** Оба заранее объявленных кандидата снижают original fault-event group-macro RMSE на настоящем development, но нарушают зафиксированный дистанционный допуск 1%. A: fault −5.779141%, distance +1.177250%; B: fault −6.827826%, distance +1.182291%. Порог не изменялся. Ни один кандидат не выбран. Validation не открывался, candidate-freeze для него не создавался. Final test не оценивался.

**Механизм:** активен; средняя ошибка рекурсивного прогноза на отложенных train-группах и fault aggregate на development уменьшаются. Это наблюдаемый положительный частный результат, не подтверждение общего R2-контракта и не доказательство независимого обобщения. Длинный выбег и отдельные группы заметно регрессируют. Семейство multi-step identification целиком не отвергнуто.

## Происхождение и неизменяемые снимки

- Round: R2-v7-fixed. Baseline: `65bba39ed05c781f3f69a65c02f69931152cbfd9`.
- Ветка: `research/round2-H16`; начата от указанного SHA, не от движущегося main.
- PLAN до первого эксперимента: `49cd275b8d1169ef1344f5b201f71eaff635aab3`, `research/R2/H16/PLAN.md`.
- Исполненный код + manifest до экспериментов: `9b382e352ea6037a71182bedd98bbc34c4b3098f`.
- Все исходные измерения и фактические A/B-конфигурации: `af5ee198617e5ecb262e78c529cea3581927557b`.
- Actions: [run 36184448864 / attempt 1](https://github.com/jabrailkhalil/hack/actions/runs/36184448864), workflow source `17884c21e7d2b6c284c7fbde7172e92f5c8d157d`.
- Данный REPORT и post-hoc таблицы добавлены позднее; они не являются новым обучением или новым прогоном.

[Исходный evidence directory](https://github.com/jabrailkhalil/hack/tree/af5ee198617e5ecb262e78c529cea3581927557b/reports/research_R2/H16/H16-36184448864-1). Архив Actions `H16-evidence-36184448864-1`, artifact 10885327986, SHA256 `f23c013585e40a0b9ac6e1333556fa6a9abea5186c857ae430989ec2e107c548`. Внутри `measured-source.zip`, PLAN, SOURCES, worksheet, логи, source manifests, train/development JSON/CSV, per-bag и access.

## Реальный baseline и что изменено

Baseline — `GuardedReadoutObserver` с эффективным `guarded_readout_v7.json/yaml`, не `Observer(Config())` и не один adaptive_v5. Readout gain=1, holdoff_s=0.5, inner wheel_time_compensation=0, adaptation_tau_s=0.5. Канонический launch `odometry.launch.py`, executable `guarded_odometry_node`. Частота 20 Гц, намеренная задержка 0.

H16 изменяет способ offline-идентификации и полученные семь существующих эффективных физических параметров. Runtime core, guarded_readout, Timeline, модельная структура, legacy drive-before-Euler, R/gates, adaptation, stop/reacquire/zero-lock, интерфейсы и единицы не изменены. Масса, радиус, передача, КПД и масштабы датчиков не подбирались. Вся реальная оценка скорости/дистанции использует возвращаемые `Estimate.v/s`, а не внутренние поля.

44 исходных runtime/config/evaluator/data-role файла проверены побайтно по фиксированному git snapshot и SHA256 (`research/R2/H16/manifest.json`). Калибровки лежат отдельно, default не меняется. Отключение H16 — исходный v7 профиль с readout gain=1, **не** отключение guarded readout.

Прочитаны H03#20/H07#22, v6 и PR14/23; H11#26 изучен как соседний механизм, но не включён. Чужие R2 validation-результаты для выбора не использовались. Все ссылки на старые исследования — контекст, не цифры нового baseline.

## Предзарегистрированное обучение

Ровно две оптимизации: A — robust multi-horizon data loss; B — тот же loss + фиксированная регуляризация 0.01 к действующей калибровке. Начало обоих theta0, исходные v3 bounds, без restarts/дополнительных вариантов. `least_squares(trf, jac=2-point, max_nfev=80, ftol=xtol=gtol=1e-8)`.

Для h∈{0.5,2,5} с: σ_h=0.1+0.2h м/с, r_h=(v_pred−y_wheel)/σ_h; ρ(r)=2(√(1+r²)−1). Data loss усредняется сначала по горизонтам, затем окнам, затем исходным группам. B добавляет `0.01*mean(((theta-theta0)/scale)^2)`, где scale=max(abs(theta0),0.1*(HIGH−LOW)). Нормировки безразмерны, зафиксированы до fitting. Stable transformed residual реализует именно этот robust loss независимо от веса группы.

На каждой theta начальное состояние получено настоящим GuardedReadoutObserver на 5 с причинного warmup до anchor включительно. Затем в течение 5 с predictor получает только разрешённые команды и собственные v/drive/d. Wheel target не подставляется в drive_target или resistance, начальные v/d не оптимизируются по концу окна. Псевдоцель — средняя held-wheel скорость на трёх горизонтах; это не независимая ground truth и она сохраняет ошибки/возраст колёс. Readout прошлой пары истекает до первого оцениваемого горизонта 0.5 с. Проверено совпадение vectorized recurrence с настоящим runtime на всех 175 baseline-окнах: max absolute delta **4.440892098500626e−16**. Включённые A/B проходят отдельную rollout-parity проверку в safety suite.

Все 64 train-bag прочитаны штатным train-loader, только три vehicle-топика; train GNSS закрыт. Фиксированный group split: 20 fitting и 7 check-групп по metadata. Реально подходящие окна имеются в 19 fitting-группах /145 окнах и 5 check-группах /30 окнах. Всего 175 окон из 59 bags: traction58, coast58, braking59. Пять bags без окон сохранены в inventory, а не заменены. Предзарегистрированный минимум покрытия пройден.

До трёх окон/bag: средний по времени допустимый anchor каждого command-режима; маска свежих согласованных колёс/команды на всём warmup+forecast. Никакого выбора по ошибке кандидата или GNSS. Группы не разделялись между fit/check. Отдельных per-group refits не было: оценивается перенос ошибки между группами, не дисперсия заново обученных коэффициентов.

### Loss, горизонты и режимы

| Роль / безразмерный data loss | Baseline | A | B |
|---|---|---|---|
| fitting | 0.215642086 | 0.180807701 | 0.181024498 |
| check | 0.238873600 | 0.200265043 | 0.199746793 |

A: nfev=29, njev=16, **141 фактический residual call**, завершение по ftol. B: nfev=22, njev=10, **92 calls**, также ftol. Ограничение max_nfev не нарушено: SciPy отдельно считает numerical-Jacobian calls. Итоговый B objective с регуляризацией — 0.182562921102; B data loss в таблице не включает penalty.

| Роль | Горизонт, с | Baseline RMSE | A RMSE | B RMSE |
|---|---|---|---|---|
| fitting | 0.5 | 0.052264719 | 0.052499417 | 0.052448571 |
| fitting | 2 | 0.198312713 | 0.168372865 | 0.168916564 |
| fitting | 5 | 0.671760647 | 0.617217006 | 0.618287627 |
| check | 0.5 | 0.084499953 | 0.076560955 | 0.076294371 |
| check | 2 | 0.289906416 | 0.255254113 | 0.254600874 |
| check | 5 | 0.518702346 | 0.469214620 | 0.470500699 |

Все ошибки скорости в таблицах — м/с. Небольшая регрессия fitting на 0.5 с сохранена, не скрыта за общим loss. На check средний RMSE уменьшается на всех трёх горизонтах, но это не универсальное улучшение по режимам:

| Check / режим в начале окна | Горизонт, с | Baseline RMSE | A RMSE | B RMSE |
|---|---|---|---|---|
| traction | 0.5 | 0.054788499 | 0.052822300 | 0.052981990 |
| traction | 2 | 0.149368603 | 0.129167910 | 0.131960427 |
| traction | 5 | 0.437762123 | 0.407798047 | 0.416474122 |
| coast | 0.5 | 0.022101215 | 0.019950472 | 0.019967192 |
| coast | 2 | 0.135851379 | 0.113713154 | 0.112883640 |
| coast | 5 | 0.116444972 | 0.183672490 | 0.181098966 |
| braking | 0.5 | 0.109576761 | 0.097593351 | 0.097174721 |
| braking | 2 | 0.380771090 | 0.347017628 | 0.345768615 |
| braking | 5 | 0.628861811 | 0.576641367 | 0.574431047 |

Режим — команда **в начале окна**; внутри окна она может меняться. На check-coast, h=5 с, baseline 0.116444972 → A 0.183672490 / B 0.181098966: явная регрессия. В check-группе `e894436afa9dd9f1` 5-секундный RMSE 0.203967354 → A 0.327340433 / B 0.338550692. Прежний критерий сильной зависимости (macro или большинство check-групп) не нарушен, однако отдельная плохая группа остаётся. Нельзя объявлять все режимы/группы устойчиво улучшенными.

### Фактически измеренные коэффициенты

| Эффективный параметр | Единицы | Baseline | A | B |
|---|---|---|---|---|
| force_per_mass | м/с² | 1.1884343181 | 1.1292263811 | 1.13897219492 |
| power_per_mass | м²/с³ | 7.02183833715 | 7.9514448567 | 7.97379412407 |
| brake_per_mass | м/с² | 1.13922023509 | 0.914979690236 | 0.914917600492 |
| rolling_per_mass | м/с² | 0.0522432703667 | 2.07775819537e-07 | 0.00174194826862 |
| quadratic_per_mass | 1/м | 1.2554870052e-21 | 0.000196515469257 | 6.70193670443e-05 |
| command_exponent | 1 | 0.520743240004 | 0.435914744794 | 0.437034561635 |
| actuator_tau_s | с | 0.392761914585 | 0.473604403198 | 0.47963214183 |

A близок к нижней границе rolling_per_mass (по предобъявленному near-bound допуску), B near-bound параметров не имеет. Active-mask solver у обоих нулевой. Scale-normalized Jacobian singular values сохранены; значения B включают регуляризационные строки, поэтому улучшенная обусловленность B не доказывает физическую идентифицируемость. Масса/силы по отдельности не идентифицировались.

YAML SHA256 A `eec9c592df71687cde326cfaec21c5445ac759899089f1377625900fb480cbe0`; B `ee1ad47597f2aec94bc9f0da6bc6d3598a1a94f35b6caca77a2c4532699e0be1`. Это хеши исходных execution YAML, сохранённых без изменений. При post-hoc проверке экспорта обнаружены целочисленные YAML literals у части model-параметров, которые нода объявляет double. Измерения использовали JSON/Config, не ROS YAML. Отдельный [патч](calibration.patch) добавляет те же численные коэффициенты с явной double-сериализацией (`40000.0`, а не `40000`) в `research/R2/H16/variants/`. Численные значения всех model-параметров сверены с исходными A/B JSON; это исправление упаковки, не новый fit/кандидат/replay. Исходный экспортёр и train YAML не переписаны. Применение patch и статический паритет PASS; установленная ROS-нода по-прежнему не запускалась. Checkout не переключает default.

## Однотипный измеритель на настоящем development

В sanity на development-bag `30618_0652866c` канонический factory и candidate-off дали **29207 точно одинаковых опубликованных outputs**, одинаковые runtime counters и 36 совпадающих metric fields против независимого неизменного `guarded.compare`; max delta0. Единственный исходный catchup сохранён; causal errors/resets0.

Затем оба варианта измерены на всех **17 development-bag /7 группах**. В clean reference доступен в 6 группах /19 bag-receiver сравнениях, 394221 matched sample. Семь bags без обоих receivers и один отсутствующий master сохранены как N/A. По исходному vehicle-only anchor правилу получено **56 original fault-сценариев на14bags**, 60 сравнений с reference в5группах. У `30618_1551d0a9`, `30618_e151d6e4`, `30639_0ab96c59` нет допустимого anchor; они не исключались из clean. Это **development**, не19-bag validation и не независимый final test.

Используются неизменные `ev.score/replay`, `ex.match/metrics`, scalar distance и `v6.summary`, одинаковые timestamps/маски и оба доступных receivers. Fault suite исходный: front bias+5м/с на5с, both dropout5/10с, both lock3с; тот же20-секундный warmup и10-секундное recovery-окно. Новый driver лишь подставляет GuardedReadoutObserver и семь параметров; старые pins/метрики/aggregation не переписаны. Baseline между A/B повторён реально и совпадает по всем metric/runtime/diagnostic полям: это 34 clean и 112 fault исполнения именно baseline в двух парных сравнениях (146 receiver-record сравнений baseline, включая missing reference).

| Метрика / development | V7 baseline | A | Δ A | B | Δ B |
|---|---|---|---|---|---|
| Clean group-macro RMSE, м/с | 0.092668143 | 0.092625524 | -0.045991% | 0.092630728 | -0.040375% |
| Original fault-event group-macro RMSE, м/с | 0.237548612 | 0.223820343 | -5.779141% | 0.221329205 | -6.827826% |
| Pooled clean RMSE, м/с | 0.129305694 | 0.128998730 | -0.237395% | 0.129000792 | -0.235800% |
| Scalar-span distance group-macro RMSE, м | 5.310295005 | 5.372810453 | +1.177250% | 5.373078122 | +1.182291% |

| Дополнительная метрика / development | Baseline | A | B |
|---|---|---|---|
| Clean MAE, м/с | 0.034933353 | 0.034844207 | 0.034845185 |
| Clean signed bias, м/с | 0.006390677 | 0.007161286 | 0.007164696 |
| Fault+recovery-window MAE, м/с | 0.153796529 | 0.140614779 | 0.139647859 |
| Fault+recovery-window signed bias, м/с | 0.011170308 | 0.046801806 | 0.047653154 |
| Среднее recovery, group-macro, с | 0.724358285 | 0.667327035 | 0.667327035 |

Coverage394221 одинаков у всех. False stops clean/fault0/0 у всех. Unrecovered4 у baseline/A/B: это те же четыре исходных fault-сравнения `30639_e4379d7f/rover`; новых нет. Нулевые counters нельзя переносить с этой роли на validation. Causal errors и unexpected resets0 во всех исполненных сравнениях. Clean per-bag tolerance не нарушен. Средний recovery улучшается, но есть локальные задержки.

### Контракт и решение

Общий контракт неизменен: ≥2% clean или ≥5% original fault gain; clean/fault/pooled не хуже более0.5%; distance не хуже более1%; per-clean-bag/receiver не выше baseline+max(0.005м/с,5%); без потери coverage, новых false stops/unrecovered/causal/reset. На development для продвижения требовались non-regression/safety/activation; minimum gain не был обязательным, хотя фактически пройден обоими.

Для distance допустимый максимум = 5.363397954849 м. A=5.372810453407, B=5.373078122499 — **оба выше**. Единственная aggregate admission-причина отказа `aggregate_regression:distance_rmse`. Допуск не округлялся/не смягчался. Selected=null, verdict=REJECTED.

По PLAN при отсутствии допустимого development-кандидата validation запрещён. `execution.json`: freeze_sha=null; `validation-skipped.log` явно фиксирует отказ. Зелёный условный шаг workflow не означает выполненный validation. Папки validation/results.json нет, отдельного validation-freeze нет. Final/test SQL payloads не открывались. Штатный downloader распаковывает общий архив splits; это не выдаётся за отсутствие копирования байтов test-части архива. В measurement access только train/development.

## Локальные регрессии и активность

У A и B ухудшились7/19clean RMSE и7/19distance сравнений. Fault-event RMSE вырос у A в41/60, у B в37/60 сравнениях, несмотря на улучшенный group-macro. Разбиение original fault RMSE по исходным группам:

| Исходная группа | Baseline fault RMSE | A | B |
|---|---|---|---|
| 8269991eafa82c45 | 0.419757752 | 0.243112829 | 0.244331121 |
| 711abb923942f9fe | 0.125038907 | 0.156290422 | 0.148640975 |
| a8a4c11ebcc1dde2 | 0.166682281 | 0.169704798 | 0.167041567 |
| 70bb14d1c90f301f | 0.245582235 | 0.232204291 | 0.223964785 |
| a0c46036cc19092a | 0.230681884 | 0.317789374 | 0.322667578 |

В трёх из пяти fault-reference групп средний event RMSE хуже у обоих кандидатов. Выигрыш концентрируется в других группах; два GNSS receiver не считаются независимыми поездками. Bootstrap отдельных ticks не выполнялся и независимая статистическая значимость не заявляется.

Существенные примеры B (все исходные A/B строки сохранены в per_bag.csv):

| Bag / receiver | Показатель | Baseline | B | Абсолютная регрессия |
|---|---|---:|---:|---:|
| 30639_c31df386 / rover | scalar-span distance, м |28.322408035|28.809526614|+0.487118579|
| 30639_9c362687 / rover | scalar-span distance, м |19.212920563|19.490452682|+0.277532119|
| 30618_0652866c / master | dropout10с event RMSE, м/с |0.157804945|0.440905012|+0.283100067|
| 30618_0652866c / rover | dropout10с event RMSE, м/с |0.160412735|0.443244642|+0.282831907|
| 30618_27e994fc / rover | dropout10с event RMSE, м/с |0.245154505|0.474114832|+0.228960326|
| 30639_0ab96c59 / rover | clean RMSE, м/с |0.019389049|0.020403326|+0.001014276|
| 30618_0652866c / оба | dropout10с recovery, с |1.256544646|1.756544646|+0.5|

Последняя clean-регрессия +5.231% всё ещё меньше разрешённого абсолютного max(0.005,5%) порога; это не причина отклонения. Для A крупнейшая dropout10с/master регрессия 0.157804945→0.436956582; крупнейшая distance/rover 28.322408035→28.806675863. У обоих три замедленных recovery-сравнения, максимум+0.5с.

Изменение **не было неактивным**: у обоих221297 изменённых published-velocity ticks в7development-группах. На clean зарегистрированы фазы coast122784 /traction102220 /braking94831 ticks, включая initialization. FUSED101949 и STOPPED96538 у всех; MODEL_ONLY120113→120111, SINGLE_WHEEL248→250. Эти два изменения выбора канала происходят при прежних guards из-за иного модельного предсказания, не из-за удаления guard. `diagnostics.fault_trace` в per-bag JSON сохраняет published/inner v, s, drive_a, disturbance, mode и statuses до/во время/после fault.

Повышение signed bias и ухудшение дистанции согласуются с накоплением ошибки скорости, но причинный вклад отдельных коэффициентов здесь не изолирован. Это post-hoc интерпретация, не доказанная ablation и не основание для дополнительной настройки. Новых вариантов после измерений не добавлялось.

## Проверки, вычислительная стоимость и ограничения

В одном research job:144 исторических runtime-unit tests PASS;43 research-integrity tests PASS;15 H16 tests PASS; затем по15 тех же проверок с реально включёнными A и B — PASS. Проверены candidate-off и всё внутреннее состояние на1200 шагах, prefix, duplicate/future/stale/reset, zero-lock, NaN/bounds, отсутствие новых histories, train/test role isolation, отсутствие использования pseudo-target в rollout и паритет recurrence. Исторические release/source checks не удалялись. Python3.13.5, NumPy2.3.5, SciPy1.17.0.

Стоимость на одном реальном development-потоке, первые60с, warmup10с исключён из step-квантилей; threads1. Для каждого кандидата три AB/BA пары, то есть12replay; одинаковый сбор outputs, отдельные CPU/wall/step. Медианы повторов:

| Измерение | Baseline перед A | A | Baseline перед B | B |
|---|---:|---:|---:|---:|
| Replay CPU, с |0.059363903|0.059630388|0.059208841|0.059365363|
| Replay wall, с |0.059376821|0.059630125|0.059208461|0.059365064|
| Step p95, мкс |44.180775|43.445250|43.816275|44.246275|
| Process high-water RSS, байт |125652992|125652992|125734912|125734912|

Для каждого профиля output hash одинаков во всех его повторениях. RSS включает offline загрузку данных/NumPy/SciPy и не является RSS одной установленной ноды. Малые различия времени не трактуются как доказанное ускорение. Это не wall-paced ROS latency, не publisher→subscriber задержка и не тест под контейнерным лимитом2CPU/500000000байт.

**Свежий установленный и включённый H16 ROS offline benchmark в обоих clock modes не выполнялся**, поскольку accuracy-gate уже отклонил кандидатов. Generic CI с canonical profile не выдаётся за CI включённых A/B. Данные и запись GitHub были доступны; Scite full text/context заблокированы квотой и это отдельный научный пробел, не выдуманная проверка. См. SOURCES.md и реально исполненный wolfram.wl с результатом в SOURCES.

Результат ограничен frozen ролями/группами; train labels зависимы от колёс, возможен common-mode и timestamp bias. Scalar-span distance — переякоренный интеграл GNSS-speed, не xyz/ENU и не общий terminal drift. Check-coast и часть групп ухудшены. Семь effective coefficients не следует трактовать как независимо идентифицированные реальные масса/сопротивления/силы.

## Фактически выполненные команды и воспроизведение

Полные фактические команды в `.github/workflows/research-R2-H16.yml`, stdout/exit-файлы в данном run-directory. Последовательность выполненного исследования:

```bash
python -m pip install -r requirements-research.txt
PYTHONPATH=src/reserve_odometry python -m unittest discover -s tests -v
PYTHONPATH=src/reserve_odometry python -m unittest discover -s research/tests -v
PYTHONPATH=src/reserve_odometry python -m unittest discover -s research/R2/H16 -p test_h16.py -v
python tools/get_dataset.py
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
export H16_SOURCE_SHA=9b382e352ea6037a71182bedd98bbc34c4b3098f
R=reports/research_R2/H16/H16-36184448864-1
python research/R2/H16/run.py sanity --output "$R/sanity"
python research/R2/H16/run.py train --output "$R/train"
python research/R2/H16/run.py develop --train "$R/train" --output "$R/development"
python research/R2/H16/run.py benchmark --candidate "$R/train/A.json" --output "$R/benchmark-A"
python research/R2/H16/run.py benchmark --candidate "$R/train/B.json" --output "$R/benchmark-B"
# freeze/validate НЕ исполнялись: selected=null.
```

Повтор **уже измеренных калибровок**, без повторного fitting/нового подбора:

```bash
git fetch origin checkpoint/H16-result-36184448864-1
git worktree add --detach ../hack-H16-reproduce af5ee198617e5ecb262e78c529cea3581927557b
cd ../hack-H16-reproduce
python3.13 -m venv .venv-research
. .venv-research/bin/activate
python -m pip install -r requirements-research.txt
python tools/get_dataset.py
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
export H16_SOURCE_SHA=9b382e352ea6037a71182bedd98bbc34c4b3098f
R=reports/research_R2/H16/H16-36184448864-1
OUT="/tmp/H16-repeat-$(date +%s)-$$"
mkdir -p "$OUT"
python research/R2/H16/run.py sanity --output "$OUT/sanity"
python research/R2/H16/run.py develop --train "$R/train" --output "$OUT/development"
```

Включение отрицательного кандидата только для отдельного research worktree после обычной ROS-сборки/source:

```bash
ros2 launch reserve_odometry odometry.launch.py \
  params_file:="$PWD/research/R2/H16/variants/B.yaml"
# A включается аналогично через variants/A.yaml.
# Для result-checkpoint af5ee... сначала git apply /path/to/calibration.patch.
# Baseline: src/reserve_odometry/config/guarded_readout_v7.yaml.
```

Последний ROS launch — **инструкция воспроизведения, не утверждение о проведённом ROS benchmark**. [calibration.patch](calibration.patch) добавляет ROS double-сериализацию тех же численных параметров как research/R2/H16/variants/A.yaml и B.yaml. Оригинальные train/A.yaml и train/B.yaml не рекомендуются для ROS до проверки типов; используйте variants-профили. Хеши и проверка значений — в posthoc/ros-profile-parity.json, конвертер — posthoc/render_ros_profiles.py. Existing outputs runner отказывается перезаписывать. При дальнейшей работе нужен новый план/раунд, не подбор по неоткрытому здесь validation. Main, чужие ветки и опубликованные отчёты не изменены; merge и auto-merge не выполнялись.
