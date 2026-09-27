# R6-H53 — REJECTED: full fault → recovery objective

**Исследовательский отрицательный результат, не готов к merge.** Две конфигурации обучены; замороженный train-check выполнен один раз. C1 улучшает primary full-cycle objective относительно matched C0 на **4.057894%**, меньше требуемых 5%, но ухудшает его относительно canonical v8 на **16.397853%** и добавляет один индивидуальный случай невосстановления. Development, validation, final/test и installed ROS не выполнялись. Это не отсутствие данных: coverage PASS.

## Версии и изоляция

Baseline `b2783206000091ab11a1c11ac3ff79082188a4fb`, tree `973d50d288e050325ee1c71a90fa8d81f2a099af`, все 320 source paths/bytes/modes проверены. Runtime — полный `GuardedReadoutObserver` с `champion_v8.yaml`, 20 Hz, delay=0. Main и historical reports не изменены; merge/auto-merge/force-push не выполняются.

Существующий PLAN `5c6bb15d4f86c9057e89f4acfe561165e60c08b2` сохранён без изменения численного протокола. Его прежний локальный lock отсутствовал: не реконструировался. Новый проверенный lock `7ce57d6d1cd021d02b4416cc29e6d199cc45cda424fdef0045ae9223abec1d2f` связан с premeasurement receipt `1771e9f959d2fd6760f223df78d9d05efaaaee70`, опубликованным до SQL/построения окон. Registry был PLANNED, Drive checkpoint пуст; отсутствия любых сторонних локальных процессов не заявляем.

C1 configuration commit `d60e1ea890552978fa901763a26a990101df10fc`; **freeze C0/C1 `33ba7a7f7a91b63e5759681024a4f99c578fce60` опубликован и перечитан ДО check speed targets и predictions**. Полные offline исходники, тесты и конфигурации заранее сохранены в [source archive](https://drive.google.com/file/d/1Mf3Mo9VtEvr5DyfxQNi9_n3D2dyruDJx/view), SHA256 `3309ea452a20c96e466e7ab50ac475b0f87077c3d50deb8104a5593c1ed1a1eb`. Git содержит YAML/freeze; report-only commit не является commit всего offline-кода.

## Единственное изменение и одинаковый контроль

Меняется только offline objective; runtime-семейство и численная схема прежние. C0 — H44-style short velocity + prefix integral; C1 — те же short terms плюс event velocity, magnitude-path у конца dropout и после 10s recovery. H44 уже имел short integral, это не заявляется новизной H53. Оба fit меняют только effective F/m, P/m, B/m через прежние torque/power/brake fields. d adaptation, readout, R/Q, guards, stop/recovery, zero-lock, quarantine, Timeline и scorer неизменны. Входы runtime только controller/front/rear. Signed s не заменяется unsigned proxy и не сбрасывается. Обычный checkout не активирует экспериментальный YAML. C0 не запасной selectable кандидат.

| Параметр | v8 | C0 | C1 |
|---|---:|---:|---:|
| F/m, м/с² |1.188434318|1.438782225|1.419178506|
| P/m, м²/с³ |7.021838337|8.547083451|8.531508160|
| B/m, м/с² |1.139220235|0.778315304|0.823564561|

## Данные, objective и бюджет

Пять обязательных архивов source/dataset/H42/H43/H44 проверены по SHA256; native H42/H43 verifiers — 85/53 payload-файла, folds согласованы для всех 64 записей. Exact-wire dedup: 36 fit / 12 check представителей. Только эти 48 train DB извлекались и читались. Ни одна группа не удалена по ошибке. H44 — historical evidence, teacher — unsigned offline proxy, не official combined XYZ.

Детерминированные anchors через 5s, первые два пригодных на фазу/bag; без error ranking. Полная teacher availability до end+10, только соседние accepted rows gap≤0.2s, без bridging masked intervals. Coverage: **115 fit anchors / 21 bag / 13 groups; 54 check / 9 bag / 5 groups**. До freeze check IO ограничен vehicle inputs и teacher stamp/accepted для coverage; не speed values/predictions.

Каждый residual проходит собственный 5s scalar warmup, 5/10s virtual both-wheel dropout и 10s recovery. Удаляются реальные wheel events через исходный Timeline; held samples стареют естественно. L0 — шесть velocity/prefix-integral terms на .5/2/5s. L1=L0+(V5+E5+R5+V10+E10+R10)/6. Шкала пути S_D=(D+.05)(.1+.2D) одинаковая у конца отказа и после recovery. Одинаковый prior .01 mean(logratio²), equal anchor/bag/group weights. Полные формулы в неизменном PLAN.

Один TRF/2-point fit на вариант, max_nfev80, bounds (.05,1,.05)…(5,100,5), no restarts. **C0: nfev14/njev10/44 actual calls; C1:9/8/33; total77**, включая finite differences. Оба ftol-success, не доказанный global optimum. На fit L1: v8 .411573950, C0 .280342236, C1 .273320467.

## Замороженный train-check

108 циклов на профиль, 324 для трёх. Ниже RMS из иерархически усреднённых квадратов, не среднее RMSE. Это H53 long-cycle proxy metrics, **не canonical original-fault/development/official XYZ score**.

| Метрика | v8 | C0 | C1 |
|---|---:|---:|---:|
| Primary L1, безразмерная |.282693335|.342966176|.329048972|
| Short L0, безразмерная |.123285270|.141987786|.137023365|
| Event RMS abs-speed error, м/с |.587447572|.655437000|.642456009|
| Outage-end magnitude-path RMS, м |4.377317474|4.885159223|4.790640061|
| End+10 magnitude-path RMS, м |7.592502706|8.294954675|8.100943911|
| Recovery abs-speed RMS, м/с |.490067364|.574642325|.556211154|

C1/v8: event RMS +9.364%, end-path +9.442%, recovery-path +6.697%, recovery-speed +13.497%. Mean magnitude velocity bias −.026576→+.056981m/s; mean path bias after recovery −.145349→+.978030m. Полные signed величины сохранены отдельно.

Gates FAIL: material gain C1/C0, non-regression C1/v8, no-new-individual-unrecovered. Gates PASS: 5/5 groups improve C0, per-group≤5%, all LOGO positive (gain3.1984…5.0885%), no added false stops. Порог не смягчался.

| Group | v8 L1 | C0 L1 | C1 L1 | C1/v8 |
|---|---:|---:|---:|---:|
|0d4506540f0e7621|.209369138|.343730025|.326672869|+56.0272%|
|6090ff2c1bc8dee6|.397628749|.362300592|.349617095|−12.0745%|
|bc1e4cbe924a90ce|.547062447|.601559942|.588622165|+7.5969%|
|dc785decbed3d7ce|.066949256|.215224440|.193601112|+189.1759%|
|eeabf7d118bbcdac|.192457085|.192015881|.186731621|−2.9749%|

## Новый failure, скрытый одинаковой суммой

Unrecovered counts v8/C0/C1 **5/6/5**, false stops **0/0/0**. Но C1 получает новый failure `ed7e07e90c0b1c0bc5e0`, bag30639_2b4a6347, t0=195s, dropout5. v8 recovery3.85s; C1 не достигает 20 последовательных outputs с abs(abs(v)−teacher)<.25m/s за10s. Event RMSE .531311→.768991m/s; recovery RMSE .214532→.590441m/s; end+10 magnitude-path error3.467601→8.985367m. Signed s_faulted−s_clean своего профиля3.432028→8.924697m — не абсолютная XYZ-ошибка. Случай t0=340/dropout10, исправившийся у C1, также сохранён и не отменяет новый individual failure.

Terminal здесь означает конец **цикла end+10**, не whole bag. Полный faulted-bag distance и whole-bag terminal NOT_RUN_AFTER_CHECK_REJECTION, не RMSE0. Все324 signed integration identities PASS, max5.68434e−13m. REGRESSIONS.csv сохраняет471 строку увеличения разных абсолютных ошибок; полные таблицы включают улучшения.

## Проверки и ограничения

161 canonical,43 research-integrity,24 prefit и31 final H53 tests PASS; наборы повторяются. Profile/only3fields/causality/masks/transport/own warmup/zero-lock/common-mode/signed integral проверены. Независимый audit сохранённых NPZ пересчитал objective, weights, recovery/gates: maxdelta5.55e−17. Проверены18frozen/130window/320source/48DB файлов и teacher hashes; actual fit source pins неизменны.

Window construction пережил120s timeout после42готовых units; resume сохранил их побайтово. Далее выявлена неверная дополнительная эквивалентность: удаление wheels может изменить момент доступности controller в такте. Cache всегда использовал actual faulted Timeline. До fit проверка исправлена на независимый исходный evaluator с no-outcomes recorder; targets/anchors/objective не менялись. Failed logs и transport witness сохранены. Это не retuning по check losses.

Installed enabled ROS/CPU/RSS/latency и реальные low-speed/H11 suites NOT_RUN_AFTER_CHECK_REJECTION. Unit tests не сертифицируют deployment. Никаких новых Actions accuracy/зелёного CI не заявляется. Повторно использованный check из5групп не независимый final test. Архивы, source, README, exact commands, post-audit и подробный русский REPORT находятся в [H53 workspace](https://drive.google.com/drive/folders/1noeLMnEXnjhKG9TlgGxgmwVCk9MsCR0w). Canonical зависимости не дублируются.

Аудит без SQL/новых прогнозов: `python post_analysis/audit.py --work /path/to/H53 --output /new/POST_AUDIT.json`.

**Не продвигать C1. Отрицательный результат относится к этой фиксированной паре objectives/fit, не ко всем методам full-cycle identification.**
