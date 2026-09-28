# H16: реально использованные источники

Farina, Marcello; Piroddi, Luigi. Simulation error minimization identification based on multi-stage prediction. IJACSP 25(5):389–406. DOI https://doi.org/10.1002/acs.1203. Online 2010-08-25; volume year 2011.

Consensus: narrow search и fetch записи 9ad098e93cd05a9c84587c0aa88eb1dd, прочитан abstract. Он мотивирует multi-step/simulation loss, не доказывает выигрыш нашей модели. Scite search_literature подтвердил авторов/том/страницы; isOa=false, contentDenied=true. Следующий read_fulltext заблокирован месячной квотой 25 calls, reset 2026-10-01 UTC. Полный текст и свежие контексты цитирующих работ не прочитаны. В карточке были только outgoing citation metadata; mentioning не верификация. Publisher Wiley вернул403. Никаких покупок/подписок.

SciPy1.17 official docs: https://docs.scipy.org/doc/scipy-1.17.0/reference/generated/scipy.optimize.least_squares.html. max_nfev не включает numerical-Jacobian calls; runner считает оба. Научные библиотеки нужны только offline.

## Wolfram: выполнено

Worksheet: wolfram.wl. Первая попытка ExportString(out,RawJSON) дала Export::jsonstrictencoding: Expression Times cannot be exported as JSON; Out=$Failed. Также слово kilogram было неоднозначно. Вторая попытка InputForm с mass of 1 kilogram успешна. Фактический вывод:

```text
"discrete_sum_identity" -> True
"discrete_drive_sensitivity" -> dt*(-((lam*(1-lam^n))/(1-lam))+n)
"bias_resistance_sensitivities" -> {dt*n,-(dt*n)}
"continuous_drive_sensitivity" -> h-(1-E^(-(h/tau)))*tau
"short_horizon_series" -> -h^3/(6*tau^2)+h^2/(2*tau)
"long_horizon_normalized_limit" -> 1
"actuator_stability" -> True
"mass_force_gauge_invariant" -> True
"continuous_sensitivities_tau0393" -> {{0.5,0.21720370385891102,0.5},{2,1.6096515424894802,2},{5,4.607239247946899,5}}
"dimensionless_velocity_residual" -> 5.
"power_per_mass_unit" -> Quantity[1,"Watts"/"Kilograms"]
"quadratic_drag_per_mass_unit" -> Quantity[1,"Meters"^(-1)]
```

Сумма точна для постоянных target/resistance/dt. Чувствительность усиливается с горизонтом, как и влияние ошибки d/сопротивления. На постоянной положительной скорости d и rolling resistance неразличимы без возбуждения/допущений. Общий масштаб mass/force/power неидентифицируем. Loss безразмерный. Доказан только stable scalar actuator pole, не глобальная устойчивость нелинейного observer и не real-data accuracy.

## Код и прежние результаты

Прочитаны pinned core/guarded_readout/Timeline/node/launch/config; experiment.py training_set/acceleration/fit_all/Store; evaluate replay/score/matching/distance; guarded compare; v6 summary; split/plan/test metadata. Source manifest сверяется по git blobs и SHA256 с фиксированным v7. Исторические pins не меняются.

H03#20/H07#22: отрицательные результаты на старом v5, их числа не показатели R2. V6 projection/decay не включены. PR14/23: canonical guarded output и zero-lock. PR26/H11 прочитан как соседний quarantine механизм и не включён. Validation других R2 агентов не читался для выбора H16.
