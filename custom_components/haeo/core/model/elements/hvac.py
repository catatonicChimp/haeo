"""Shared heating/cooling mode and electrical flow for unzoned HVAC."""

from collections.abc import Mapping
from typing import Literal, TypedDict

import numpy as np
from numpy.typing import NDArray

from custom_components.haeo.core.model.element import Element
from custom_components.haeo.core.model.linear import Rows
from custom_components.haeo.core.model.reactive import TrackedParam, constraint
from custom_components.haeo.core.model.solver import Solver

from .connection import Connection, ConnectionOutputName

type HvacElementTypeName = Literal["hvac"]


class HvacElementConfig(TypedDict):
    """Shared HVAC model configuration; mode +1 heat, -1 cool, 0 off."""

    element_type: HvacElementTypeName
    name: str
    connection: str
    mode: float


def hvac_arguments(config: HvacElementConfig, elements: Mapping[str, object], /) -> dict[str, object]:
    """Resolve the one electrical actuator connection."""
    connection = elements[config["connection"]]
    if not isinstance(connection, Connection):
        msg = "HVAC requires a connection"
        raise TypeError(msg)
    return {"connection": connection, "mode": config["mode"]}


class Hvac(Element[str]):
    """Externally selected mode shared by every attached room; no room actuators."""

    mode: TrackedParam[float] = TrackedParam()

    def __init__(
        self,
        name: str,
        periods: NDArray[np.float64],
        *,
        solver: Solver,
        connection: Connection[ConnectionOutputName],
        mode: float,
    ) -> None:
        """Retain the electrical connection and a reactive mode."""
        super().__init__(name, periods, solver=solver, output_names=frozenset())
        self.connection = connection
        self.mode = mode

    @constraint
    def operating_mode(self) -> Rows:
        """Idle consumes no HVAC power; heating and cooling cannot coexist."""
        if self.mode not in (-1, 0, 1):
            msg = "HVAC mode must be -1 (cool), 0 (off), or 1 (heat)"
            raise ValueError(msg)
        power = self.connection.total_power_out
        return power <= 0.0 if self.mode == 0 else power.free()
