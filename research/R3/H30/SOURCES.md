# R3-H30: источники и уровень проверки

Полный baseline core/readout/Timeline/canonical launch/profile/evaluator/split прочитан из e3b0c9c039d2953fbfcda51231263d38ef9f1024, не moving main. Хеши в BASELINE.json. Source archive проверен по SHA256/git archive comment.

Предыдущие результаты: H01 PR21 (live metadata/body, механизм/отрицательный результат, source dcf63fb024c3c5f24237884c1ac7bc642c708a67); H12 REPORT на 891729a99902766ae05beff64690d0bfc65e06c1, reports/research_R2/H12/36184024656-1/REPORT.md; H14 REPORT на 2713554d279c87577e7958d6379ca662d900acad, reports/research_R2/H14/36184182027-1/REPORT.md. Точные ключевые разделы прочитаны. H12 менял интеграл readout, H14 не имел покрытия async adaptation. Их метрики не являются результатом H30.

Low-speed suite: прочитан tools/research_lock/low_speed.py на f10e3cfc0689ecbd7894575945897a6696db3e72 (PR13). Точный anchor: 1<meanwheel<2, abs(front-rear)<.15, u>=0, t>max(25,.1*end), t<end-25, lock3/5s. Перенесён на development без validation IO. H11 common-mode: функции common_fault_windows/inject_common из tools/research_h11/compare.py точного baseline используются непосредственно; его validation worker не вызывается.

## Литература
Y. Bar-Shalom, Update with out-of-sequence measurements in tracking: exact solution, IEEE TAES (2002), DOI 10.1109/TAES.2002.1039398, https://ieeexplore.ieee.org/document/1039398/ . Уровень: indexed publisher metadata/abstract, НЕ полный текст. HTML открыл JS/robot verification; прямой PDF https://ieeexplore.ieee.org/iel5/7/22279/01039398.pdf вернул HTTP418. Ограничение не обходилось. Consensus/Scite не вызваны повторно из-за известных quota stops в карточке. Citation contexts не проверены.

WolframContext не дал релевантного доказательства. Отдельный фактический WolframLanguageEvaluator проверил наши явные линейные формулы; worksheet и настоящий output сохранены. Exact joint conditioning/Brownian bridge требуют известных additive drift/process noise и independent fixed-R observations. Нелинейный clipped observer с adaptive d и robust residual-dependent R глобально этим условиям не соответствует. Кандидат использует baseline F=1/local additive-error approximation, а не exact nonlinear OOSM. Численные batch/chronological oracle, PSD и causality проверяются offline; это не доказательство real-data accuracy.
