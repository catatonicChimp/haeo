"""Unzoned HVAC room regressions using the actual network solver."""

import numpy as np
import pytest

from custom_components.haeo.core.model import Network
from custom_components.haeo.core.model.elements.hvac import Hvac
from custom_components.haeo.core.model.elements.room import Room


def network_with_room(mode: float, initial: float = 25.1) -> tuple[Network, Hvac, Room]:
    """Build one unzoned actuator and a warm room with soft comfort."""
    network = Network(name="house", periods=np.ones(2))
    network.add({"element_type": "node", "name": "grid", "is_source": True, "is_sink": False})
    network.add({"element_type": "node", "name": "ac", "is_source": False, "is_sink": True})
    network.add(
        {
            "element_type": "connection",
            "name": "power",
            "source": "grid",
            "target": "ac",
            "tags": {1},
            "segments": {
                "limit": {"segment_type": "power_limit", "max_power": 2.0},
                "price": {"segment_type": "pricing", "price": 0.2},
            },
        }
    )
    hvac = network.add({"element_type": "hvac", "name": "hvac", "connection": "power", "mode": mode})
    room = network.add(
        {
            "element_type": "room",
            "name": "bedroom",
            "hvac": "hvac",
            "initial_temperature": initial,
            "outdoor_temperature": np.full(2, 20.0),
            "minimum_temperature": np.full(3, 18.0),
            "maximum_temperature": np.full(3, 25.0),
            "loss_rate": 0.01,
            "response": 1.0,
            "comfort_price": 10.0,
        }
    )
    return network, hvac, room


def test_heating_already_above_ceiling_remains_feasible() -> None:
    """Regression: an initially warm room coasts instead of breaking the solve."""
    network, _, room = network_with_room(1)
    network.optimize()
    temperatures = room.outputs()["room_temperature"].values
    assert temperatures[1] == pytest.approx(20 + 5.1 * np.exp(-0.01))
    assert temperatures[2] == pytest.approx(20 + 5.1 * np.exp(-0.02))
    assert room.outputs()["room_hot_shortfall"].values[0] == pytest.approx(0.1)


def test_cooling_and_reactive_mode_change() -> None:
    """The same shared actuator can cool, then become idle without stale dynamics."""
    network, hvac, room = network_with_room(-1, 28.0)
    network.optimize()
    cooled = room.outputs()["room_temperature"].values[-1]
    hvac.mode = 0
    network.optimize()
    assert room.outputs()["room_temperature"].values[-1] > cooled


def test_conflicting_rooms_share_one_power_input() -> None:
    """A warm and cold room cannot be independently heated or cooled."""
    network, _, warm = network_with_room(1, 26.0)
    cold = network.add(
        {
            "element_type": "room",
            "name": "living",
            "hvac": "hvac",
            "initial_temperature": 15.0,
            "outdoor_temperature": np.full(2, 20.0),
            "minimum_temperature": np.full(3, 18.0),
            "maximum_temperature": np.full(3, 25.0),
            "loss_rate": 0.01,
            "response": 0.5,
            "comfort_price": 30.0,
        }
    )
    network.optimize()
    assert cold.outputs()["room_temperature"].values[-1] > 15.0
    assert warm.outputs()["room_temperature"].values[-1] > 26.0
    assert warm.outputs()["room_hot_shortfall"].values[-1] > 0
    assert len([e for e in network.elements.values() if isinstance(e, Hvac)]) == 1


def test_variable_interval_passive_decay() -> None:
    """Exact decay remains stable on coarse intervals and duration updates."""
    network, _, room = network_with_room(0)
    network.update_periods(np.array([0.25, 1.75]))
    network.optimize()
    assert room.outputs()["room_temperature"].values[-1] == pytest.approx(20 + 5.1 * np.exp(-0.02))
