"""Temperature input conversion protects thermal forecasts from unit confusion."""

import pytest

from custom_components.haeo.core.data.util.field_units import to_field_unit
from custom_components.haeo.core.model.const import OutputType


@pytest.mark.parametrize(("value", "unit", "expected"), [(140.0, "°F", 60.0), (60.0, "°C", 60.0), (-4.0, "°F", -20.0)])
def test_temperature_converts_to_celsius(value: float, unit: str, expected: float) -> None:
    """Convert absolute temperatures with offset, preserving subzero readings."""
    assert to_field_unit(value, unit, OutputType.TEMPERATURE) == pytest.approx(expected)


def test_temperature_rejects_power_units() -> None:
    """A power sensor is not accepted as a temperature source."""
    assert to_field_unit(60.0, "kW", OutputType.TEMPERATURE) is None
