"""Test data and factories for the Appliance element.

Each case feeds the appliance from a supply at a price per period, with
one-hour periods, so the run's energy must come from the in-window periods.
"""

from collections.abc import Sequence

import numpy as np

from custom_components.haeo.core.model.elements.appliance import Appliance

from .element_types import ElementTestCase, ExpectedOutput


def _case(
    description: str,
    *,
    in_window: Sequence[float],
    energy: float,
    duration: float,
    supply_price: Sequence[float],
    expected_outputs: dict[str, ExpectedOutput],
    expected_cost: float,
    armed: bool = True,
) -> ElementTestCase:
    """Return a case for an appliance fed by a supply at the given price per period."""
    n = len(in_window)
    return {
        "description": description,
        "factory": Appliance,
        "data": {
            "name": "appliance",
            "periods": np.ones(n),
            "in_window": np.asarray(in_window, dtype=np.float64),
            "energy": energy,
            "duration": duration,
            "armed": armed,
        },
        "inputs": {
            "input_cost": np.asarray(supply_price, dtype=np.float64),
            "max_power": [np.inf] * n,
            "min_power": [0.0] * n,
        },
        "expected_outputs": expected_outputs,
        "expected_cost": expected_cost,
    }


VALID_CASES: list[ElementTestCase] = [
    _case(
        "Run takes the cheapest in-window period",
        in_window=[0, 1, 1],
        energy=2.0,
        duration=1.0,
        supply_price=[0.5, 0.5, 0.1],
        expected_cost=0.2,
        expected_outputs={
            "appliance_power": {"type": "power", "unit": "kW", "values": (0.0, 0.0, 2.0)},
            "element_power_balance": {"type": "shadow_price", "unit": "$/kWh", "values": (0.5, 0.5, 0.1)},
        },
    ),
    _case(
        "Run spreads over the cheapest in-window periods",
        in_window=[1, 1, 1],
        energy=2.0,
        duration=2.0,
        supply_price=[0.1, 0.2, 0.05],
        expected_cost=0.15,
        expected_outputs={
            "appliance_power": {"type": "power", "unit": "kW", "values": (1.0, 0.0, 1.0)},
            "element_power_balance": {"type": "shadow_price", "unit": "$/kWh", "values": (0.1, 0.2, 0.05)},
        },
    ),
    _case(
        "Window shorter than the run prices the shortfall",
        in_window=[1, 0, 0],
        energy=4.0,
        duration=2.0,
        supply_price=[0.2, 0.2, 0.2],
        expected_cost=200.4,
        expected_outputs={
            "appliance_power": {"type": "power", "unit": "kW", "values": (2.0, 0.0, 0.0)},
            "element_power_balance": {"type": "shadow_price", "unit": "$/kWh", "values": (0.2, 0.2, 0.2)},
        },
    ),
]
