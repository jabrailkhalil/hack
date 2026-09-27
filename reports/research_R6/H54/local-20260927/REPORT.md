# R6-H54 — INCONCLUSIVE / optimizer-limited; C1 runtime REJECTED

Исследование завершено. К merge не готово. Main, чужие ветки и исторические отчёты не менялись. Нет merge/auto-merge, validation и final/test закрыты.

## Основной результат

Ровно два preregistered fit C0/C1, 59 реальных residual calls, без restarts или retuning. C1 возвратил исходные F/P/B канонического v8; его clean/fault gain равен 0%, Contract L не пройден (`insufficient_gain`). C0 ухудшил original fault RMSE на 6.8333016%, common-mode на 4.7225852%.

**Саму group-robust цель нельзя объявить опровергнутой:** повторная агрегация уже замороженных групповых losses даёт `J1(C0)=0.9919358040775982 < J1(C1)=1.0`. Это допустимый конечный контрпример к утверждению, что возврат C1 — глобальный минимум. Новый fit/новые физические predictions для этого аудита не нужны и не выполнялись. C0 не выбран вместо C1 после freeze. Общий научный вывод **INCONCLUSIVE (ограничение оптимизации)**; отрицательный runtime-вердикт возвращённому C1 — **REJECTED**.

## Версии

- Baseline `b2783206000091ab11a1c11ac3ff79082188a4fb`, tree `973d50d288e050325ee1c71a90fa8d81f2a099af`; полный GuardedReadoutObserver/champion_v8.yaml.
- PLAN commit до вычислений: `440921dc3ea3b37b8462034c7a0c5296608ab0a2`.
- Измеренный study.py опубликован в commit `1cfc5985a9037e6297c81068fd52bfd8789ca82d`; SHA256 `d9cdd90b989ef26ea84145435ead4279e4b6e4bff09c5baa7dce482866dec4b4`. Его Git blob `9d759bd7e3f8c8add16c11562d9be8a9b9e5769b` совпал с локальным. Commit опубликован после выполнения; source hashes были заморожены до fitting.
- Исходный H44 measured source `0ca93500d4d305c21c998bfd8d2a2e78c98b90ad` используется как byte-verified offline dependency. Его overlay не переносится в main этим PR.
- DEPENDENCIES.lock SHA256 `a153cc9ee9eda505ceb43ab98447a996b331e1008cf7196bc9ed9f82920d64d7`.
- FITS_FREEZE SHA256 `62cbb5696b75e872220eac079333f318c433f5218fb7526eb69dbaa0a62bfd3b`, опубликован в Drive до train-check.

## Метод

Сохранены H44 eligible windows, target H42, F/m,P/m,B/m family, пятисекундный own-config warmup, horizons .5/2/5s, scales, bounds, prior, wire duplicates и runtime/scorer. Все покрытые группы остаются; группа 8269991eafa82c45 не удалялась.

141 train-fit окно / 25 bag / 15 групп; 54 train-check окна / 5 групп. Baseline независимо воспроизведён на всех fit-окнах, max difference 0.0. Teacher только offline unsigned-speed proxy, не official signed/XYZ truth.

`eps=.0010757599412382314`; `Rg=Lg/max(Lg0,eps)`, одинаковая масса групп и исходные within-group bag/window weights. C0 = mean(Rg)+prior. C1 = .5 mean(Rg)+.5 mean(worst8 of15 Rg)+prior. Prior `.01*mean(logratio**2)` не менялся.

TRF least_squares, jac2point, max_nfev80, ftol/xtol/gtol1e-8, одинаковый старт0. Несглаженный сортированный sqrt(Rg)-tail заранее объявлен, квадрат residual norm равен цели. В начальной точке все15 Rg=1; C1 остановлен по xtol, optimality0.2888486, njev1. Success flag не является сертификатом оптимальности в точке ties.

C0 theta=(1.216075743636,8.836222102545,1.250498201415), nfev7/28 actual calls. C1 theta=(1.188434318103,7.021838337152,1.139220235088)=v8, nfev28/31 actual calls.

## Train-check и development

На check C1 против C0: aggregate velocity -4.5514%, integral -7.8550%; worst velocity -9.9186%, worst integral -13.5496%. Заранее фиксированный допуск пройден. Но без группы6090ff2c1bc8dee6 worst velocity gain остаётся лишь0.1376%, worst integral становится0.0721% регрессией; концентрация эффекта раскрыта. LOO — frozen-prediction reaggregation, **не retraining CV**.

Один development pass:17 bag/7групп,56 original fault cases с полным faulted-bag replay,26 low-speed и28 common-mode. Первая транспортная попытка остановилась до SQL/replay из-за leading slash в ZIP path; исправлено только извлечение с опубликованным amendment, измерительный pass один. У unchanged H44 driver сохранены технические aliases: main=v8,gnss=C1,wheel=C0. Оба H54fit используют H42; wheel здесь не другой teacher.

| Метрика | v8 | C0 | C1 |
|---|---:|---:|---:|
| Clean group-macro RMSE, м/с | .092668142983 | .092792626595 | .092668142983 |
| Original fault RMSE, м/с | .237548612056 | .253781025173 | .237548612056 |
| Pooled clean RMSE, м/с | .129305694477 | .129472953985 | .129305694477 |
| Clean scalar distance, м | 5.310295004801 | 5.307240104886 | 5.310295004801 |
| Full-faulted scalar distance, м | 6.269376947281 | 6.239600847371 | 6.269376947281 |
| Low-speed event RMSE | .368545673306 | .358393121920 | .368545673306 |
| Common-mode event RMSE | .100632272301 | .105384717123 | .100632272301 |

394221 matched clean samples, без новых false stops/coverage loss/causal errors/resets. Исходные scorer unrecovered:4 original,6 low,2 common, одинаковы во всех моделях. C1 не исправляет имеющиеся проблемы baseline.

C0 локально ухудшает dropout5s на 30618_88548b02: master .09152494→.18826263 (+105.6954%), rover .09230434→.18899950 (+104.7569%). Исключение8269991eafa82c45 только из diagnostic aggregate меняет fault delta C0 с +6.8333% на -4.2068%. Не использовать этот LOO как оценку полного набора.

## Проверки

161 canonical unit,43 integrity,12 H54 tests PASS. Patch apply/check на pristine baseline и повтор12tests PASS. Все320 baseline files неизменны.

C1/v8:73 clean/full-fault NPZ arrays,1584837 строк повторов, совпадают побайтно;366 receiver-score pairs и runtime counters точны. Вспомогательные колёсные столбцы содержат одинаковые missing-value NaN; опубликованные t/v/s конечны.241 проверка integral(delta_v)=delta_s: max residual8.7899243e-11m при допуске1e-7m. Post10/terminal delta_s сохранены, backfill/reset отсутствует.

Реальные measurements, не synthetic accuracy. GitHub Actions/installed enabled ROS/отдельные latency,RSS,CPU benchmark не запускались. Нет независимого final test. H54 solver не перезапускался после finding. Candidate.patch не создан: C1identity не имеет нового runtime diff; research.patch содержит offline research source.

## Полные результаты в Google Drive

- [Workspace H54](https://drive.google.com/drive/folders/1087tRHb09j71ZIrIjQ5G4aNLTd9z3TGg).
- [Полный русский отчёт](https://drive.google.com/file/d/1fmqYbjtslRjji02miP2ZG77lvIDbYPbO/view?usp=drivesdk); SHA256 `d264b4c6662b5da944c85b413245b8c0243eb0dd7ee7a2b5c91bdd7beb0caceb`.
- [SUMMARY.json](https://drive.google.com/file/d/19Qk4QpTI52jobsYN_5zTWCBe9k98CqMi/view?usp=drivesdk).
- [Полный пакет](https://drive.google.com/file/d/1XWqQxDTzvRz6z3tHktEZx6bRrBYTjBfQ/view?usp=drivesdk):79243551bytes, SHA256 `e1d9a1816eb64cde78a077391a19295299d360662d74a0505a0cef747d9fac0b`;194 payload files плюс SHA256 manifest.
- [Offline research.patch](https://drive.google.com/file/d/12MONncHNg_OJwCuU4kv4UTtDSjrrAixc/view?usp=drivesdk).

Пакет включает все raw predictions/traces, fit/call/freeze/check/development/LOO results, зависимости по ссылкам и hashes, команды, код и локальные журналы. Зависимости заново не генерировать. Для независимого воспроизведения нужен чистый baseline, exact H44 source_overlay, новый lock путей при тех же bytes и отдельные output directories. Study stages: prepare → publish objective → fit → publish FITS_FREEZE → confirm; development только по ADMISSION. Полные фактически исполненные CLI сохранены в отчёте/логах.
