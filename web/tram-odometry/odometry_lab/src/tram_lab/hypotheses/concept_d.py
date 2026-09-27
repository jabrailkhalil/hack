"""Concept D: a supplied, ordered metric route; no route inference from wheels.

A branch at a switch must be resolved by the caller. This class never selects
one using a bag name, test trajectory, clock or future GNSS positions.
"""
import numpy as np


class Route:
    def __init__(self, points):
        self.points = np.array(points, dtype=float, copy=True)
        if self.points.ndim != 2 or self.points.shape[1] not in (2, 3) or len(self.points) < 2:
            raise ValueError("an ordered Nx2 or Nx3 metric route is required")
        if not np.isfinite(self.points).all():
            raise ValueError("route must be finite")
        if self.points.shape[1] == 2:
            self.points = np.column_stack((self.points, np.zeros(len(self.points))))
        self.delta = np.diff(self.points, axis=0)
        lengths = np.linalg.norm(self.delta, axis=1)
        if np.any(lengths <= 0):
            raise ValueError("duplicate consecutive vertices are forbidden")
        self.arc = np.r_[0., np.cumsum(lengths)]

    def position(self, s):
        query = np.asarray(s, dtype=float)
        if not np.isfinite(query).all() or np.any(query < 0) or np.any(query > self.arc[-1]):
            raise ValueError("distance outside supplied route: no silent extrapolation")
        index = np.clip(np.searchsorted(self.arc, query, side="right") - 1, 0, len(self.delta) - 1)
        fraction = (query - self.arc[index]) / (self.arc[index + 1] - self.arc[index])
        return self.points[index] + fraction[..., None] * self.delta[index]

    def tangent(self, s):
        self.position(s)  # validate the same domain
        index = np.clip(np.searchsorted(self.arc, s, side="right") - 1, 0, len(self.delta) - 1)
        vector = self.delta[index]
        return vector / np.linalg.norm(vector, axis=-1, keepdims=True)
