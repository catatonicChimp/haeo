"""Normal builder and reactive lifecycle for unzoned room optimization."""

import numpy as np
import pytest

from custom_components.haeo.core.adapters.network_builder import build_element_updaters, build_network
from custom_components.haeo.core.schema import as_connection_target
from custom_components.haeo.core.schema.elements import ElementConfigData, ElementType
from custom_components.haeo.core.schema.elements.room import RoomConfigData


def test_joint_network_with_shared_hvac_and_two_rooms() -> None:
    """The ordinary builder respects dependency order and charges electrical use once."""
    rooms: list[RoomConfigData] = [
        {
            "name": name,
            "element_type": ElementType.ROOM,
            "connection": as_connection_target("AC"),
            "room": {
                "initial_temperature": temp,
                "outdoor_temperature": np.full(2, 10.0),
                "minimum_temperature": np.full(3, 18.0),
                "maximum_temperature": np.full(3, 25.0),
                "loss_rate": 0.03,
                "response": 0.5,
                "comfort_price": 5.0,
            },
        }
        for name, temp in (("bedroom", 17.0), ("living", 20.0))
    ]
    participants: dict[str, ElementConfigData] = {
        "bus": {"name": "bus", "element_type": ElementType.JUNCTION},
        "grid": {
            "name": "grid",
            "element_type": ElementType.GRID,
            "connection": as_connection_target("bus"),
            "pricing": {"price_source_target": np.array([0.1, 0.3]), "price_target_source": np.zeros(2)},
            "power_limits": {},
        },
        "AC": {
            "name": "AC",
            "element_type": ElementType.HVAC,
            "connection": as_connection_target("bus"),
            "hvac": {"mode": 1.0, "max_power": np.full(2, 4.5)},
        },
        **{r["name"]: r for r in rooms},
    }
    network = build_network("home", participants, [3600.0, 3600.0])
    assert network.optimize() > 0
    assert len([n for n in network.elements if n.endswith(":connection")]) == 1
    outputs = network.elements["bedroom"].outputs()
    assert outputs["room_temperature"].values[-1] >= 18.0 - 1e-6
    updater = build_element_updaters(network, participants)["bedroom"]
    rooms[0]["room"]["initial_temperature"] = 20.0
    updater(rooms[0])
    network.optimize()
    assert network.elements["bedroom"].outputs()["room_temperature"].values[0] == pytest.approx(20.0)
