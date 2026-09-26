# R3-H30: предварительная проверка основания

Round R3-v8-fixed. Baseline e3b0c9c039d2953fbfcda51231263d38ef9f1024; GuardedReadoutObserver, champion_v8.yaml, 20 Hz, delay=0. Собственная ветка research/R3-H30 создана после поиска branches/PR по R3-H30 и H30 и проверки точного ref (совпадений не найдено). Main/чужие ветки/release evidence не изменять. Merge/auto-merge запрещены.

До реализации кандидата выполнить только vehicle-only diagnostics на всех исходных development bags: число входных событий, новые/принятые wheel samples, age при первом наблюдении observer, per-channel/global source order, sample.t относительно предыдущего output tick, dropped/coalesced events на границе Timeline, число исходных групп и потенциально изменяемых outputs. Не читать validation/final/test и train GNSS; reference для этого этапа не нужен. Не путать ненулевой age с настоящим OOSM и повторные held samples с новым наблюдением.

После чтения кода и linear sanity oracle, до accuracy comparison опубликовать PLAN с ОДНИМ способом native-time assimilation (cross-covariance либо bounded forward replay), coherent readout/fallback и машинными veto. Не выбирать механизм по accuracy. Max history 32 state slots/64 independent events и max_age_s. Структурная некорректность accounting или отсутствие естественного покрытия => INCONCLUSIVE без validation. R3 prospective development gate неизменен (2% clean ИЛИ 5% original fault; <=0.5% clean/fault/pooled, <=1% distance; per-bag/safety/coverage + отдельные v8 suites).

Литература: Bar-Shalom DOI 10.1109/TAES.2002.1039398; явно различать abstract/full text. Consensus/Scite имеют известные quota stops в переданной карточке; не повторять поиски в обход лимитов. Использовать доступный первоисточник и Wolfram/независимую локальную математику.

Первый workflow только выгружает точный baseline source archive для локального изучения; accuracy, dataset и validation в нём не запускаются.
