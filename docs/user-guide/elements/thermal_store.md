# Thermal store (shadow)

The experimental thermal store adds hot-water temperature dynamics to a HAEO network.
Use a new, separately named hub with Advanced mode enabled for shadow evaluation.
It exposes forecasts only and has no relay, climate or water-heater action configuration.
Do not connect its output sensors to appliance-control automations.

Configure the grid, solar, battery and uncontrolled house load as ordinary HAEO elements in that shadow hub.
Do not reuse whole-house consumption forecasts without subtracting any separately modeled appliances, or their demand will be counted twice.
Add a thermal store connected to the shadow switchboard.

## Thermal inputs

- Measured tank temperature: the live sensor, converted to C.
- Readiness temperature: a constant or forecast of desired boundary temperatures.
- Physical maximum: the equipment's verified maximum in C, not its comfort target.
- Effective thermal capacity: kWh/K; volume alone does not establish effective capacity.
- Standing heat loss: thermal kW.
- Expected hot-water draw: thermal kW, scaled by each interval's duration.
- Readiness shortfall price: positive currency per thermal kWh at each boundary.

## Heat pump inputs

- Heat pump ceiling temperature: the upper temperature at which the heat pump may run. A period starting above this temperature uses only the resistive element.
- Maximum heat pump power: kW of electrical input; set to 0 to disable the heat pump.
- Heat pump COP: a positive dimensionless ratio, not a percentage.

## Resistive element inputs

- Maximum element power: kW of electrical input; set to 0 to disable the element.
- Element COP: a positive dimensionless ratio (typically 1.0 for direct resistance heating).

No volume, COP, draw or hygiene behavior is inferred from a device name.
Enter explicit research assumptions and validate them against recorded behavior.
An unreachable readiness target produces a visible shortfall; conflicting physical limits fail the solve.

## Sensors

The element exposes planned heat-pump power, planned element power, combined planned heating power, predicted tank temperature and readiness shortfall with forecast attributes.
The hub's existing optimization status reports failures.
These are counterfactual optimized forecasts, not predictions of actual tank behavior while EMHASS remains in charge.
Compare actual behavior only where actual heating matches the modeled input, or replay actual power separately.

## Installation and rollback

The fork retains the `haeo` domain and replaces installed HAEO code, rather than installing alongside it.
Back up the installed component before replacing it and retain the original version for rollback.
Existing hubs must remain unchanged; create only a new shadow hub through the normal configuration flow.
HACS metadata expects a release asset named `haeo.zip`; a fork URL alone does not publish the experimental code or create that asset.
Publishing requires authenticated GitHub access and a tested versioned release.

## Next steps

<div class="grid cards" markdown>

- **Thermal formulation**

    ---

    Review the continuous-power approximation and its limitations.

    [Thermal model](../../modeling/model-layer/elements/thermal_store.md)

</div>
