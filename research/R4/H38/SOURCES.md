# R4-H38: фактически прочитанные источники

## Первичный научный источник
Hao Zhu, Henry Leung, Zhongshi He, 2013. A variational Bayesian approach to robust sensor fusion based on Student-t distribution. Information Sciences 221, 201–214. DOI: 10.1016/j.ins.2012.09.017.
Publisher: https://www.sciencedirect.com/science/article/abs/pii/S002002551200610X
Прочитаны metadata/abstract и доступные издательские excerpts, не полный текст. Прямой DOI open позже вернул access error; карточка издателя найдена web search. Использован лишь принцип heavy-tailed likelihood и VB, а не чужие численные результаты как доказательство для одометрии. Формула с тремя итерациями и clipping — собственная ограниченная инженерная аппроксимация; не утверждаем точное воспроизведение опубликованного VB-фильтра.

## Собственная математическая проверка
WolframLanguageEvaluator действительно исполнил wolfram.wl. Результат в wolfram-result.json: scale/variance, эффективный R, Joseph, реконструкция gain при отсутствии floor, PSD, Gaussian limit, пределы gain. Warnings в algebra response отсутствуют. Ранее WolframContext не нашёл запрошенные формулы; его нерелевантные snippets не использованы. Positive scalar covariance не доказывает устойчивость всей switched/clipped системы. Постериорный floor 1e-8 может нарушать восстановление gain по Ppost/Pprior; это отдельно проверяется в тесте и запрещает безусловное утверждение readout parity у несуществующего кандидата.

## Проектные контрпримеры
Прочитаны полные тела PR15/H02, PR17/H05 и PR35/R2-H20, включая measured SHA и ссылки на их immutable reports. Это прошлые результаты на иных baseline, не новые H38 метрики.
- H02: https://github.com/jabrailkhalil/hack/pull/15 — age/skew R, insufficient gain, локальные recovery регрессии.
- H05: https://github.com/jabrailkhalil/hack/pull/17 — история надёжности, negligible gain, коррелированные wheel errors остаются проблемой.
- H20: https://github.com/jabrailkhalil/hack/pull/35 — направленный вес, +/− slip trade-off и недостающий qualitative veto; H38 PLAN фиксирует отдельные обе-sign veto заранее.

Карточка R4-H38, baseline core/guarded_readout/Timeline/ROS adapter/launch/profile, loader/split/scorer/tests и v6 report прочитаны из целиком верифицированного ZIP. Только controller/front/rear входят в estimator; reference доступен лишь внешнему baseline development scorer.

## Квоты и границы
Consensus/Scite в этой задаче не вызывались повторно после известных сообщений о месячных лимитах в предыдущих раундах. Не заявляем новую проверку citation context или full text через эти сервисы, не покупаем доступ. Отсутствие плагина не было блокером: source/data/execution доступны, итог INCONCLUSIVE определяется зарегистрированным foundation coverage.
