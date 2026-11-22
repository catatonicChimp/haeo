"""Configure a shared whole-house HVAC electrical actuator model."""

from typing import ClassVar

from custom_components.haeo.core.schema.elements import ElementType
from custom_components.haeo.flows.connected_flow import ConnectedElementSubentryFlow
from custom_components.haeo.flows.field_schema import SectionDefinition


class HvacSubentryFlowHandler(ConnectedElementSubentryFlow):
    """One electrical appliance with an externally selected heating/cooling mode."""

    element_type = ElementType.HVAC
    sections: ClassVar[tuple[SectionDefinition, ...]] = (
        SectionDefinition(key="hvac", fields=("mode", "max_power"), collapsed=False),
    )
