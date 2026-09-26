# R2-v7-fixed / H19 — REJECTED

**Исследовательский артефакт, не готов к merge.** Проверены два заранее объявленных порога одного bounded sequential detector. Ни один не достиг общего численного контракта; в диагностических инъекциях оба понижали вес неинъецированного канала. Это отказ конкретных кандидатов, не опровержение всего семейства CUSUM.

## Версии и фиксация

- Baseline: `65bba39ed05c781f3f69a65c02f69931152cbfd9`, **GuardedReadoutObserver**, guarded_readout_v7.yaml/json. Readout gain=1.0, holdoff=0.5 s; inner wheel_time_compensation=0, adaptation_tau=0.5; 20 Hz, delay=0. Сравниваются возвращённые Estimate.v/s, не inner v/s.
- Ветка: `research/round2-H19`, создана от общего SHA. H11/v8 не включался. Main и чужие ветки не менялись; merge/auto-merge не выполнялись.
- PLAN до испытаний: `a6549707c07375ad5fd7f955c12e6d1a76c797db`. Предэкспериментальное уточнение строгого 4 s epoch: `6c05cc423b5d5469fe86ce9454de297f6f114365`.
- **Измеренный commit алгоритма, обоих порогов, тестов и runner: `6f6b447d7d17de6ad39f896e9d22dee844eacc76`.** Этот отчёт добавлен позднее, без изменения алгоритма.
- Module SHA256: `73889c02a2cfc5eb9632a717aba016282e78de9d4598531db88badd25df56fee`; применённый isolated core SHA256: `e2195cb3fffaf8a2cfa99f2992865bc52174c03f1f1994030684d24c7774554a`.
- [Реальный Actions run 36184813159/1](https://github.com/jabrailkhalil/hack/actions/runs/36184813159) завершился **success**. Это успешное исполнение исследования, не eligibility кандидата.
- [Неизменяемый checkpoint](https://github.com/jabrailkhalil/hack/tree/09ac6c90c80b03adf44818608bf88771a060f11d/reports/research_R2/H19/36184813159-1), commit `09ac6c90c80b03adf44818608bf88771a060f11d`, ветка `checkpoint/R2-H19-36184813159-1`.

## Алгоритмическое изменение

H05/#17 учитывал историю уже зарегистрированных hard anomalies. Здесь накапливаются слабые нормированные innovations новых gate-passing samples и front-rear residual. Новая история ограничена и по времени, и по размеру: четыре CUSUM скаляра, два последних принятых peer samples и фиксированное число timestamps/флагов; O(1). Raw peer history живёт не дольше max_age, накопитель принудительно сбрасывается каждые 4 source seconds. Held/duplicate samples не начисляют evidence; первый sample или gap не начисляет отсутствовавшее время.

До wheel correction:

```text
r_i = (z_i - v_pred) / sqrt(P_prior + sigma_w^2 + Q_v*age_i)
d_i = (z_i - z_j) / sqrt(2*sigma_w^2 + (a_max*abs(t_i-t_j))^2)
```

Атрибуция i разрешена только при abs(r_i)>=abs(r_j)+0.5, abs(r_j)<=1, r_i*d_i>0, abs(d_i)>0.5, свежем peer/команде, допустимом skew и обеих скоростях по модулю >0.5 m/s. Иначе e_i=0. При атрибуции e_i=sign(r_i)*min(abs(r_i),abs(d_i),3).

```text
C_plus  = clip(exp(-dt/2)*C_plus  + dt*( e_i - 0.25), 0, 2)
C_minus = clip(exp(-dt/2)*C_minus + dt*(-e_i - 0.25), 0, 2)
```

Сравнены только `h03` (H=0.30 s) и `h06` (H=0.60 s); release=H/4. Эти имена — пороги H19, не номера других R1-гипотез. Noise/нормировка не обучаются на текущем выбросе. При единственном latch и сохраняющейся текущей атрибуции q_suspect=0.25; иначе исходный fallback. Weighted z, R умножается на len(accepted)/sum(q), без R/N. Подозрительный канал не участвует в FUSED disturbance adaptation, adapt_previous очищается. Статус SEQUENTIAL_DOWNWEIGHTED естественно отключает существующий guarded readout его штатной проверкой.

Hard gates, low-speed zero-lock/stop, bootstrap, reacquisition, физика, Timeline и формулы readout не изменены. Нет новых runtime inputs, GNSS/IMU, bag ID, fault oracle, ожидания будущей пары или тяжёлых зависимостей. При активной H19 изменение состояния может косвенно повлиять на последующие gates; универсальная эквивалентность при включённом механизме не заявляется.

Изучены отрицательные v6, H02/#15, H05/#17, H09/#24, успешные #14/#23 и соседний #26/H11. Исторические числа не подставлены вместо нового R2 исполнения.

## Измеритель, данные и порядок

Исходные evaluator score/replay/distance, research_v3 match/metrics и research_v6 group-macro summary побайтно сверены с fixed baseline. Подставляется только фабрика Observer. Legacy aliases baseline_v2/balanced_physics переименовываются после scoring; в данном driver baseline_v2 создаёт именно v7, не Observer(Config()). Точные timestamps, masks, оба reference receivers и source inputs общие для всех вариантов. Fault metadata остаётся во внешнем injector/evaluator.

Все **17 development bags / 7 групп**, reference в 6 группах / 19 clean bag/receiver-парах. 15 missing receiver-потоков сохранены как missing, не нулевая ошибка. 14 bags имеют исходный vehicle-only anchor: **56 original fault cases / 60 reference-сравнений**. Original placement/formulas не изменены: front+5 m/s 5 s, both dropout 5/10 s, both lock 3 s.

На тех же anchors отдельные **112 diagnostic cases / 120 reference-сравнений**: gradual +/-0.4 m/s (ramp4s + hold4s), intermittent +/-0.2 m/s (period0.5s, duty0.5, duration8s), оба колеса и знака. Специальная suite не заменяет original admission. Все события, маски, outputs и атрибуции сохранены; названия bags никогда не поступают в Observer.

Локальное execution использовало проверенный development-export H09, но только входы, не старый source/baseline. Remote repeat заново загрузил те же bags непосредственно из SQLite с role gate до IO, checksum и access journal. Параметры после локальных/удалённых результатов не менялись.

## Общий контракт и результаты development

Критерии сохранены: >=2% clean gain ИЛИ >=5% original fault gain; clean/fault/pooled regression <=0.5%; distance <=1%; clean per-bag/receiver <=baseline+max(0.005 m/s,5%); без потери coverage, дополнительных false stops/unrecovered/causal errors/reset. Этот же контракт заранее использован как development gate перед validation. Zero baseline проверяется абсолютной дельтой.

| Метрика | Baseline v7 | H19 h03 | H19 h06 |
|---|---:|---:|---:|
| Clean group-macro RMSE, m/s | 0.092668142983 | 0.092660660661 | 0.092668142983 |
| Original fault-event macro RMSE, m/s | 0.237548612056 | 0.237548612056 | 0.237548612056 |
| Pooled clean RMSE, m/s | 0.129305694477 | 0.129304306528 | 0.129305694477 |
| Scalar-span distance RMSE, m | 5.310295004801 | 5.310295004801 | 5.310295004801 |
| Matched clean samples | 394221 | 394221 | 394221 |
| False stops clean/original | 0/0 | 0/0 | 0/0 |
| Unrecovered original comparisons | 4 | 4 | 4 |
| Causal errors / resets | 0/0 | 0/0 | 0/0 |

h03 clean delta **-0.000007482322 m/s (-0.008074319%)**, pooled delta -0.000001387950 m/s (-0.001073386%); original fault delta **0**. Distance +1.24e-14 m — уровень floating-point арифметики, не содержательная регрессия. h06 основные агрегаты совпадают точно. **Минимальный gain не достигнут.**

Clean MAE baseline/h03: 0.034933352905 -> 0.034925820783 m/s. Signed bias: +0.006390677420 -> +0.006405174134 m/s (модуль немного вырос). P95: 0.090092790092 -> 0.090090146916 m/s. h06 без изменения. Все 60 original recovery_s совпадают, включая 4 None; group-macro confirmed recovery 0.724358284875 s, None не считаются нулём. Slow STOPPED при reference0.07..0.5 m/s: clean238 у всех, original/diagnostic0 у всех.

h03: 18/19 clean RMSE без изменения, один improved (`30639_e4379d7f/rover`: 0.138142126696 -> 0.138097232766). h06: 19/19 без изменения. Все per-bag/per-receiver/per-case значения, включая missing и регрессии: [CSV](https://github.com/jabrailkhalil/hack/blob/09ac6c90c80b03adf44818608bf88771a060f11d/reports/research_R2/H19/36184813159-1/development/per_bag_receiver_case.csv), [полные JSON](https://github.com/jabrailkhalil/hack/blob/09ac6c90c80b03adf44818608bf88771a060f11d/reports/research_R2/H19/36184813159-1/development/results.json).

## Механизм активен, но ошибается в атрибуции

| Диагностика | h03 | h06 |
|---|---:|---:|
| Weighted accepted updates, все наборы | 473 | 292 |
| Групп с активацией | 5 | 2 |
| Detected diagnostic cases /112 | 13 | 8 |
| Wrong-channel weighted updates внутри diagnostic fault | **173** | **133** |
| Clean weighted ticks /318865 | 12 | 0 |
| Clean alarm onsets | 6 | 0 |
| Clean duty, % | 0.00376335 | 0 |
| Clean onsets/min | 0.02258129 | 0 |

Clean false-alarm proxy укладывается в predeclared <=0.5% aggregate / <=1% каждой группы / <=2 onsets/min. Естественные faults не размечены независимо: все clean срабатывания консервативно считаются proxy ложной тревоги, а не доказанными отказами. h03 проходит activation threshold >=100 updates, >=3 групп, >=10 detections. h06 имеет ограниченный охват (2 группы, 8 detections); эффективность по покрытию недостаточна. Но его отклонение обосновано реально наблюдавшейся неверной атрибуцией, не одной неактивностью.

На original suite h03 имеет всего3 weighted updates и ни одного изменения reference метрик; h06 —0. Основная активация происходит в специальной suite. Нельзя выдать её за покрытие естественных слабых отказов или за original-suite gain.

### Контрпример

`30618_073f08d1-diagnostic-2`: **rear negative drift [127.6,135.6) s**, от0 до-0.4 m/s за4s. h03 понижает **front** 23 раза (133.365782164..135.515782164s); h06 —20 раз (133.615782164..135.515782164s). Правильного воздействия на injected channel в этом case нет. «Wrong channel» означает неинъецированный канал; независимых labels естественной исправности front нет.

Rover event RMSE: 0.213941009369 -> **0.264702977688 m/s** для h03 (+0.050761968319; **+23.7271%**), h06 0.258124337078 (+20.6521%). h03 p95 окна fault+10s: 0.267457785596 ->0.365347071513 (**+36.5999%**). В первый h03 downweight tick C_front+=0.355408728s, q_front=.25, q_rear=1, d=.6m/s²; output v baseline2.62837 vs h032.56797m/s. Накопитель фиксирует устойчивое расхождение, но близость колеса к уже смещённой модели не гарантирует правильную атрибуцию. Это интерпретация сохранённой трассы, не универсальное доказательство причинности.

В [decision.json](https://github.com/jabrailkhalil/hack/blob/09ac6c90c80b03adf44818608bf88771a060f11d/reports/research_R2/H19/36184813159-1/development/decision.json) перечислены все10 h03 и6 h06 wrong-channel cases. Обновления и два receivers не считаются независимыми поездками.

Special event-macro RMSE: baseline0.142685336670 -> h030.142854661989 / h060.142850266701 (**+0.118670% / +0.115590%**). Drift отдельно: 0.178381640130 ->0.178752394576 /0.178912924569; intermittent отдельно: 0.106989033209 ->0.106956929402 /0.106787608833. Малый intermittent gain не отменяет провал основного контракта и wrong-channel safety.

Conditional median detection delay среди обнаруженных случаев: h033.220133437s, h064.615782164s. Остальные99/104 cases не считаются нулевой задержкой. Все120 diagnostic recovery_s совпали, включая8 None. Mean case-wise disturbance contamination proxy (RMSE d относительно clean twin того же алгоритма): drift0.03246657 ->0.03273798 /0.03259204m/s²; intermittent0.09566090 ->0.09419002 /0.09530698. Это описательная негрупповая диагностика, не true disturbance и не admission.

## Выполненные проверки и воспроизводимость

144 штатных теста,43 research-integrity,27 H19 unit/integration tests — PASS локально и в Actions; compileall PASS. Сохранены исторические release-hash проверки. Изолированные tests покрывают disabled/monitor equivalence, causal prefix, duplicate/held/future/stale, reset, bounded size/4s epoch, stop/zero-lock, weighted fusion, adaptation freeze. Дополнительный post-measurement guard audit без изменения алгоритма реально вошёл в REACQUIRING:43 такта, первый0.8s, h03/h06/off полностью совпали с v7.

**Все64 train bags**, первые<=180s:406293 vehicle events,208014 outputs на алгоритм,212494 baseline/pristine/off checked ticks. Train GNSS не читался, fitting отсутствует. Это execution/invariance, не accuracy evidence.

На development+original **359956 тактов** точного совпадения Estimate и всех baseline state полей с независимо загруженным pristine R2 и H19-off. Канонический baseline исполнялся реально, не копировался из исторических таблиц.

Local export vs remote SQLite: **24048 числовых полей, max delta0.0; 597 массивов /34101300 элементов совпали точно**.18 code/patch/evaluator/profile/split файлов и patched core hash совпали. Локальный source_commit label c052... — начальный checkout плюс рабочие исследовательские файлы, не подмена measured remote SHA; хэши связывают код с6f6b447d.... Документы PLAN/SOURCES и полный source manifests не объявляются побайтно одинаковыми. [Паритет](PARITY.json).

Python3.13.5, NumPy2.3.5, SciPy1.17.0. Organizer ZIP SHA256 d0b2483e13990edb8219b0d7bbcafc7ed001cce549a4d3af467069b2472e7d52 и каждый использованный bag проверены. Artifact10886002746:55263228bytes,SHA2564d0b708a361aee8790a4b1847fff1b9f27ad8b56fd7e68f4e66041fa8eb1b845. Журналы и source association сохранены в checkpoint.

## Стоимость и непроведённые этапы

Первый development bag30618_0652866c,<=180s,threads1,три AB/BA пары для каждого порога. Enabled detector работает, но на этом коротком отрезке downweight нет: обычный путь, не worst-case fault. Step CPU после первых10s того же потока; replayCPU/wall полный180s после отдельного cache warmup10s, одинаковый сбор outputs.

| Медиана, microseconds/output | baseline для h03 | h03 | baseline для h06 | h06 |
|---|---:|---:|---:|---:|
| Step CPU |25.473005|31.811589|25.706326|32.071421|
| Replay CPU |37.938638|45.014093|38.078496|44.993727|
| Replay wall |37.942519|45.025861|38.098638|44.995478|

Peak RSS124530688bytes относится ко всему benchmark process, не ROS-node RSS. Это НЕ installed ROS latency/p95/p99, не hard-real-time гарантия. **Enabled H19 ROS offline replay под2CPU/500000000bytes и оба clock modes не выполнялся**, поскольку accuracy уже REJECTED; это допускает протокол. Штатный/default ROS CI и исторические v4/v5/v7 измерения не сертифицируют включённый H19.

**Validation не запускался, разрешающий FREEZE не создавался, выбранного кандидата нет. Final/test measurement payloads не открывались.** Dataset unpack не даёт разрешения test SQLite IO; access journals содержат только train/development. Сравнение с текущим движущимся main не проводилось.

## Наука и ограничения

[Источники и фактический доступ](../../../../research/R2/H19/SOURCES.md): Consensus abstract/metadata Murguia & Ruths2019 DOI10.1049/iet-cta.2018.5970; Wiley metadata Guedaouria et al.2025 DOI10.1002/acs.3986. Scite реально вызван, но вернул месячный25-call quota, reset01.10.2026. OA excerpts/fulltext/citation contexts Scite в этой работе НЕ прочитаны. Publisher fulltext также недоступен. Платных действий не было.

Wolfram реально проверил bounded C, pole в(0,1), limit stationary C=tau*(e-k), отсутствие начисления приdt0 и rank2/nullspace(-1,1,1) для двух wheel observations относительно(v,b_front,b_rear). Общий bias без допущений неидентифицируем. Numeric dt.1,tau2,e1,k.25: detection за5/10 updates дляH.3/.6; decay изcap доrelease за30/27. Это идеальный случай внутри4s epoch, не гарантия точности, калибровки false alarms или замкнутой устойчивости.

Первый Wolfram запрос содержал warnings и ошибочную индексацию FirstPosition; неправильные numeric2/2,1/1 сохранены как DISCARDED. Второй запрос с явными индексами исполнен корректно, Python cross-check подтвердил5/10,30/27. Worksheet и реальные ответы сохранены в research/R2/H19 и checkpoint/source. Не переносились PFEKF/particle-filter реализация и чужие sensor интерфейсы.

Нет независимой natural-fault/true-stop разметки и independent final test. Соседние residual/инъекции/receivers зависимы; significance не заявляется, ticks не бутстрепировались как независимые испытания. Scalar-span distance — переякоренный GNSS-speed integral surrogate, не xyz/ENU и не полный terminal drift.

## Воспроизведение и включение

```bash
git fetch origin
git switch --detach 6f6b447d7d17de6ad39f896e9d22dee844eacc76
python3.13 -m venv .venv-h19
. .venv-h19/bin/activate
python -m pip install -r requirements-research.txt
python tools/get_dataset.py
sha256sum -c research/R2/H19/MEASURED_CODE.sha256
PYTHONPATH=src/reserve_odometry python -m unittest discover -s tests -v
python -m unittest discover -s research/tests -v
python -m unittest discover -s research/R2/H19 -p 'test_*.py' -v
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
python tools/research_h19/run.py --stage train --output /tmp/h19-train-new
python tools/research_h19/run.py --stage development --output /tmp/h19-dev-new
python tools/research_h19/run.py --stage benchmark --output /tmp/h19-cost-new
```

Output directories должны быть новыми. **Checkout сам по себе H19 в canonical ROS launch не включает.** Driver автоматически применяет research/R2/H19/core.patch к temporary pristine copy и создаёт SequentialFaultObserver. Не применять core.patch заранее в том же checkout: fixed-source guard должен отказать. Factory.make('off') — ablation, make('h03')/make('h06') — два измеренных порога. Отдельный ROS adapter для отвергнутого кандидата не добавлялся. Validation CLI в этой версии заблокирован до IO.

## Вывод

**h03 REJECTED:** достаточная активация по плану, нет требуемого original gain и нарушена wrong-channel safety. **h06 REJECTED:** наблюдавшаяся ошибочная атрибуция и отсутствие gain; эффективность дополнительно ограничена недостаточным coverage. Не обобщаем отказ на все sequential methods. Draft PR сохраняет воспроизводимый отрицательный результат, не готов к merge.
