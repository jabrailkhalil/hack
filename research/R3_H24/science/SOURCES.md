# R3-H24: actual source access, not proof of performance

User-provided mechanism reference: Han and de Callafon (2011),
Closed-loop Identification of Hammerstein Systems Using Iterative Instrumental
Variables, IFAC Proceedings Volumes44(1),13930-13935.
DOI10.3182/20110828-6-IT-1002.01589.
Publisher record: https://www.sciencedirect.com/science/article/abs/pii/S1474667016458635

Level actually read: publisher search-record metadata and abstract. Direct
publisher HTML open returned403; full paper NOT read. The abstract concerns
input/output noise correlation in feedback Hammerstein identification, a
triangular static basis, iterative instrumental variables and a different servo
experiment. H24 borrows only the static/dynamic separation motivation. It does
NOT implement that IV estimator, establish its feedback assumptions, or transfer
its reported performance to this vehicle. This offline pseudo-label fit remains
vulnerable to wheel bias, feedback and timestamp confounding.

The task and earlier reports identify exhausted monthly Consensus/Scite quotas.
No R3 retry/search was made against those known quota stops; no fulltext or
citation-context check through those plugins is claimed. No purchase or access
change was performed. Earlier R1/R2 reports were read through GitHub, not treated
as new R3 measurements.

WolframContext and WolframLanguageEvaluator actually called before fitting.
Worksheet/output here retain the shape, rank, crossover and unit checks. Full
ordered-simplex parameterization is independently exercised in test_driver.py;
q2-q1=(1-a)b, q3-q2=(1-a)(1-b)c, 1-q3=(1-a)(1-b)(1-c), all nonnegative
for a,b,c in[0,1]. These facts do not prove identification or switched-observer
stability. Repeated samples at one notch do not increase structural design rank.
