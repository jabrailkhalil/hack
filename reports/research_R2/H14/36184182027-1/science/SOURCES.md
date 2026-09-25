# H14: источники и границы прочитанного

## Узкая литература

Jiang Lu / Lu Jiang, Liping Yan, Yuanqing Xia, Qiao Guo, Mengyin Fu, Kunfeng Lu (2017). **Asynchronous Multirate Multisensor Data Fusion Over Unreliable Measurements With Correlated Noise**. IEEE Transactions on Aerospace and Electronic Systems, 53(5), 2427–2437. DOI: 10.1109/TAES.2017.2697598.

Consensus: https://consensus.app/papers/asynchronous-multirate-multisensor-data-fusion-over-jiang-yan/5ce1c43c3166513686585241dee6ff95/ . Поиск: `asynchronous multirate sensor fusion state estimation correlated measurements sample reuse disturbance observer wheel speed`, затем отдельный fetch записи. **Прочитаны metadata и abstract**, не полный текст. Abstract описывает асинхронные измерения с коррелированными шумами и численный пример. Это мотивация аккуратного учета корреляций и частот, не доказательство нашего pairing/observer.

Scite: точный поиск по названию вернул metadata, closed access. На дату вызова: 51 citing publications, 23 mentioning, 0 supporting, 0 contrasting; это счетчики индекса, не независимая верификация метода. Следующий вызов `read_fulltext(doi=...)` вернул ошибку **monthly MCP usage limit (25 calls), reset 2026-10-01 UTC**. Полный текст и действительные контексты цитирования через Scite **НЕ прочитаны**. Никаких покупок/подписок или изменений прав.

Публичная проверка metadata/abstract через web: первичная страница института авторов https://pure.bit.edu.cn/en/publications/asynchronous-multirate-multisensor-data-fusion-over-unreliable-me . Не утверждаем, что abstract равен полному доказательству. Остальные выдачи Consensus не используются как доказательная база. Никаких IMU/GNSS/camera/motor-current идей в runtime.

## Wolfram: фактически выполнено

`wolfram.wl` — исполнимый код фактического WolframLanguageEvaluator вызова. `wolfram-output.json` — возвращенный JSON с сохраненным предупреждением undefined symbolic L. WolframContext сам по себе релевантного вычисления не дал. Проверены: арифметическое среднее пары соответствует среднему времени только для affine v(t); строгое продвижение обоих consumed stamps продвигает среднее; среднее не позже самого позднего source stamp; exp-веса компонуются по сумме уникальных интервалов; scalar EMA при tau>0 устойчива для постоянной цели; convex update bounded при bounded цели.

Software invariant «каждый stamp один раз» проверяется тестами, не выводится из символической алгебры. При rho=1 variance среднего = sigma², не sigma²/2. **Ковариация runtime не меняется**. Дифференцирование асинхронного среднего не устраняет шум или jerk; смешанная замкнутая система и качество на записях алгеброй не сертифицированы. Нулевой дополнительный input delay не означает нулевой source age.

## История проекта

Прочитаны core, guarded_readout, Timeline, canonical YAML/launch, evaluator/score/match, split/roles, tests и reports/research_v6/REPORT.md на закрепленных снимках. H06/PR16: отсутствие REACQUIRING в первом раунде показало необходимость activation gate. H03/PR20: сглаживание derivative не гарантирует fault improvement. H04/PR19: переменная tau не дала admission. H02/PR15: R(age/skew) не достиг minimum gain. H10/PR18: совместная covariance[v,d] также имела fault-регрессию. Их старые цифры не являются R2 baseline. PR14/23 дают canonical output-only readout и low-speed zero-lock; PR26/H11 изучен как соседняя quarantine-идея и НЕ включен. Bootstrap/recovery buffering в baseline уже существует и не считается новизной H14.

## Журнал разработки до реальных данных

Исходный source перенесен через приватный GitHub Actions artifact после реального DNS-failure git clone. PLAN commit a012d7a7d7596280bcff73c0a85e6bc8cd14bea6 предшествует локальным тестам. Первая локальная версия:19 H14 tests PASS; затем21 PASS с driver tests. Synthetic-01 выполнен до реальных данных; fixture alternating_zeros оказался дубликатом common_lock. До real-data исполнения исправлен только fixture: теперь нулевой канал чередуется по 0.1s циклам. Алгоритм/параметры по синтетическим ошибкам не подбирались. Дополнительно добавлен fail-fast при отсутствии примененного core hook; baseline/config/evaluator неизменны. Оригинальные локальные логи сохраняются в delivery, не выдаются за Actions.
