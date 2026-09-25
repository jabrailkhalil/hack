from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

FRONT = "/vehicle/front_bogie_velocity"
REAR = "/vehicle/rear_bogie_velocity"
COMMAND = "/vehicle/driver_position_cmd"
VEHICLE_TOPICS = frozenset((FRONT, REAR, COMMAND))
MASTER_VEL = "/sensing/gnss/master/vel"
ROVER_VEL = "/sensing/gnss/rover/vel"


@dataclass(frozen=True)
class Event:
    topic: str
    stamp_ns: int
    received_ns: int
    sequence: int
    data: Mapping[str, Any]
    frame_id: str = ""


@dataclass(frozen=True)
class Estimate:
    time_ns: int
    velocity: float | None
    distance: float | None
    status: str
    diagnostics: Mapping[str, Any] = field(default_factory=dict)


class Estimator(Protocol):
    def reset(self, config: Mapping[str, Any]) -> None: ...
    def update(self, event: Event) -> None: ...
    def predict(self, time_ns: int) -> Estimate: ...
