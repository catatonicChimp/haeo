"""Configure forecast-only hot-water modeling in a shadow network."""

from typing import ClassVar

from custom_components.haeo.core.schema.elements import ElementType
from custom_components.haeo.flows.connected_flow import ConnectedElementSubentryFlow
from custom_components.haeo.flows.field_schema import SectionDefinition


class ThermalStoreSubentryFlowHandler(ConnectedElementSubentryFlow):
    """Configure thermal inputs without an appliance actuator selector."""

    element_type = ElementType.THERMAL_STORE
    sections: ClassVar[tuple[SectionDefinition, ...]] = (
        SectionDefinition(
            key="thermal",
            fields=(
                "initial_temperature",
                "target_temperature",
                "maximum_temperature",
                "capacity_per_degree",
                "cop",
                "loss_power",
                "draw_power",
                "max_power",
                "shortfall_price",
            ),
            collapsed=False,
        ),
    )
