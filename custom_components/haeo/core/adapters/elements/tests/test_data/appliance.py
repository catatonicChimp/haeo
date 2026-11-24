"""Appliance adapter fixtures with independently specified expected mappings."""

from datetime import UTC, datetime, timedelta

import numpy as np

from custom_components.haeo.core.model import OutputData, OutputType
from custom_components.haeo.core.schema import as_connection_target
from custom_components.haeo.core.schema.elements import ElementType
from custom_components.haeo.core.schema.elements.appliance import ApplianceConfigData

from . import CreateCase, OutputsCase

# A run of one kWh over two hours draws half a kilowatt
ENERGY = 1.0
DURATION = 2.0
POWER = ENERGY / DURATION

# Four one-hour periods, with the run allowed from 01:00 onward
WINDOW = np.array([0.0, 1.0, 1.0, 1.0])
PERIODS = np.ones(4)

START = datetime(2026, 1, 1, tzinfo=UTC)
FORECAST_TIMES = tuple(START + timedelta(hours=hour) for hour in range(5))


def _data(*, armed: bool = True) -> ApplianceConfigData:
    return ApplianceConfigData(
        name="dishwasher",
        element_type=ElementType.APPLIANCE,
        connection=as_connection_target("bus"),
        schedule={"armed": armed, "energy": ENERGY, "duration": DURATION},
        window={"earliest_start": 1.0, "latest_finish": 4.0, "in_window": WINDOW},
    )


DATA = _data()
DISARMED_DATA = _data(armed=False)

CREATE_CASES: list[CreateCase] = [
    {
        "description": "Appliance draws from its node and carries its run's energy and window",
        "data": DATA,
        "model": [
            {
                "element_type": "appliance",
                "name": "dishwasher",
                "is_source": False,
                "is_sink": True,
                "in_window": WINDOW,
                "energy": ENERGY,
                "duration": DURATION,
                "armed": True,
            },
            {
                "element_type": "connection",
                "name": "dishwasher:connection",
                "source": "bus",
                "target": "dishwasher",
            },
        ],
    }
]

OUTPUTS_CASES: list[OutputsCase] = [
    {
        "description": "The cheapest fitting block wins over an equally sized earlier one",
        "data": DATA,
        "periods": PERIODS,
        "model_outputs": {
            "dishwasher": {
                "appliance_power": OutputData(type=OutputType.POWER, unit="kW", values=(0.0, 0.25, 0.25, 0.0)),
            },
            "bus": {
                "element_power_balance": OutputData(
                    type=OutputType.SHADOW_PRICE, unit="$/kWh", values=(0.0, 0.4, 0.1, 0.3)
                )
            },
        },
        "forecast_times": FORECAST_TIMES,
        "outputs": {
            ElementType.APPLIANCE: {
                "appliance_power": OutputData(
                    type=OutputType.POWER, unit="kW", values=(0.0, 0.0, POWER, POWER), direction="-"
                ),
                "appliance_planned_start": OutputData(
                    type=OutputType.TIMESTAMP,
                    unit=None,
                    values=(FORECAST_TIMES[2],),
                    state=FORECAST_TIMES[2],
                ),
            }
        },
    },
    {
        "description": "Without a node price the earliest fitting block wins",
        "data": DATA,
        "periods": PERIODS,
        "model_outputs": {
            "dishwasher": {
                "appliance_power": OutputData(type=OutputType.POWER, unit="kW", values=(0.0, 0.25, 0.25, 0.25)),
            },
        },
        "forecast_times": FORECAST_TIMES,
        "outputs": {
            ElementType.APPLIANCE: {
                "appliance_power": OutputData(
                    type=OutputType.POWER, unit="kW", values=(0.0, POWER, POWER, 0.0), direction="-"
                ),
                "appliance_planned_start": OutputData(
                    type=OutputType.TIMESTAMP,
                    unit=None,
                    values=(FORECAST_TIMES[1],),
                    state=FORECAST_TIMES[1],
                ),
            }
        },
    },
    {
        "description": "A disarmed appliance commits no power and has no planned start",
        "data": DISARMED_DATA,
        "periods": PERIODS,
        "model_outputs": {
            "dishwasher": {
                "appliance_power": OutputData(type=OutputType.POWER, unit="kW", values=(0.0, 0.0, 0.0, 0.0)),
            },
            "bus": {
                "element_power_balance": OutputData(
                    type=OutputType.SHADOW_PRICE, unit="$/kWh", values=(0.0, 0.4, 0.1, 0.3)
                )
            },
        },
        "forecast_times": FORECAST_TIMES,
        "outputs": {
            ElementType.APPLIANCE: {
                "appliance_power": OutputData(
                    type=OutputType.POWER, unit="kW", values=(0.0, 0.0, 0.0, 0.0), direction="-"
                ),
                "appliance_planned_start": OutputData(
                    type=OutputType.TIMESTAMP,
                    unit=None,
                    values=(),
                    state=None,
                    available=False,
                ),
            }
        },
    },
    {
        "description": "A run that cannot fit its window commits no power and has no planned start",
        "data": ApplianceConfigData(
            name="dishwasher",
            element_type=ElementType.APPLIANCE,
            connection=as_connection_target("bus"),
            schedule={"armed": True, "energy": ENERGY, "duration": 4.0},
            window={"earliest_start": 1.0, "latest_finish": 3.0, "in_window": np.array([0.0, 1.0, 1.0, 0.0])},
        ),
        "periods": PERIODS,
        "model_outputs": {
            "dishwasher": {
                "appliance_power": OutputData(type=OutputType.POWER, unit="kW", values=(0.0, 0.5, 0.0, 0.0)),
            },
        },
        "forecast_times": FORECAST_TIMES,
        "outputs": {
            ElementType.APPLIANCE: {
                "appliance_power": OutputData(
                    type=OutputType.POWER, unit="kW", values=(0.0, 0.0, 0.0, 0.0), direction="-"
                ),
                "appliance_planned_start": OutputData(
                    type=OutputType.TIMESTAMP,
                    unit=None,
                    values=(),
                    state=None,
                    available=False,
                ),
            }
        },
    },
]
