# R2 H13 — согласование интервала disturbance target

**Вердикт: REJECTED для единственного кандидата H13_interval_linear_v1. Исследовательский отрицательный результат, не готов к merge.**

Механизм активен на реальных данных, идеальная формула проверена, но необходимое улучшение точности не подтверждено. На reused validation clean RMSE +0.041764%, original fault RMSE −0.085461%; необходимы ≥2% clean gain ИЛИ ≥5% original fault gain. Единственная причина отказа общего accuracy-gate — `insufficient_gain`. Допустимость регрессий и safety/coverage не заменяет минимального выигрыша. Семейство всех интервальных методов одним кандидатом не опровергается.

PR: https://github.com/jabrailkhalil/hack/pull/29 . Ветка `research/round2-H13`. Merge/auto-merge не выполнялись. Более поздний main/H11/v8 не включён и не является baseline сравнения.

## 1. Фиксация исследования

| Назначение | Commit SHA |
|---|---|
| R2 baseline | `65bba39ed05c781f3f69a65c02f69931152cbfd9` |
| PLAN до экспериментов | `d70cb94dbebaa0f0bcf8c3a08bc0c3ebdba9ae6d` |
| **Измеренный кандидат, patch и driver** | **`f53ae2b84f6ce1e4fa3f272107a79a86c911d88b`** |
| Отдельный опубликованный freeze | `6cc359f7b8d645606afe087a6469b95b25559614` |
| Неизменяемые исходные результаты | `91b450f276c55a42810a20febe5daeeaadb2d486` |

[PLAN](https://github.com/jabrailkhalil/hack/blob/d70cb94dbebaa0f0bcf8c3a08bc0c3ebdba9ae6d/research/R2/H13/PLAN.json) опубликован до implementation tests и экспериментов. Один кандидат, без настройки tau, физических коэффициентов или реконструкции по результатам. Train64 использован только для vehicle-only replay. Development17 — все предусмотренные группы, точность, безопасность, активация, ablation и стоимость.

FREEZE создан **2026-09-25 20:16:17.250160 UTC**, затем закоммичен и опубликован в собственной checkpoint-ветке. Validation started.json: **20:16:20.448226 UTC**; первый read-only access: **20:16:20.468886 UTC**. До опубликованного freeze validation DB не распаковывались. Хеш содержимого FREEZE по формату Git blob совпадает с опубликованным blob `646634f8fddeda8921005f870b33346529187d8a`. Перед validation сверены source/config/evaluator/split hashes. После validation алгоритм и параметры не изменялись. Отчёт и описательный анализ добавлены позднее, не являются новым измеренным кандидатом.

[Run 36184242998, attempt 1](https://github.com/jabrailkhalil/hack/actions/runs/36184242998) завершён **success**, включая все измерительные стадии, freeze, checkpoint и artifact. Зелёный workflow означает успешное завершение отрицательного эксперимента, не подтверждение гипотезы.

[Полные исходные evidence](https://github.com/jabrailkhalil/hack/tree/91b450f276c55a42810a20febe5daeeaadb2d486/reports/research_R2/H13/36184242998-1).

## 2. Алгоритм и активация

Baseline — **GuardedReadoutObserver**, настоящий `guarded_readout_v7.yaml/json`: readout gain=1.0, holdoff_s=0.5, inner wheel_time_compensation=0.0, adaptation_tau_s=0.5, 20 Гц, alignment delay=0. Оценивается возвращаемый **Estimate.v/s**, а не внутренние observer.v/s.

Изменён только target disturbance:

```text
Delta = t_pair - t_previous_pair
measured_a = (z_pair - z_previous_pair) / Delta
g = native drive_a - resistance(native pre-correction v)
d_target = measured_a - integral(g, t_previous_pair, t_pair) / Delta
weight = 1 - exp(-Delta / 0.5)
d = clip(d + weight * (d_target - d), previous disturbance bounds)
```

Исходные pre-correction g snapshots сохраняются с временами native output ticks. Интеграл — аналитическая сумма перекрытий кусочно-линейных сегментов **точно на [t_previous_pair,t_pair]**, без экстраполяции и без ожидания будущей пары. Он точен относительно реконструированного кусочно-линейного сигнала, а не произвольного истинного g между тиками. История ограничена одновременно **32 сегментами и 0.75 с**; фактический максимум на real replay — **15 сегментов**.

Startup/reset, непокрытый интервал, stale controller/wheels, clipping ускорения/скорости и numerical sign-reversal clamp запрещают обучение на затронутом интервале. Пропуск записывается с причиной; endpoint fallback не добавлен. Исходное продвижение adapt_previous, запрет повторной ассимиляции, eligibility доверенной пары, tau, bounds, physical/numerical predictor, robust R, covariance, guards, low-speed zero-lock и guarded readout сохраняются. Остановка очищает историю.

Это не сглаживание H03, переключение tau H04, joint Kalman H10, H11 quarantine или H12 readout. Runtime принимает только controller/front/rear с прежними единицами/timestamps. Нет GNSS/IMU, bag ID, injected-fault oracle или future samples. Новые runtime-модули — только stdlib.

[Самодостаточный patch](https://github.com/jabrailkhalil/hack/blob/f53ae2b84f6ce1e4fa3f272107a79a86c911d88b/research/R2/H13/algorithm.patch), SHA256 **`746b174c09281061f437e73024644e0beb270b88c17b0ed15644a271f8bd0ef4`**. Applied core SHA256 `cf9804faa802564f77802c91a56fb656939bb506cf60a695ac962b0dce3080f8`.

**Checkout сам по себе не включает H13:** выполнить `git apply research/R2/H13/algorithm.patch`, затем создавать `IntervalReadoutObserver(Config(**v7_profile["config"]), enabled=True)`. Канонический launch в research checkout не переключён на новый класс; `enabled=False` — feature-off baseline. Runtime-патч применяется только в экспериментальной рабочей копии.

## 3. Измеритель и реально воспроизведённый v7

Неизменны `tools/finalization/evaluate.py::score/replay`, `ex.match/metrics`, distance surrogate, `tools/research_guarded/compare.py::fault_windows`, `tools/research_v6/compare.py::summary`. Подменяется только фабрика observer. Новый отдельный BASE_PINS.json проверяет evaluator, runtime, profile, scales и split; старые pins и отчёты не переписаны. Development loader проверяет истинную роль development и DB SHA256 до read-only IO, не переименовывает роль в train/validation.

Независимая baseline factory использует исходный core, извлечённый через git show из закреплённого SHA, и неизменный GuardedReadoutObserver. Старые JSON-ключи — API-алиасы: **baseline_v2 здесь означает R2 guarded v7**, balanced_physics — H13, feature_off — отключённый H13. Это не сравнение со старым adaptive_v5 или Observer(Config()).

Baseline исполнен тем же driver. Во всех **260 replay-сравнениях** (64 train, 101 development с faults/diagnostics, 95 validation) совпали полный fingerprint возвращаемого Estimate и runtime-счётчики baseline и feature-off. Unit-test дополнительно сверяет каждое исходное поле состояния на 6000 шагах. После run проверены три опубликованных полноточных агрегата champion v7 и reference count: **4/4 совпали, max absolute delta=0.0**. Это проверка воспроизведения, не копирование старых цифр вместо исполнения. Подробности в audit.json.

Validation: **19 bag / 10 групп**, reference в 9 группах / **30 bag/receiver-парах**, **698891** точка. Четыре bag без reference (`30618_2255aade`, `30618_4e1e3181`, `30618_7bfbb5ed`, `30618_95c49c30`) сохранены missing. **76 original fault-сценариев / 120 reference-сравнений**. Anchors, windows, bias +5 м/с 5 с, dropout5/10 с и lock3 с не изменены. Два GNSS receiver одной записи не объявлены двумя независимыми поездками; агрегация по исходным группам.

## 4. Результат общего validation-контракта

| Метрика | Baseline v7 | H13 | Абсолютная Δ | Изменение ошибки |
|---|---:|---:|---:|---:|
| Clean group-macro RMSE, м/с | 0.114549861317 | 0.114597701842 | +0.000047840524 | **+0.041764%** |
| Original fault-event group-macro RMSE, м/с | 0.538286782601 | 0.537826756567 | -0.000460026034 | **-0.085461%** |
| Pooled clean RMSE, м/с | 0.216406794155 | 0.216422431195 | +0.000015637040 | +0.007226% |
| Scalar-span distance group-macro RMSE, м | 4.595480653018 | 4.595209237810 | -0.000271415208 | -0.005906% |

| Ограничение | Baseline v7 | H13 | Итог |
|---|---:|---:|---|
| Reference-точки clean | 698891 | 698891 | Без потери |
| False stop samples, clean / fault | 18 / 0 | 18 / 0 | Без роста |
| Original unrecovered | 0 | 0 | Без новых случаев |
| Causal errors / unexpected resets | 0 / 0 | 0 / 0 | Без нарушений |
| Clean per-bag/per-receiver allowance | — | Все пары в допуске | PASS |
| Clean/fault/pooled regression ≤0.5%, distance ≤1% | — | Все агрегаты в допуске | PASS |
| Clean gain ≥2% ИЛИ original fault gain ≥5% | — | Ни одно условие не выполнено | **FAIL** |

[Оригинальный decision.json](https://github.com/jabrailkhalil/hack/blob/91b450f276c55a42810a20febe5daeeaadb2d486/reports/research_R2/H13/36184242998-1/validation/decision.json): **REJECTED**, `insufficient_gain`, safety_reasons=[]. Порог не смягчён.

[Raw results.json](https://github.com/jabrailkhalil/hack/blob/91b450f276c55a42810a20febe5daeeaadb2d486/reports/research_R2/H13/36184242998-1/validation/results.json) · [все per-bag/per-receiver/per-fault метрики CSV](https://github.com/jabrailkhalil/hack/blob/91b450f276c55a42810a20febe5daeeaadb2d486/reports/research_R2/H13/36184242998-1/validation/per_bag.csv) · [bag checkpoints](https://github.com/jabrailkhalil/hack/tree/91b450f276c55a42810a20febe5daeeaadb2d486/reports/research_R2/H13/36184242998-1/validation/bags).

Дополнительные метрики:

| Показатель | Baseline v7 | H13 |
|---|---:|---:|
| Clean group-macro MAE, м/с | 0.047549651404 | 0.047559585394 |
| Clean group-macro signed bias, м/с | -0.015975155952 | -0.016294305539 |
| Fault+recovery group-macro MAE, м/с | 0.225316973762 | 0.225394967061 |
| Fault+recovery signed bias, м/с | -0.065924573423 | -0.065955259584 |
| Group-macro confirmed recovery, с | 0.226255203389 | 0.226602425611 |

Fault MAE/bias используют прежнюю полную fault+recovery маску; это не event-only MAE. Нулевое число невосстановлений не означает одинаковой скорости recovery.

## 5. Существенные регрессии

Clean RMSE хуже в **16/30** парах; event RMSE хуже в **60/120**; distance хуже в **22/30**. Общий original fault RMSE скрывает следующий разрез:

| Original fault | Baseline RMSE | H13 RMSE | Δ |
|---|---:|---:|---:|
| Bias 5 с | 0.414421398 | 0.414305275 | -0.028021% |
| Dropout 5 с | 0.558804079 | 0.555766798 | -0.543532% |
| Dropout 10 с | 0.723733997 | 0.732368955 | **+1.193112%** |
| Lock 3 с | 0.456187656 | 0.448865998 | -1.604966% |

Это описательный group-macro разрез, не замена original-suite admission и не новый отдельный gate.

| Bag / receiver | Fault | Baseline → H13 RMSE, м/с | Δ, м/с | Δ, % |
|---|---|---:|---:|---:|
| 30639_50956d6e/master | Dropout 10 с | 0.086837468 → 0.236122331 | +0.149284864 | **+171.913%** |
| 30639_50956d6e/rover | Dropout 10 с | 0.086635397 → 0.234828577 | +0.148193180 | +171.054% |
| 30618_0686195f/master | Dropout 10 с | 0.358063209 → 0.405086392 | +0.047023183 | +13.133% |
| 30618_0686195f/rover | Dropout 10 с | 0.353737832 → 0.400483751 | +0.046745918 | +13.215% |
| 30639_9f0b519f/rover | Dropout 10 с | 0.844705613 → 0.890340353 | +0.045634740 | +5.402% |
| 30639_9f0b519f/master | Dropout 10 с | 0.844380624 → 0.890007708 | +0.045627084 | +5.404% |

Максимальная абсолютная clean-регрессия: `30618_defd0170/rover`, **0.111658335 → 0.112179795 м/с**, +0.000521459 м/с (+0.467013%), в исходном per-bag допуске.

В **7/120** сравнениях recovery медленнее. Максимум: `30639_3b3d9eb8/master` и `/rover`, dropout10, **0.017672399 → 0.217672399 с**, +0.2 с. На `30618_b15eafc3` и `30639_50956d6e` при dropout10 — +0.15 с для обоих receiver; `30639_9f0b519f/master` lock3 — +0.1 с. Новых unrecovered нет.

Самая большая абсолютная distance-регрессия: `30639_9f0b519f/rover`, **10.480994133 → 10.658801085 м**, +0.177806953 м (+1.696470%). На `30618_2f104a1d/rover`: **0.311448984 → 0.327978712 м**, +5.307363%. Лимит1% относится к агрегату; дополнительного per-bag distance gate задним числом не вводили. Все остальные значения сохранены в raw CSV/JSON; описательный анализ воспроизводится скриптом analyze_saved_results.py.

## 6. Активация, development и ablation

| Активация на clean replay | Development | Validation |
|---|---:|---:|
| Eligible disturbance updates на траектории H13 | 93826 | 144909 |
| Интервальный target применён | 93623 | 144559 |
| Изменённых targets >1e-6 м/с² | 87514 | 137806 |
| Skipped | 203 | 350 |
| Доля skipped | 0.216358% | 0.241531% |
| Обновлений в 1 с после command-class transition | 20097 | 32205 |
| Группы с активацией | 7 | 10 |

Все эти clean skips — stale-сегменты. Clipping/gap на этих eligible clean обновлениях не наблюдались, соответствующие guards проверены отдельно синтетикой. Порог≥100 applied /≥3 групп /≥20 transition updates /≥20 changed targets пройден. Доля skips≤10% суммарно и≤25% в группе с≥100 eligible соблюдена; максимум development group skips около0.5168%. Деноминатор — eligible updates на собственной H13-траектории, не число исходных сообщений.

Train64: **1366299 outputs каждого алгоритма**, 441264 eligible, 440014 applied, 413837 changed, 1250 skipped. Только vehicle-входы; независимая reference accuracy на train не измерялась.

Development: **17 bag /7 групп**, reference в6 группах /19 bag-receiver парах,394221 clean reference-точка. Оригинальные faults:56 сценариев /60 reference-сравнений. Семь bag без reference сохранены missing. Все предусмотренные группы использованы, удобные bags не отбирались.

| Development | Baseline v7 | H13 | Изменение ошибки |
|---|---:|---:|---:|
| Clean group-macro RMSE, м/с | 0.092668142983 | 0.092515753409 | -0.164447% |
| Original fault-event group-macro RMSE, м/с | 0.237548612056 | 0.229397587949 | **-3.431308%** |
| Pooled RMSE, м/с | 0.129305694477 | 0.129189495620 | -0.089864% |
| Scalar-span distance, м | 5.310295004801 | 5.261026251963 | -0.927797% |

Development false stops clean/fault **0/0 у обоих**, original unrecovered **4 у обоих**, без новых случаев. Минимальный accuracy gain также не выполнен. PLAN допускал validation при достаточном покрытии и без новых safety failures даже при слабом development gain; правило не изменялось после просмотра данных.

Неселектируемый development-control `endpoint_same_skips` использует прежний endpoint target при **тех же правилах допустимости и пропуска истории**. Его original fault RMSE **0.2375486120563008**, точно baseline; clean **0.0926684517171935**, distance **5.310506806789214**. Development-эффект H13 не воспроизводится одним включением этих skip-правил. Это ablation правил, не искусственное навязывание одинаковой маски разошедшимся траекториям и не доказательство общей полезности H13. Control не считался выбираемым кандидатом.

В объявленном 1-секундном переходном режиме development clean macro RMSE **0.084366216 → 0.084007766 м/с**, около−0.425%,67489 точек. На validation тот же разрез **0.089097889 → 0.089205974 м/с**, около+0.121%,132544 точки. Само изменение target не обеспечивает улучшения реальных переходов.

Отдельные development low-speed-lock и transition-dropout suites: **28 сценариев**, combined diagnostic event RMSE **0.374192002 → 0.377168172 м/с (+0.795359%)**, без дополнительных safety failures. Они не входят в original-suite admission. Есть локальные development-провалы: `30639_dce52be4/master`, dropout10 **0.227959065 → 0.305348965 м/с (+33.949%)**; `30618_0652866c/master`, dropout5 **0.099996483 → 0.142358354 м/с (+42.363%)**. Все control/phase/diagnostic/missing-reference результаты: [development/results.json](https://github.com/jabrailkhalil/hack/blob/91b450f276c55a42810a20febe5daeeaadb2d486/reports/research_R2/H13/36184242998-1/development/results.json), [CSV](https://github.com/jabrailkhalil/hack/blob/91b450f276c55a42810a20febe5daeeaadb2d486/reports/research_R2/H13/36184242998-1/development/per_bag.csv).

## 7. Наблюдаемая трасса до, во время и после отказа

Худшая абсолютная validation-регрессия `30639_50956d6e`, dropout **[110.5,120.5] с**. Reference master добавлен только внешним анализатором.

| t, с | Режим | d v7, м/с² | d H13, м/с² | v-error v7, м/с | v-error H13, м/с |
|---:|---|---:|---:|---:|---:|
| 110.497966079 | MODEL_ONLY | -0.024994488 | -0.082912373 | -0.001311837 | -0.012149053 |
| 120.497966079 | MODEL_ONLY | -0.123374253 | -0.176491335 | 0.075307982 | -0.456832833 |
| 120.547966079 | MODEL_ONLY | -0.123374253 | -0.176491335 | 0.101670956 | -0.433125713 |
| 121.547966079 | FUSED | -0.046641261 | -0.077131409 | 0.002618546 | -0.002641333 |

Последний update перед anchor: output110.447966079, wheel interval **[110.282752761,110.374717415]**. На H13-траектории measured_a=−0.257740820, current pre-g=−0.363906773, mean(g)=−0.314846657 м/с²; endpoint desired на той же траектории **+0.106165953**, interval desired **+0.057105837** м/с². d до update−0.111186370, после−0.082912373 м/с². [Полная fault-трасса](https://github.com/jabrailkhalil/hack/blob/91b450f276c55a42810a20febe5daeeaadb2d486/reports/research_R2/H13/36184242998-1/validation/traces/30639_50956d6e-fault2.json).

Это свидетельство исполнения target и различия состояний, не отдельное доказательство причинности конкретной ошибки. Feedback, разные состояния и приём оставшихся причинно доступных wheel samples в начале outage не разложены новыми post-validation экспериментами. По трассе ничего не настраивалось. На поздних MODEL_ONLY тиках ошибка H13 больше; после восстановления fusion она снова уменьшается.

## 8. Проверки и вычислительная стоимость

В полном checkout с **применённым patch** в run36184242998:

| Проверка | Итог |
|---|---|
| compileall src и H13 | PASS |
| Legacy suite | **144/144 PASS**,0.857 с |
| Research-integrity suite | **43/43 PASS**,0.528 с |
| H13 implementation suite | **18/18 PASS**,0.975 с |
| Feature-off Estimate/runtime на реальных replay | **260/260 PASS** |
| Dataset/archive/bag SHA, роли/access, freeze barrier | PASS |
| Train → development → published freeze → validation | Выполнено |

H13 checks: constant/affine g, дробные границы, no extrapolation, stale/reset/gap/clipping, future/duplicate, prefix causality, true stop/zero-lock, finite state, time/count bounds, AST-идентичность прежних guard-методов. 15000 synthetic шагов state bounds;6000 disabled all-original-state equivalence. Unit/математика не используются вместо реальной accuracy.

Стоимость: полный development bag `30618_0652866c`, **29207 outputs**. Отброшенный warmup, затем четыре пары **AB,BA,AB,BA**, одинаковый сбор outputs, OMP/OPENBLAS threads=1. Медианы:

| Offline replay | v7 | H13 | Δ |
|---|---:|---:|---:|
| Wall, с | 0.837557314 | 0.964478455 | **+15.153726%** |
| Process CPU, с | 0.837475177 | 0.964356851 | **+15.150500%** |
| Wall / output, мкс | 28.676595 | 33.022168 | +15.153726% |

[Raw cost.json](https://github.com/jabrailkhalil/hack/blob/91b450f276c55a42810a20febe5daeeaadb2d486/reports/research_R2/H13/36184242998-1/development/cost.json). Это Timeline+формирование массива, не ROS publish/subscribe latency. Отдельный synthetic step CPU:3000 шагов,0.057116456→0.071825377 с; это не real-bag latency или RSS.

**Полный установленный и включённый H13 ROS benchmark на real-bag, в двух clock modes, под2CPU/500000000B не выполнялся: accuracy уже REJECTED.** Это разрешено заданием; ресурсный/latency бюджет кандидата на этом уровне не подтверждён. [Обычный CI исходного checkout36184242926](https://github.com/jabrailkhalil/hack/actions/runs/36184242926): все4 jobs success, включая installed/offline canonical ROS. H13 в нём не включён, поэтому это compatibility evidence, не benchmark кандидата.

Один служебный source-export run36182568039 сначала упал: shallow checkout не имел baseline object. Исправленный экспорт36182725155 success, без measurement IO. Локальный source-only export не имел всех исторических артефактов; полный локальный legacy suite имел4 missing-file errors. Полный checkout в основном run прошёл144/144. Исторические release/hash guards не удалялись; неуспешные попытки не выдаются за успешные.

## 9. Источники и ограничения

[SOURCES.md](https://github.com/jabrailkhalil/hack/blob/f53ae2b84f6ce1e4fa3f272107a79a86c911d88b/research/R2/H13/SOURCES.md) фиксирует код/v6/PR20/H03,19/H04,18/H10,14/23 и соседний26/H11. Числа других R2 агентов не использовались для настройки.

Consensus/Scite: Sariyildiz et al., IEEE Access2021, DOI10.1109/ACCESS.2021.3123365. Прочитаны metadata/abstract и первые5500 символов индексированного текста Scite, **не вся статья**. Citation graph усечён с неполным покрытием, mentioning не означает независимую верификацию. Источник — контекст observer limitations, не доказательство H13 и не разрешение переносить acceleration/motor-current/GNSS в наш интерфейс.

[Исполнимый Wolfram worksheet](https://github.com/jabrailkhalil/hack/blob/f53ae2b84f6ce1e4fa3f272107a79a86c911d88b/research/R2/H13/wolfram.wl) и [фактический ответ](https://github.com/jabrailkhalil/hack/blob/f53ae2b84f6ce1e4fa3f272107a79a86c911d88b/research/R2/H13/wolfram-output.txt): для g(t)=g0+jt и постоянного d endpoint bias=−j(h+Delta/2), interval residual=d; ideal adaptation contraction=exp(−Delta/tau),0<factor<1. Это не доказательство устойчивости всего нелинейного observer. Временная разностная noise variance=2(1−rho)sigma²/Delta² остаётся; model error em даёт d−em; g/d не разделимы без модели. Clipping-контрпример: clip(g+d=4,±3)−g=1 при g=2,d=2. Единицы target м/с².

Верификация общего dataset.zip не означает использования test: inner ZIP содержит все роли, но **индивидуальные final/test DB entries не распаковывались и не открывались**. Access:train64/development17/validation19 плюс один development access для cost; train SQL — только vehicle. Исторические final-test метрики не подставлялись. Reused validation не независимый final test; статистическая значимость крошечного fault gain не заявляется. Distance scalar-span surrogate — не XYZ/ENU и не полный terminal drift. Common-mode wheel errors остаются неоднозначными.

## 10. Команды запуска

Фактически выполненная последовательность и окружение: [.github/workflows/research-R2-H13.yml](https://github.com/jabrailkhalil/hack/blob/f53ae2b84f6ce1e4fa3f272107a79a86c911d88b/.github/workflows/research-R2-H13.yml), исходные логи в checkpoint. Основные стадии:

```bash
python -m pip install -r requirements-research.txt
git apply --check research/R2/H13/algorithm.patch
git apply research/R2/H13/algorithm.patch
python -m compileall -q src research/R2/H13
PYTHONPATH=src/reserve_odometry python -m unittest discover -s tests -v
python -m unittest discover -s research/tests -v
python -m unittest discover -s research/R2/H13 -p test_h13.py -v
python research/R2/H13/prepare_data.py --roles train development \
  --journal "$OUT/extraction-prevalidation.json"
python research/R2/H13/run.py train --output "$OUT/train" --workers 2
python research/R2/H13/run.py development --output "$OUT/development" --workers 2
python research/R2/H13/run.py freeze --development "$OUT/development" \
  --output "$OUT/FREEZE.json"
# Workflow коммитит и публикует FREEZE; только после push ставит H13_FREEZE_COMMIT.
python research/R2/H13/prepare_data.py --roles validation \
  --journal "$OUT/extraction-validation.json"
python research/R2/H13/run.py validation --freeze "$OUT/FREEZE.json" \
  --output "$OUT/validation" --workers 2
```

Для повторения **того же frozen candidate**, без нового выбора и без записи в main:

```bash
git fetch origin research/round2-H13 checkpoint/R2-H13-freeze-36184242998-1
git worktree add --detach ../hack-H13-reproduce f53ae2b84f6ce1e4fa3f272107a79a86c911d88b
cd ../hack-H13-reproduce
python3.13 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-research.txt
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
export H13_SOURCE_COMMIT=f53ae2b84f6ce1e4fa3f272107a79a86c911d88b
export H13_FREEZE_COMMIT=6cc359f7b8d645606afe087a6469b95b25559614
export H13_BASELINE_CORE="$(mktemp /tmp/H13-original-XXXXXX.py)"
git show 65bba39ed05c781f3f69a65c02f69931152cbfd9:src/reserve_odometry/reserve_odometry/core.py \
  > "$H13_BASELINE_CORE"
git apply --check research/R2/H13/algorithm.patch
git apply research/R2/H13/algorithm.patch
python -m unittest discover -s research/R2/H13 -p test_h13.py -v
OUT="$(mktemp -d /tmp/H13-reproduce-XXXXXX)"
git show 6cc359f7b8d645606afe087a6469b95b25559614:reports/research_R2/H13/36184242998-1/FREEZE.json \
  > "$OUT/FREEZE.json"
python research/R2/H13/prepare_data.py --roles validation \
  --journal "$OUT/extraction-validation.json"
python research/R2/H13/run.py validation --freeze "$OUT/FREEZE.json" \
  --output "$OUT/validation" --workers 2
```

Это команды воспроизведения, не заявление о втором выполненном validation. Требуется свежий output; старые данные не перезаписываются. Python3.13.5, pinned requirements; NumPy/SciPy только offline.

## 11. Артефакты и итог

[Неизменяемый исходный checkpoint](https://github.com/jabrailkhalil/hack/tree/91b450f276c55a42810a20febe5daeeaadb2d486/reports/research_R2/H13/36184242998-1) содержит source/PLAN, patch/applied files, FREEZE, train/development/validation JSON/CSV, per-bag checkpoints, fault traces, access/extraction journals и все логи. Artifact R2-H13-36184242998-1, ID10886042064, ZIP SHA256 **`7e15dc311c0c5b4933a35ed17d89932c6d8c6aa9d76eb6e12483d7a51344e667`**; скачанные bytes проверены. Checkpoint не зависит от artifact retention.

В этом позднем отчётном коммите добавляются audit.json и analyze_saved_results.py. Полные development-analysis.json и validation-analysis.json предоставлены в дополнительном пакете анализа вместе с ответом; их можно воспроизвести скриптом по распакованным development/validation. Скрипт читает сохранённые результаты, не bag DB, не меняет candidate/gates. Номинальная длительность в описательном fault-type разрезе нормализуется к3/5/10с, оригинальные fault timestamps и scorer не меняются.

**Accuracy: REJECTED. Mechanism: ACTIVE, идеальная формула проверена, необходимая реальная accuracy не подтверждена. Merge readiness: FALSE.** H13 не продвигать. Новый подбор или комбинация с актуальным main — отдельное исследование, здесь не выполнялись.
