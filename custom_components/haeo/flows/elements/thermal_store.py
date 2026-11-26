"""Configure two-stage hot-water modeling in a shadow network."""

from collections.abc import Mapping
from typing import ClassVar

from custom_components.haeo.core.schema.elements import ElementType
from custom_components.haeo.core.schema.elements.thermal_store import (
    CONF_HP_CEILING_TEMPERATURE,
    SECTION_ELEMENT,
    SECTION_HEAT_PUMP,
    SECTION_THERMAL,
)
from custom_components.haeo.flows.connected_flow import ConnectedElementSubentryFlow
from custom_components.haeo.flows.field_schema import SectionDefinition


class ThermalStoreSubentryFlowHandler(ConnectedElementSubentryFlow):
    """Configure two-stage thermal inputs without an appliance actuator selector."""

    element_type = ElementType.THERMAL_STORE
    sections: ClassVar[tuple[SectionDefinition, ...]] = (
        SectionDefinition(
            key=SECTION_THERMAL,
            fields=(
                "initial_temperature",
                "target_temperature",
                "maximum_temperature",
                "capacity_per_degree",
                "loss_power",
                "draw_power",
                "shortfall_price",
            ),
            collapsed=False,
        ),
        SectionDefinition(
            key=SECTION_HEAT_PUMP,
            fields=(
                CONF_HP_CEILING_TEMPERATURE,
                "hp_max_power",
                "hp_cop",
            ),
            collapsed=False,
        ),
        SectionDefinition(
            key=SECTION_ELEMENT,
            fields=(
                "element_max_power",
                "element_cop",
            ),
            collapsed=False,
        ),
    )

    def _validate_fields(self, user_input: Mapping[str, object], errors: dict[str, str]) -> None:
        """Reject a heat-pump ceiling that is above the physical maximum."""
        super()._validate_fields(user_input, errors)
        thermal = user_input.get(SECTION_THERMAL)
        heat_pump = user_input.get(SECTION_HEAT_PUMP)
        if not isinstance(thermal, dict) or not isinstance(heat_pump, dict):
            return
        maximum = thermal.get("maximum_temperature")
        ceiling = heat_pump.get(CONF_HP_CEILING_TEMPERATURE)
        if isinstance(maximum, (int, float)) and isinstance(ceiling, (int, float)) and ceiling > maximum:
            errors[SECTION_HEAT_PUMP] = "invalid_ceiling"
