# Источники и фактический уровень чтения

## Частные project sources
- R3-H25 user card: baseline, scope, 1 delta, .01 cap, R3 admission.
- Pinned v8 runtime, profile, launch, data-role code and evaluator: read source. Baseline manifest lists exact SHA256.
- PR15 is H02 timing uncertainty, not hypothesis H15: https://github.com/jabrailkhalil/hack/pull/15 (body read).
- PR17 is H05 reliability memory, not H17: https://github.com/jabrailkhalil/hack/pull/17 (body read).
- R2-H20 report: https://github.com/jabrailkhalil/hack/blob/c8b83980facc63348682293ee83574149c385a0e/reports/research_R2/H20/36185299933-1/REPORT.md (mechanism, methods, development and reported decision read; no new R3 outcomes used).
- Historical v5/v6 reports in previous session are context, not H25 measurements.

## Primary public sources, one narrow web search
Jung, Changbae; Chung, Woojin (2011). Calibration of Kinematic Parameters for Two Wheel Differential Mobile Robots by Using Experimental Heading Errors. International Journal of Advanced Robotic Systems 8(5). DOI 10.5772/50906.
https://journals.sagepub.com/doi/abs/10.5772/50906
Read publisher metadata and abstract only (not full text). Motivation: unequal wheel diameters are a systematic error source; their actual method needs final-pose heading errors. Not transferred to our front/rear interface, no performance claims borrowed.

CVRA Robot Software, author-maintained engineering documentation, Calibrate the odometry.
https://cvra.ch/robot-software/howto/calibrate-odometry/
Read HTML guide. Separates wheel ratio, steps/mm and track. Uses an external straight edge/ruler; not evidence that our common scale is observed. No text copied.

Consensus/Scite: new calls deliberately NOT_RUN_KNOWN_QUOTA_STOP, as the R3 card reports coordinator quota exhaustion. No claims of new plugin search or full-text access. No paid retrieval.

Wolfram: Context returned elementary related material only; actual targeted LanguageEvaluator ran math.wl. Exact output and warnings in math-output.txt. Independent local numeric examples in tests. This is algebra under stated ideal assumptions, not empirical confirmation.
