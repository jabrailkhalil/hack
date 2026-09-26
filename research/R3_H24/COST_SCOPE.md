# Cost-only scope correction, no candidate changes

The completed run36220877255 rejected both frozen fits at development; no
validation is authorized. The original cost.json retains step CPU after10s
warmup but replay CPU/wall includes that warmup. Do not label it steady replay.

A separate cost-only run uses the SAME measured source6b3a11a, SAME exact fitted
JSON (hash-checked), SAME20Hz development input and AB/BA order. Its replay timer
starts just before the first step at >=10s; step/replay CPU and wall then cover
the same remaining180s interval. Original evidence is retained unchanged.
No fitting, no new parameter variant, no development accuracy selection, no
validation/test. This measurement is offline CPU, not installed ROS latency.
