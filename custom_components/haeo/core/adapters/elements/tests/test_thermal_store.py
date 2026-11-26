"""Exercise a configured thermal device through HAEO's normal build lifecycle."""

import numpy as np
import pytest

from custom_components.haeo.core.adapters.elements.thermal_store import adapter
from custom_components.haeo.core.adapters.network_builder import build_element_updaters, build_network
from custom_components.haeo.core.schema import as_connection_target
from custom_components.haeo.core.schema.elements import ElementConfigData, ElementType
from custom_components.haeo.core.schema.elements.thermal_store import ThermalStoreConfigData


def test_configured_thermal_store_build_update_and_outputs() -> None:
    """Use compiled electrical tags and tracked inputs, not a private live network."""
    tank = ThermalStoreConfigData(
        name="tank",
        element_type=ElementType.THERMAL_STORE,
        connection=as_connection_target("bus"),
        thermal={
            "initial_temperature": 50.0,
            "target_temperature": np.array([50.0, 50.0, 60.0]),
            "maximum_temperature": 75.0,
            "capacity_per_degree": 0.1,
            "loss_power": np.zeros(2),
            "draw_power": np.zeros(2),
            "shortfall_price": np.array([10.0, 10.0, 10.0]),
        },
        heat_pump={
            "hp_ceiling_temperature": 75.0,
            "hp_max_power": np.ones(2),
            "hp_cop": np.full(2, 2.0),
        },
        element={
            "element_max_power": np.zeros(2),
            "element_cop": np.ones(2),
        },
    )
    participants: dict[str, ElementConfigData] = {
        "bus": {"element_type": ElementType.JUNCTION, "name": "bus"},
        "grid": {
            "element_type": ElementType.GRID,
            "name": "grid",
            "connection": as_connection_target("bus"),
            "pricing": {"price_source_target": np.array([0.1, 0.3]), "price_target_source": np.zeros(2)},
            "power_limits": {},
        },
        "tank": tank,
    }
    network = build_network("shadow", participants, [3600.0, 3600.0])
    assert network.optimize() == pytest.approx(0.05)
    outputs = {name: element.outputs() for name, element in network.elements.items()}
    result = adapter.outputs("tank", outputs, config=tank)
    assert result[ElementType.THERMAL_STORE]["thermal_store_temperature"].values[-1] == pytest.approx(60.0)
    assert result[ElementType.THERMAL_STORE]["thermal_store_power_element"].values == pytest.approx((0.0, 0.0))
    updater = build_element_updaters(network, participants)["tank"]
    tank["thermal"]["initial_temperature"] = 55.0
    updater(tank)
    assert network.optimize() == pytest.approx(0.025)
