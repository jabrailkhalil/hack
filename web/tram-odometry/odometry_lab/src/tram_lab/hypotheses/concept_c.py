"""Concept C: B plus an exported, bounded causal ridge acceleration residual."""
import json
from pathlib import Path
import numpy as np
from .concept_b import AdaptiveEKF


class ResidualEKF(AdaptiveEKF):
    def reset(self, config):
        super().reset(config)
        self.residual_model = config.get("residual_model")
        if config.get("residual_file"):
            self.residual_model = json.loads(Path(config["residual_file"]).read_text(encoding="utf-8"))
        if self.residual_model is not None:
            for key in ("mean", "scale", "coef"):
                value = np.asarray(self.residual_model[key], dtype=float)
                if value.shape != (8,) or not np.isfinite(value).all():
                    raise ValueError("residual arrays must have eight finite entries")
            if min(self.residual_model["scale"]) <= 0:
                raise ValueError("residual scale must be positive")
            if not 0 < self.residual_model.get("limit_mps2", .35) <= 1:
                raise ValueError("residual acceleration bound must be in (0,1]")

    def residual(self, features):
        if self.residual_model is None:
            return 0.0
        model = self.residual_model
        x = np.clip((features - model["mean"]) / model["scale"], -8, 8)
        return float(np.clip(x @ model["coef"], -model.get("limit_mps2", .35), model.get("limit_mps2", .35)))
