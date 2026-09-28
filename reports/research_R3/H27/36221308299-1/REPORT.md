# R3-H27: committed disturbance — REJECTED на development

**Исследовательский артефакт, не готов к merge.** Проверенный lag 0.4 s имеет достаточное заранее заданное покрытие, но не проходит prospective development contract: original fault RMSE улучшился на **2.830891% вместо требуемых 5%**, clean gain только **0.000028287%**, и нарушены четыре counterexample veto. Validation не открывался. Lag 0.2 s отдельно имеет **INCONCLUSIVE по покрытию original-задачи**: всего 14 effective ticks; его диагностические регрессии при этом также сохранены.

| Поле | Фактическое значение |
|---|---|
| mechanism_status | ACTIVE |
| coverage_status | SUFFICIENT для lag 0.4; INSUFFICIENT для lag 0.2 |
| scientific_verdict | REJECTED для покрытого варианта 0.4 и проверенного бюджета исследования |
| accuracy_contract_passed | false |
| runtime_verified | false — enabled installed ROS не выполнялся |
| ready_to_merge | false |
| validation / final test | NOT_RUN / NOT_OPENED; метрики N/A |

Это отрицательный вывод о конкретной реализации и зарегистрированном бюджете, не доказательство бесполезности любой истории disturbance. Наличие отдельных улучшений не меняет контракт. Merge, auto-merge и force-push не выполнялись.

## 1. Идентичность и неизменяемые источники

| Назначение | Commit SHA |
|---|---|
| Общий R3-v8-fixed baseline | `e3b0c9c039d2953fbfcda51231263d38ef9f1024` |
| Foundation protocol до измерений | `2c273b04fdcb0d9800289beeddf411a1b21233d3` |
| Измеренный foundation source | `9a36b9c216fc9be5783079ba50b4c6f483dd1ff6` |
| Train threshold, опубликованный до development IO | `70e17cd736175752ad27858401f999116d86a5b5` |
| Полный PLAN до сравнения кандидатов | `310a883cabbe6ce6c8d88a738437e53d9664bcaf` |
| **Измеренный candidate / development / CPU** | **`e998c7df8e9ce13f284e3c2cbe935c70c0f76c11`** |
| Foundation checkpoint | `464ed0b779cd4059bbdade279a99edd2dcafdc34` |
| Development checkpoint | `0693c29daeede2a642d3fe4cac70d669fb52dd5c` |
| Validation FREEZE | **N/A: development admission не пройден** |

Ветка `research/R3-H27`; один [draft PR #39](https://github.com/jabrailkhalil/hack/pull/39). До создания выполнен поиск точного scientific ID по PR и веткам, дубликат не найден. Ветка создана от указанного baseline. Движущийся main не включён. После получения accuracy-результатов candidate/threshold/PLAN/evaluator не изменялись; этот отчёт и аудит добавлены отдельно позднее. SHA публикации отчёта приведён в PR, не подменяет measured candidate SHA.

Baseline — настоящий `GuardedReadoutObserver` с полным `champion_v8.yaml`, не `Observer(Config())`, не v5/v7. Readout gain=1, holdoff=0.5 s; adaptation_tau=0.5 s, wheel_time_compensation=0, common_mode_quarantine_s=1.5 s; output 20 Hz, alignment 0. Сравниваются возвращаемые `Estimate.v/s`. Все физические параметры взяты из профиля. Проверены 18 baseline source/profile/evaluator/split pins относительно Git object. Core, guarded_readout, Timeline, node, launch, штатные профили, scaler, matching и старые release guards не менялись.

## 2. Основание и что именно реализовано

Прочитаны PR #20, который является scientific H03, точные отчёты R2-H13 (`91b7d9a...`, source `f53ae2b...`) и R2-H15 (`2f959a41...`, source `5b9ab842...`). H03 менял healthy derivative, H13 — interval target, H15 — drive-dependent d при loss. Их отрицательные результаты показывают риск старого/сглаженного d, но не доказывают физическое загрязнение конкретного d в новых данных.

Добавлены только два runtime-модуля: `committed_history.py` и `committed_disturbance.py`. Последний определяет явный opt-in `CommittedDisturbanceObserver`. Обычный executable `guarded_odometry_node` остаётся canonical v8. Checkout сам по себе H27 в ROS не включает.

В здоровом режиме сохраняется история уже доступных legacy d, максимум 16 snapshots и 1 s. Записывается время доступности update, а не задним числом wheel stamp. Нужен фактически выполненный допустимый FUSED derivative update: две новые принятые скорости, native dt в [0.05,max_age], |a_wheel|<=max_accel, |v|>0.5; дополнительно wheel age<=0.20 s, skew<=0.05 s, разность скоростей<=0.15 m/s. Command mode определяется существующим deadband; invalid/mode change очищает доверенную историю. Код History побайтно совпадает с foundation monitor.

Обычные MODEL_ONLY ticks с двумя `DUPLICATE_OR_OLD` не открывают outage. Loss обнаруживается после canonical step по MODEL_ONLY и хотя бы одному иному статусу; duplicate-only ticks продолжают уже открытый loss. При входе проверяется медиана d в 0.2 s-окне, заканчивающемся на lag 0.2 или 0.4 s раньше последнего trusted update. Требуются >=3 точки, span>=0.1 s, последний update не старше 0.35 s, MAD<=threshold/2 и отличие текущего d от медианы>threshold. Смена режима либо недостаток истории дают native fallback.

При допуске checkpoint фиксируется, но **не записывается в native disturbance**. Отдельная выходная поправка в model-only вычисляется так:

```text
g = updated_native_drive_a - resistance(old_native_v)
delta_a = clip(g + checkpoint_d) - clip(g + old_native_d)
delta_v += dt * delta_a
```

Оба clip используют существующий max_accel. Это изолированная аддитивная поправка первого порядка, не второй нелинейный физический observer. Начальный текущий интервал корректируется только после получения его причинного evidence; будущий onset, fault type/duration, reference и bag ID observer не получает.

На FUSED/SINGLE_WHEEL recovery delta_v уменьшается множителем (1-K) из native scalar update; на REACQUIRING уменьшается к нулю существующим ограниченным шагом с фактическим pair dt. На STOPPED velocity correction обнуляется. При смене/потере команды отменяется дальнейшее применение checkpoint d, но уже накопленная delta_v сохраняется до recovery. Readout ограничивает скорость и не создаёт дополнительный переход через ноль.

```text
delta_s += 0.5 * (old_delta_v + new_delta_v) * dt
published_v = native_Estimate.v + delta_v
published_s = native_Estimate.s + delta_s
published_a = native_Estimate.a + (new_delta_v-old_delta_v)/dt
```

**Delta_s никогда не сбрасывается при recovery, остановке или смене команды.** Только явный reset начинает её заново. Все native поля, включая healthy adaptation, низкоскоростной zero-lock и common-mode quarantine, остаются идентичны отдельному canonical объекту. `last_estimate` — выход, его native counterpart сохраняется отдельно. После outage опубликованная s может сохранять offset при уже нулевой velocity correction: это ожидаемое следствие интегрирования, не переякоривание к reference.

Runtime — stdlib, только controller/front/rear; нет новых сенсоров или тяжёлых зависимостей. История ограничена, фактический максимум 11 записей. Дополнительные variance envelopes — консервативная диагностика, не калиброванные доверительные интервалы и не доказательство устойчивости.

## 3. Train scale и foundation до accuracy

На всех 64 train-bag выполнен canonical replay только vehicle topics. 27 исходных групп заранее отсортированы и разделены через одну: 14 fitting / 13 check; 11 fitting-групп дали >=100 residual increments. Собрано 425795 приращений d: **176808 fitting**, **248987 check**. Check не участвовал в настройке.

Заранее опубликованное правило:

```text
sigma_group = 1.4826 * MAD(trusted legacy d increments)
theta = max(0.02, 3 * median(sigma_group over eligible fitting groups))
```

Результат **theta=0.0823180344240239 m/s²**. SCALE SHA256 `fd6cc4152626c6b71f1c34d8d9a429d4f2df0fd816fe252937690bd3fb437847`. Это residual scale приращений уже фильтрованного wheel-derived d, не ошибка относительно истинного возмущения. Значение опубликовано отдельным commit до development foundation.

Foundation использовал все 17 development-bag, только vehicle даже на этом этапе, natural + 56 original faults. Canonical Estimate и все native поля сверялись на каждом tick. Порог покрытия до IO: >=10 qualifying entry episodes, >=3 исходных групп, >=100 потенциальных model-only ticks.

| Lag | Qualifying entries | Natural / original | Группы | Потенциальные ticks | Foundation |
|---|---:|---:|---:|---:|---|
| 0.2 s | 14 | 14 / 0 | 4 | 14 | insufficient ticks |
| 0.4 s | 15 | 12 / 3 | 3 | 164 | passed |

У 0.4 s **153 ticks сосредоточены в одной группе**. Другая группа с 10 ticks не имеет reference; третья даёт 1 tick. Это ограниченная репрезентативность, не 15 независимых длительных outages. Foundation считает предлагаемые замены, не полезность вмешательства. После него опубликован полный PLAN, и только затем реализованы/сравнены два заданных lag. Бюджет и threshold не расширялись.

## 4. Один неизменный measuring path

Два кандидата и off реально исполнены на всех 17 development-bag. 7 исходных групп, clean reference в 6 группах / 19 bag-receiver парах; 7 bag вообще без reference сохранены как missing. Original faults: 56 сценариев, 60 reference comparisons в 5 группах. Ни пары receivers одного bag, ни соседние ticks не считаются независимыми поездками.

Driver подставляет только Observer factory в неизменный `evaluate.score/replay`. Внутренние legacy aliases явно переименованы в полный v8; прежний v5 не используется. Формулы matching, masks, distance, original anchor/fault windows и v6 group aggregation сохранены. Дополнительный independent v8 control и H27 off совпадают с baseline по массивам/метрикам/счётчикам. На каждом tick сравниваются все native поля включённого H27 с independent canonical v8; опубликованный last_estimate сравнивается через native counterpart.

**73 natural/original полных replay baseline точно воспроизвели SHA256 выходных массивов и runtime counters предыдущего foundation.** Это не копирование прежних агрегатов. Schedule всех кандидатов проверен; n/coverage совпадают, causal/reset errors нулевые. Аудит 950 файлов артефакта подтвердил их SHA256.

Data loader допускает только train/development, проверяет роль и checksum до read-only SQLite. Train GNSS закрыт. Organizer ZIP скачан и проверен целиком; из вложенного архива индивидуально извлечены только 64 train + 17 development DB. Validation/test DB не распаковывались и не открывались. Offline development reference не передаётся observer.

## 5. Основные development-метрики

Отрицательная процентная дельта ошибки означает улучшение. R3 требует >=2% clean gain ИЛИ >=5% original fault gain; clean/fault/pooled regression<=0.5%, scalar distance<=1%, clean bag/receiver<=baseline+max(0.005 m/s,5%). Дополнительно требуются actual coverage и все safety/counterexample veto. Эти пороги зафиксированы до сравнения, не менялись после чисел.

| Метрика | Full v8 / off | Lag 0.2 | Lag 0.4 |
|---|---:|---:|---:|
| Clean group-macro RMSE, m/s | 0.092668142983 | 0.092668160640 | 0.092668116770 |
| Изменение clean RMSE | — | +0.000019055% | -0.000028287% |
| Original fault-event macro RMSE, m/s | 0.237548612056 | 0.237548612056 | 0.230823868906 |
| Изменение original fault RMSE | — | 0% | **-2.830891%** |
| Pooled clean RMSE, m/s | 0.129305694477 | 0.129305704061 | 0.129305682388 |
| Изменение pooled RMSE | — | +0.000007411% | -0.000009349% |
| Scalar-span distance RMSE, m | 5.310295004801 | 5.310291964266 | 5.310307498121 |
| Изменение distance RMSE | — | -0.000057257% | +0.000235266% |
| Matched clean samples | 394221 | 394221 | 394221 |
| False stops clean / original | 0 / 0 | 0 / 0 | 0 / 0 |
| Original cases без recovery | 4 | 4 | 4 |
| Actual qualifying entries / ticks | — | 14 / 14 | 15 / 164 |
| Итог варианта | baseline | INCONCLUSIVE coverage; diagnostic failures | **REJECTED** |

Малые clean-дельты не объявляются практически/статистически значимым улучшением. Основные regression/per-bag guards пройдены, но gain недостаточен. У 0.4 фактическое покрытие совпало с foundation: 12 natural ticks + 152 original ticks, 3 группы. У 0.2 недостаточное original-покрытие не маскируется большей активацией в дополнительных suites.

Дополнительный описательный group-macro аудит, не новые критерии выбора:

| Метрика | v8 | Lag 0.2 | Lag 0.4 |
|---|---:|---:|---:|
| Clean MAE, m/s | 0.034933352905 | 0.034933353401 | 0.034933334059 |
| Clean signed bias, m/s | 0.006390677420 | 0.006390805877 | 0.006390735227 |
| Clean p95, m/s | 0.090092790092 | 0.090092790092 | 0.090092790092 |
| Original fault+10s MAE, m/s | 0.153796529331 | 0.153796529331 | 0.151741366331 |
| Original fault+10s signed bias, m/s | 0.011170307852 | 0.011170307852 | 0.017303775175 |
| Original fault+10s p95, m/s | 0.456670428618 | 0.456670428618 | 0.449876503650 |
| Group-macro подтверждённый recovery, s | 0.724358284875 | 0.724358284875 | 0.718108284875 |

Recovery macro включает только подтверждённые случаи и 4 группы; четыре unrecovered не заменяются нулями. Все они относятся к четырём original faults `30639_e4379d7f/rover`, как у baseline. У 0.4 в original lock `30639_dce52be4` recovery лучше на 0.2 s у обоих receivers, остальные original recovery неизменны. В low-speed suite у `30639_9c362687` recovery хуже на 0.15 s для lock3 и 0.25 s для lock5; новых unrecovered нет.

### Все clean bag

Здесь для компактности среднее RMSE доступных receivers одного bag, **не замена group-macro aggregation**. Полные receiver-метрики находятся в исходных bags JSON и экспортируемом CSV.

| Bag | v8, m/s | Lag 0.2 | Lag 0.4 |
|---|---:|---:|---:|
| 30618_0652866c | 0.036107025889 | 0.036107025889 | 0.036107025889 |
| 30618_073f08d1 | 0.033935203813 | 0.033935045972 | 0.033935203813 |
| 30618_117c2d02 | missing | missing | missing |
| 30618_1551d0a9 | 0.003988359652 | 0.003988359652 | 0.003988359652 |
| 30618_27e994fc | 0.161364401745 | 0.161364401745 | 0.161364401745 |
| 30618_3e012faf | missing | missing | missing |
| 30618_46e21b9b | missing | missing | missing |
| 30618_5036aa78 | missing | missing | missing |
| 30618_74559c73 | missing | missing | missing |
| 30618_88548b02 | 0.050600852667 | 0.050600978133 | 0.050600314471 |
| 30618_bcc9e7a2 | missing | missing | missing |
| 30618_e151d6e4 | missing | missing | missing |
| 30639_0ab96c59 | 0.019185027740 | 0.019185027740 | 0.019185027740 |
| 30639_9c362687 | 0.120351633512 | 0.120351633512 | 0.120351633512 |
| 30639_c31df386 | 0.063707555446 | 0.063707794693 | 0.063707779090 |
| 30639_dce52be4 | 0.231633603805 | 0.231633556210 | 0.231633603805 |
| 30639_e4379d7f | 0.138142126696 | 0.138142126696 | 0.138142126696 |

## 6. Контрпримеры и крупные локальные регрессии

Все семейства зарегистрированы до accuracy. Их gain не подменяет original admission; каждое имеет veto на event macro regression>0.5%, новые false stops/individual unrecovered/causality. Anchors реальных инъекций выбираются только по vehicle data, не по reference ошибке.

| Семейство | Сценариев / reference comparisons | v8 event RMSE | Lag 0.2, изменение | Lag 0.4, изменение |
|---|---:|---:|---:|---:|
| Existing low-speed lock3/5 | 26 / 34 | 0.368545673 | -0.214642% | **+21.258207%** |
| Existing abrupt common +5, 0.7/1.2s | 28 / 30 | 0.100632272 | 0% | **+3.943123%** |
| Dropout после смены команды | 38 / 45 | 0.214224494 | **+7.823092%** | 0% |
| Common slow drift до dropout | 28 / 30 | 0.684294658 | -1.214365% | -0.271610% |
| Synthetic genuine load change | 2 / 2 | 0.250275880 | 0% | **+154.087291%** |
| Synthetic late correct update | 2 / 2 | 0.444864228 | **+75.585609%** | **+92.298687%** |

В synthetic plant истинная нагрузка меняется на +/-0.3 m/s² в t=30 s, а dropout начинается через 0.7 s либо 0.4 s и длится 5 s. Эти четыре детерминированные проверки показывают риск отказа от свежего правильного d в конкретной идеальной модели. Они не являются реальными записями или доказательством причин реальных ошибок. Physical d в real bags не наблюдается.

False stops во всех diagnostics остались 0. Число unrecovered также без роста: low_speed 6, common_mode 2, transition 3, slow_drift 2, synthetic 0. Наличие этих baseline-проблем не разрешает рост RMSE. У 0.4 mandatory v8 low-speed/common-mode veto нарушены, хотя внутренние guards побитово сохранены: выходная поправка сама может ухудшать качество защищённого режима.

| Случай / метрика | Baseline -> candidate, m/s | Изменение |
|---|---|---:|
| 0.4, 30639_dce52be4/master, original dropout10 event RMSE | 0.227959065 -> 0.289802978 | **+27.129394%** |
| 0.4, тот же bag/rover, dropout10 | 0.234228605 -> 0.289478593 | +23.588062% |
| 0.4, 30639_9c362687/master, low-speed lock5 | 0.160237113 -> 0.549833525 | **+243.137438%** |
| 0.4, тот же bag/rover, lock5 | 0.153562247 -> 0.542949639 | +253.569742% |
| 0.4, 30639_dce52be4/rover, common jump0.7s | 0.098276729 -> 0.138940719 | +41.377029% |
| 0.2, 30639_e4379d7f/rover, transition dropout | 0.251580860 -> 0.502965558 | **+99.922028%** |
| 0.2, 30618_073f08d1/rover, low-speed lock3 | 0.059203206 -> 0.155720619 | +163.027342% |

Несмотря на улучшение low_speed aggregate у 0.2, его последняя локальная регрессия существенна и не скрыта. На clean обе версии слегка ухудшают `30639_c31df386` у обоих receivers: у 0.4 rover RMSE +0.000000231 m/s, distance +0.000272 m, далеко в пределах основных limits. Все положительные локальные RMSE/MAE/p95/|bias|/distance/recovery дельты экспортируются `audit.py` в regressions.csv.

Выигрыш original aggregate 0.4 сосредоточен в `30639_dce52be4`: dropout5/master 0.264680028 -> 0.077768201 m/s и lock3/master 0.226136060 -> 0.085662616 m/s. Но dropout10 в том же bag ухудшился, как показано выше. Это не устойчивое превосходство по продолжительности отказа.

## 7. Before / during / after: интерпретация сохранённой трассы

Original dropout `30639_dce52be4` [114.9,124.9) s, lag0.4. Скорости ниже — опубликованные Estimate, а d — native; checkpoint не подменяет native d.

| t, s | Native d | Checkpoint | v8 v | H27 v | delta_v | delta_s, m | Mode |
|---|---:|---:|---:|---:|---:|---:|---|
| 115.014844 | -0.066281 | — | 4.283206 | 4.283206 | 0 | 0 | MODEL_ONLY, duplicate held |
| 115.064844 | -0.066281 | 0.052005 | 4.288471 | 4.294385 | 0.005914 | 0.000148 | MODEL_ONLY, stale wheels |
| 117.514844 | -0.066281 | 0.052005 | 5.605860 | 5.901576 | 0.295716 | 0.369645 | MODEL_ONLY |
| 117.564844 | -0.066281 | отменён | 5.614876 | 5.910592 | 0.295716 | 0.384430 | MODEL_ONLY, команда в нейтрали |
| 124.914844 | -0.066281 | — | 2.498280 | 2.793995 | 0.295716 | 2.557940 | MODEL_ONLY |
| 124.964844 | -0.066281 | — | 2.131380 | 2.134754 | 0.003374 | 2.565417 | FUSED |
| 134.914844 | 0.002574 | — | 0.583801 | 0.583801 | 0 | 2.565931 | MODEL_ONLY, duplicate held |

Onset определяется фактической свежестью в Timeline, поэтому он позже offline injection start. После смены mode в 117.564844 дальнейшая acceleration correction прекращается, но delta_v сохраняется до recovery согласно PLAN. Интеграл расстояния не сбрасывается: в конце окна остаётся +2.565931 m относительно canonical s. Это offset между алгоритмами в диагностическом окне, не новый GNSS distance score.

В synthetic genuine_load_positive native d на entry уже 0.217864, checkpoint всего 0.076746; к t=35.7 s delta_v=-0.684422 m/s, после восстановления накопленный delta_s остаётся около -1.679449 m. В этой заданной модели старая поправка действительно отбрасывает реальную свежую динамику. Для реального bag такая причинная интерпретация остаётся ограниченной: независимого ускорения/true d нет. Повторной настройки по этим трассам не было.

Полные gzip traces содержат каждый tick до/во время/после всех original и diagnostic инъекций. Схема строки: t, current_u, front, rear, old_d, native_d, drive_a, native_inner_v, native_published_v, candidate_published_v, native_published_s, candidate_published_s, checkpoint_d, delta_v, delta_s, delta_a, mode, front_status, rear_status. В Git крупные traces не коммитились.

## 8. Проверки и цена

[Foundation run 36220511208](https://github.com/jabrailkhalil/hack/actions/runs/36220511208), [development/cost run 36221308299](https://github.com/jabrailkhalil/hack/actions/runs/36221308299), attempt1: все шаги success. Это успех исполнения исследования, не принятие accuracy-кандидата.

| Проверка | Фактически выполнено |
|---|---|
| Foundation monitor tests | 18 PASS |
| Candidate tests | 21 PASS; вместе с foundation 39 PASS в development job |
| Неизменный полный unit suite | 156 PASS в обоих research jobs |
| Research integrity | 43 PASS в обоих research jobs |
| Compileall / source SHA verification | PASS |
| Off/native state/prefix/future/duplicate/stale/reset/bounds/recovery/integral | специальные тесты PASS; native state/off дополнительно проверены на каждом real/synthetic tick |
| Baseline replay reproduction | 73 полных natural/original replay, exact hashes/counters |
| Artifact audit | 950 SHA256 проверены; 193 real score rows + 4 synthetic |

Subset/повторные прогоны не суммируются как независимые уникальные тесты. Локально те же 18 и 21 тест также PASS. Read-only audit первоначально встретил отсутствующий ключ MAE у записи без reference; исправлен только экспорт через missing/None, исходный scorer и decision не менялись. Отсутствующая метрика не превращена в 0.

[Обычный CI 36221311353](https://github.com/jabrailkhalil/hack/actions/runs/36221311353): четыре jobs success, включая ROS/offline2CPU/500MB. Этот установленный launch остаётся **canonical v8, не enabled H27**. Он не сертифицирует новый runtime.

CPU: один и тот же original replay collector без проверки двойного observer/trace, threads1; 10 s warmup исключены. Два заранее выбранных workload: первые120s `30618_0652866c` (2200 post-warmup steps) и первый по foundation activation original dropout5 `30639_dce52be4` (502 steps). Для каждого lag и workload 3 AB + 3 BA пары: 6 baseline + 6 candidate, всего 48 replay. Хеши outputs стабильны во всех повторах.

| Workload / lag | Effective ticks | Step CPU A -> B, s | Медиана парной дельты | Replay CPU A -> B, s | Парная дельта |
|---|---:|---|---:|---|---:|
| Prefix120 / 0.2 | 0 | 0.046055155 -> 0.054170445 | +17.366171% | 0.069208085 -> 0.077747609 | +12.121795% |
| Prefix120 / 0.4 | 0 | 0.046170333 -> 0.054287969 | +17.685148% | 0.069515222 -> 0.077939439 | +12.199565% |
| Active original / 0.2 | 0 | 0.010233529 -> 0.012549775 | +22.388095% | 0.015650256 -> 0.018097244 | +15.745680% |
| Active original / 0.4 | 50 | 0.010200658 -> 0.013938699 | **+36.635263%** | 0.015623085 -> 0.019541239 | **+24.915246%** |

Дельты — медиана парных отношений, не отношение двух отдельных медиан. Для 0.4 prefix step CPU range +10.382313…+47.498743%, replay +5.001992…+40.592526%: разброс не скрыт. Для активного workload step +32.840114…+38.760673%, replay +21.462320…+26.622326%. Wall timers сохранены отдельно; у активного0.4 медианные дельты step wall +36.673712%, replay wall +24.912875%.

Это instrumented offline CPU/wall, не end-to-end node latency, не RSS ноды и не hard real-time гарантия. Process/node RSS здесь не измерялся. **Enabled installed ROS replay в обоих clocks, offline2CPU/500000000bytes, GetParameters/import hashes и latency/RSS: NOT_RUN_AFTER_REJECTION.** Существующие v8 показатели H27 не присвоены.

## 9. Evidence, воспроизведение и ограничения

[Foundation compact checkpoint](https://github.com/jabrailkhalil/hack/tree/464ed0b779cd4059bbdade279a99edd2dcafdc34/reports/research_R3/H27/36220511208-1).

[Development raw per-bag scores, original SUMMARY, costs, logs и hashes](https://github.com/jabrailkhalil/hack/tree/0693c29daeede2a642d3fe4cac70d669fb52dd5c/reports/research_R3/H27/36221308299-1). В поддиректории development/bags каждый JSON содержит все suites/receivers/варианты данного bag; synthetic counterexamples отдельно. Крупные traces — только в сжатых Actions artifacts.

| Artifact | ID | SHA256 ZIP | Retention |
|---|---:|---|---|
| R3-H27-foundation-36220511208-1 | 10898314719 | `5be45ca4f01ed589320d1475f66b9532230bf70d504ca60fb1e536bbce18335e` | до 2026-10-26 05:24:26 UTC |
| R3-H27-development-36221308299-1 | 10898757901 | `f7c37a7d71ecd0dca2bdaea76091a7708dce945ebf5b54fd3508d59498321e0d` | до 2026-10-26 05:39:55 UTC |

Runtime patch SHA256 `52818bb3b4954cf4a1bd5c0248da874ceaa1d8087830c948b870361bf27762b6`; module committed_disturbance SHA256 `b75250635a051e5f5c2782671d8512efd14d1120a0ba2d431e4286415eae01c3`. Artifact/source manifests сохраняют остальные pins. Компактные checkpoints не зависят от retention больших traces.

Воспроизведение уже фиксированного development в отдельной рабочей копии полного репозитория:

```bash
git fetch origin research/R3-H27 \
  checkpoint/R3-H27-foundation-36220511208-1 \
  checkpoint/R3-H27-development-36221308299-1
git worktree add --detach ../hack-R3-H27 \
  e998c7df8e9ce13f284e3c2cbe935c70c0f76c11
cd ../hack-R3-H27
python3.13 -m venv .venv-h27
source .venv-h27/bin/activate
python -m pip install -r requirements-research.txt
export PYTHONPATH=src/reserve_odometry
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
python -m compileall -q src research/R3/H27
python -m unittest discover -s research/R3/H27/tests -v
python -m unittest discover -s tests -v
python -m unittest discover -s research/tests -v
python research/R3/H27/prepare.py
python research/R3/H27/development.py --output /tmp/H27-dev-new --workers 2
python research/R3/H27/cost.py --output /tmp/H27-cost-new
```

Checkout уже содержит модуль; повторный git apply не нужен. Candidate factory использует `CommittedDisturbanceObserver(config, readout=readout, lag_s=0.4, threshold=0.0823180344240239)` с config/readout из exact v8 profile. CLI не имеет validation/test stage. Output paths должны быть новыми. Python3.13.5, NumPy2.3.5, SciPy1.17.0 нужны только offline.

Для точного foundation отдельно checkout `9a36b9c216fc9be5783079ba50b4c6f483dd1ff6`, та же подготовка данных, затем `probe.py --stage fit --output /tmp/H27-fit-new --workers 2` и `probe.py --stage probe --scale /tmp/H27-fit-new/SCALE.json --output /tmp/H27-probe-new --workers 2`. Не запускать foundation reproduction из позднего дерева с иным набором research-файлов: его provenance guard намеренно обнаружит изменение. Исторический scale commit уже показывает freeze значения до первоначального development IO.

`audit.py` рядом с отчётом читает распакованный development artifact и экспортирует per_bag_receiver.csv, per_group.csv, activation.csv, diagnostic_macro.csv, regressions.csv и таблицы missingness. Он не делает replay, не подбирает параметры и не меняет decision. Исходные JSON не дублируются в Git большими CSV; экспорт включён в локальный пакет результата.

## 10. Научный объём проверки

Сохранены `research/R3/H27/oracle.py`, настоящий `oracle-output.json`, assumptions и warnings. Локальный независимый SymPy oracle подтвердил для одинаковых начальных состояний и постоянного unclipped acceleration error: delta_v=delta_d*T и delta_s=0.5*delta_d*T², нулевые пределы и дискретную трапецию. Пример acceleration clipping: g=2.9 и delta_d=0.3 дают delta_a=0.1, а не0.3. Формулы не переносятся без оговорок на нелинейный переключаемый runtime; устойчивость полного observer не доказана.

Новые Consensus/Scite запросы не выполнялись: известные monthly quota stops из задания соблюдены. Прочитаны metadata и полный abstract первичной институциональной карточки Sariyildiz et al.2021, IEEE Access9,148911–148924, DOI10.1109/ACCESS.2021.3123365; полный текст и citation contexts в этом цикле не проверены. Её force-control схема с иными измерениями не перенесена в H27. Источник: https://keio.elsevierpure.com/en/publications/discrete-time-analysis-and-synthesis-of-disturbance-observer-base/ . Список прочитанных prior reports и scope есть в SOURCES.md.

Локальная попытка загрузки organizer dataset встретила DNS-ошибку; все перечисленные реальные прогоны успешно выполнены в Actions. Validation/final-test не запускались, их метрики не приписаны кандидату. Повторно использованные исторические данные не становятся независимыми из-за нового freeze. Scale1/3.6, fixed physical gauge, ambiguity common-mode колёс и скалярная distance surrogate (не XYZ/ENU) остаются ограничениями.

**Итог:** механизм активен, но старая доверенная медиана не отличает загрязнение от настоящей свежей динамики достаточно надёжно для данного контракта. Оставить закреплённый v8 baseline. R3-H27 lag0.4 — REJECTED на development; lag0.2 — недостаточное original-покрытие плюс зафиксированные diagnostic failures. Validation не расходован.
