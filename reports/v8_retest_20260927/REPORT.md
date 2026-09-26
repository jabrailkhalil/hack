# Повторная проверка v8_residual070, 27.09.2026

**LOCAL_TESTS_PASS / RELEASE_STILL_BLOCKED.** Кандидат, его YAML/JSON, численное
ядро, evaluator и default не менялись. Проверяемый head: f1b83058127bab1b57108a6d8f5daa1d93d4f7e3.
main не переключён; нового validation RMSE нет.

## Реально выполнено

255 unit invocations PASS: 161 runtime (включая 5 ранее непроверенных packaging
checks), 43 integrity, 27 candidate, 24 release. Compileall и bash syntax PASS.
Снимок численного кода e3b0c9c дополнен точными candidate/release overlays и
полученными с GitHub актуальными packaging-файлами. Все 19 baseline hashes,
10 frozen candidate hashes и Git blob SHA упаковки сверены. Это не заявление
о полном свежем clone или выполнении ROS tests.

Повторены все 17 development bags, 56 original faults, 56 full-faulted replays,
26 low-speed, 28 abrupt и 26 slow common-mode scenarios. Сопоставлено 394221
receiver-time samples. С предыдущим опубликованным запуском **точно совпали**
17 per-bag JSON без wall-time, 73 NPZ / 146 arrays / 3169674 rows, все основные
и supplemental metrics. Максимальная разность 0. Базовый fingerprint EXACT.
Первая попытка исполнения была остановлена лимитом времени среды на 16/17
записях и не используется как результат; полный повтор завершён отдельно.

| 30618, reused development | v8 | residual070 |
|---|---:|---:|
| Clean RMSE, m/s | 0.065329745 | 0.064907484 |
| Original fault RMSE, m/s | 0.272398330 | 0.207065180 |
| Full-faulted scalar-span distance RMSE, m | 1.227531488 | 1.168662597 |

Fault error -23.9844% на 30618, -11.0012% в целом подтверждён повтором, не новым
holdout. Прежняя slow-common regression +0.3239% тоже воспроизведена, не скрыта.
Во время wheel dropout команда контроллера в native benchmark доступна.

## Установка и длительные тесты ядра

Wheel 0.8.1 собран без сети (--no-index --no-build-isolation --no-deps), установлен
в пустой target. Проверены единственные installed entrypoint, launch и YAML.
Обычный installed default по-прежнему v8; residual070 подаётся явно через Config.

Из установленного wheel выполнены ДВА отдельных прогона по 6 часов модельного
времени на 20 Hz: healthy и faults. Каждый: 432001 ticks для v8, кандидата и
независимой копии кандидата, всего 2592006 step-вызовов в двух прогонах.
Оба проходят проверки конечности, ограничения скорости/поправки, неизменного
размера состояния, reset parity, независимого state/output parity и интеграла s.
Max integral residual <=1.02e-10 m. В healthy после первых 5 s максимальная
ошибка относительно заданной синтетической скорости 0.03685 m/s у обоих.

Ограничения: два разрешённых CPU и RLIMIT_AS=500000000 B для ОДНОГО Python
процесса. Наблюдаемый peak RSS <97 MB. Это НЕ Docker/ROS/DDS resource check,
НЕ 6 часов реального wall time, НЕ end-to-end latency certification.
Задержки step и счётчики режимов приведены в RESULT, полные RSS samples в архиве.

Важно: в faults-прогоне оба профиля находились MODEL_ONLY на 430790/432001 ticks.
Этот жёсткий синтетический поток включает all-input dropout, lock, большие
смещения и не задаёт физически согласованную динамику. INVARIANTS_PASS означает
отсутствие NaN/разрушения состояния, но НЕ успешное восстановление после всех
отказов. Ни восстановление, ни новую реальную accuracy этим тестом не сертифицируем.

Повторение после локальной установки wheel:

```bash
python research/v8_release/kernel_soak.py --installed /path/to/target --output /new/healthy --pattern healthy
python research/v8_release/kernel_soak.py --installed /path/to/target --output /new/faults --pattern faults
```

## Почему выпуск не подтверждён

Повторно запрошен job validation-inputs старого CI run 36274037856, чтобы получить
validation payload. Попытка 2 вновь failure до шагов; новые jobs 108498220366 и
108498221499 не выполнили validation/ROS. Причина по доступным ответам не установлена.
Это был retry старого staging, не успешный запуск нового validation runner.

Локальный validation preflight прекращён до SQL: отсутствуют все 19 validation DB.
Прямой источник Yandex недоступен (DNS из container; web тоже не получил файл).
Поиск Library не дал исходного архива. Final-test не декодировался. Development
не переименовывался в validation, пороги и профиль не подстраивались.

**Для завершения numerical admission нужен исходный dataset.zip или 19
validation DB с исходными hashes. Installed ROS ещё требует ROS Humble/рабочего
runner. Эти два ограничения остаются; main остаётся v8.**
