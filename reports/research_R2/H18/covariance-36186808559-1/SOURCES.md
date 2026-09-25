# H18: источники, реально прочитанные материалы и границы математики

1. Renato Zanetti, Robert H. Bishop (2012), Kalman Filters with Uncompensated Biases, Journal of Guidance, Control, and Dynamics 35(1), DOI 10.2514/1.55120. Через Consensus: узкий поиск Schmidt/consider uncertainty и fetch(c9658c437c8754ae8e13cda8d1dcb9eb). Прочитаны карточка, metadata и abstract/introduction-like текст, НЕ полный текст. https://consensus.app/papers/kalman-filters-with-uncompensated-biases-zanetti-bishop/c9658c437c8754ae8e13cda8d1dcb9eb/ . Источник мотивирует учёт структурированной bias-uncertainty без оценки bias как нового mean state; не доказывает нашу конструкцию или точность на odometry.
2. Primary author bibliography: https://sites.utexas.edu/near/publications/journal-publications/ . Прочитана библиографическая запись: 327–330, DOI выше. Consensus metadata указывал 327–335; это расхождение сохранено, а не выдано за прочитанный PDF.
3. Scite search_literature по точным названиям Kalman Filters with Uncompensated Biases и Partial-Update Schmidt–Kalman Filter вернул: monthly MCP usage limit (25 calls), reset 2026-10-01 UTC. Ни full text, ни citation context через Scite не прочитаны. Подписки не покупались, права не менялись. Citation count/mentioning не используется как независимая проверка результатов.

# Wolfram и аналитические допущения

WolframContext вызван; точные поисковые запросы не дали ответа. WolframLanguageEvaluator затем реально выполнил worksheet wolfram.wl; полный фактический результат в wolfram-output.txt.

Для локальной ошибки x=[v,d], F(T)=[[1,T],[0,1]], P(T)=F P0 F^T+Q(T):
Pvv(T)=Pvv0+2*T*Pvd0+T^2*Pdd0+Qv*T+Qd*T^3/3;
Pvd(T)=Pvd0+T*Pdd0+Qd*T^2/2; Pdd(T)=Pdd0+Qd*T.
Вариант H18 использует Qd=0: random walk не идентифицирован и добавление означало бы другой вариант.

Единицы (проверка размерностей аналитически): v — m/s; d — m/s^2; Pvv — m^2/s^2; Pvd — m^2/s^3; Pdd — m^2/s^4; Qv — m^2/s^3; Qd — m^2/s^5. Все слагаемые согласованы. T=0 возвращает P0; F имеет semigroup. Детерминант двухстрочной observability matrix H=[1,0], H F(T) равен T: в идеальной модели d наблюдаем при двух разнесённых измерениях, но во время outage наблюдений нет. Физическую идентифицируемость common-mode wheel error это не доказывает.

Шмидтовский gain [K,0] сохраняет mean d и Pdd, а Joseph даёт Pvv+=(1-K)^2 Pvv- + K^2 R; Pvd+=(1-K)Pvd-. PSD следует из суммы A P A^T+K R K^T. Начальный envelope diag(2p,2d) доминирует любую PSD P=[[p,c],[c,d]], поскольку разность [[p,-c],[-c,d]] имеет неотрицательные диагонали и determinant p*d-c^2>=0. Это увеличение initial covariance, а не Q×2 tuning.

После legacy d adaptation marginalization сохраняет Pvv, не уменьшает его до старого scalar prior. Новый эпизод вновь применяет train-derived Vd envelope. Это приближённая episode-local модель: clipped nonlinear dynamics, actuator-history uncertainty, selection bias trusted residuals и корреляции derivative pseudo-label с velocity error не оценены полностью. Нельзя называть её точной covariance нелинейного observer или calibrated confidence intervals. Residual variance может содержать common wheel noise и модельную ошибку; два согласованных колеса не становятся независимой истиной.

# Код и прежние исследования

Baseline frozen 65bba39ed05c781f3f69a65c02f69931152cbfd9. Прочитаны core/guarded_readout/Timeline, v7 JSON/YAML, launch, evaluator/score/matching, роли данных, тесты и v3/v5/v6 отчёты. PR #18 H10 — отрицательная совместная коррекция mean [v,d] с Qd; H18 сохраняет прежнее mean d. PR #22 H07 и v5 Q×2/Q×4, v6 projection/decay — исторические отрицательные результаты, не сравнение с R2. PR #14/#23 — механизм и интеграция guarded v7. PR #26 H11 — соседняя quarantine common-mode, изучена, но не включена. Результаты других R2 агентов не использовались.
