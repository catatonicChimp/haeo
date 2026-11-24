"""Appliance element configuration flows."""

from typing import ClassVar

from custom_components.haeo.core.schema.elements.appliance import (
    CONF_ARMED,
    CONF_DURATION,
    CONF_EARLIEST_START,
    CONF_ENERGY,
    CONF_LATEST_FINISH,
    ELEMENT_TYPE,
    SECTION_SCHEDULE,
    SECTION_WINDOW,
)
from custom_components.haeo.flows.connected_flow import ConnectedElementSubentryFlow
from custom_components.haeo.flows.field_schema import SectionDefinition


class ApplianceSubentryFlowHandler(ConnectedElementSubentryFlow):
    """Handle appliance element configuration flows."""

    element_type = ELEMENT_TYPE
    sections: ClassVar[tuple[SectionDefinition, ...]] = (
        SectionDefinition(
            key=SECTION_SCHEDULE,
            fields=(CONF_ARMED, CONF_ENERGY, CONF_DURATION),
            collapsed=False,
        ),
        SectionDefinition(
            key=SECTION_WINDOW,
            fields=(CONF_EARLIEST_START, CONF_LATEST_FINISH),
            collapsed=False,
        ),
    )
