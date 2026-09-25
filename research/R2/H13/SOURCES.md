# H13: источники и пределы переноса

## Код и прежние исследования

Baseline 65bba39ed05c781f3f69a65c02f69931152cbfd9: core, guarded_readout, Timeline, actual v7 YAML/JSON, launch, score/replay/match/metrics, split/plan, тесты. Исходный класс — GuardedReadoutObserver, не старый v5, независимо от исторических имён моделей evaluator.

Прочитаны reports/research_v6/REPORT.md и описания PR #20/H03, #19/H04, #18/H10: сглаживание производной, изменение tau и совместная covariance не дали нужной fault accuracy. H13 не повторяет эти механизмы. Прочитаны PR #14/#23: output-only readout и low-speed zero-lock входят в закреплённый baseline. PR #26/H11 прочитан как соседняя работа; quarantine не включается. Числа других исследователей R2 не использовались.

## Узкий поиск литературы

Consensus search: disturbance observer integral acceleration velocity measurements discrete time sampling time alignment. Из результатов использована одна первичная работа, не как доказательство H13:

Emre Sariyildiz, Satoshi Hangai, Tarik Uzunović, Takahiro Nozaki (2021), **Discrete-Time Analysis and Synthesis of Disturbance Observer-Based Robust Force Control Systems**, IEEE Access 9, 148911–148924. DOI: https://doi.org/10.1109/ACCESS.2021.3123365 . Авторская запись: https://keio.elsevierpure.com/en/publications/discrete-time-analysis-and-synthesis-of-disturbance-observer-base/ . Consensus record: https://consensus.app/papers/discretetime-analysis-and-synthesis-of-disturbance-sariyildiz-hangai/5de4e44366ab5b7bac53f55d8375af62/ .

Фактически прочитано: Consensus fetch — metadata и abstract; Scite search_literature — карточка и цитатные фрагменты; Scite read_fulltext — первые 5500 из 18127 символов индексированного fulltext (введение), НЕ вся статья. Работа рассматривает discrete-time disturbance/force observers и ограничения модели/полосы/шума, но не доказывает выигрыш нашего интервального target. Её acceleration/motor/force interface не переносится в controller/front/rear. Scite incoming graph: 3 edges, truncated=true, low_coverage=true; один доступный mentioning-фрагмент 10.1109/amc51637.2022.9729279 ссылается на анализ ограничений. Mentioning не равно независимой верификации. Другие результаты узкого поиска не использованы для реализации.

## Математика

wolfram.wl исполнен через WolframLanguageEvaluator; фактический ответ в wolfram-output.txt. Для аффинного g и постоянного d endpoint target смещён на -j(h+Delta/2), интервальный residual равен d. При неизменном tau=.5 ошибка идеального обновления сокращается exp(-Delta/tau); clipping состояния — не доказанная этим устойчивость реального observer. Шум двух последовательных скоростей имеет variance 2(1-rho)*sigma^2/Delta^2 (rho — временная корреляция), interval alignment его не устраняет. Постоянная ошибка модели em переносится в target как -em; g и d нельзя разделить без модельных допущений. Контрпример clipping: clip(g+d=4,±3)-g=1 при g=2,d=2. Поэтому clipped segments запрещены. Все величины target имеют единицы м/с².

В реализации интеграл точен относительно кусочно-линейно реконструированных исходных pre-correction snapshots g. Для реального нелинейного g между тиками это приближение. Никаких новых samples, IMU/GNSS или ожидания пары нет. Проверка формулы и unit tests не доказывают точность на записях.
