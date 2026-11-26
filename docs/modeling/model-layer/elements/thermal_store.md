# Experimental thermal store

This model is an offline hot-water feasibility prototype, not a user-configurable device or an appliance controller.
It reads two existing electrical connections (heat pump and optional resistive element), so battery discharge, grid imports and thermal storage participate in the same network solve.
It adds no electrical power variables and provides no external plugin API.

## State and units

Boundary energy `E` is thermal kWh above a fixed reference temperature `R`.
Thermal capacity `C` is kWh/K, so temperature is `R + E / C`.
For a well-mixed water approximation, capacity can be estimated from litres times density times specific heat, with joules converted to kWh.
The physical tank volume and effective capacity still require verification; the prototype tests use synthetic parameters.

For each interval of duration `dt` hours:

```text
E[next] = E[now] + H * hp_cop * dt + R * element_cop * dt - loss_power * dt - draw_energy
```

`H` is heat-pump electrical power and `R` is resistive-element electrical power.
`hp_cop` and `element_cop` are forecast coefficients, not decision variables.
Standing loss is thermal kW; draw is prescribed thermal kWh per interval and is not multiplied by duration again.
The initial temperature fixes the first energy state.
Zero stored energy and the configured physical maximum are hard bounds.
Invalid physical telemetry needs explicit input validation before any future live integration.

## Two-stage heating and the heat-pump ceiling

The heat pump is allowed only while the period starts at or below a heat-pump ceiling temperature.
Above that ceiling only the resistive element may add heat.
The gating uses one binary variable per interval:

```text
C  = capacity_per_degree * (hp_ceiling_temperature - reference_temperature)
U  = capacity_per_degree * (maximum_temperature - hp_ceiling_temperature)
Emax = C + U
E[t] <= C + U * (1 - b[t])
H[t] <= hp_max_power[t] * b[t]
H[t] * hp_cop[t] * dt[t] <= C - E[t] + loss_power[t] * dt[t] + draw_energy[t] + U * (1 - b[t])
b[t] in {0, 1}
```

The cutoff is applied at the period start (`E[t]`), so a period that begins above the ceiling has `b[t] = 0` and only the element can heat.
When `hp_ceiling_temperature` equals `maximum_temperature`, `U = 0` and the model collapses to a pure LP with the heat pump always allowed.

## Readiness and cost

At each boundary, nonnegative thermal shortfall permits energy below a desired temperature.
Shortfall is priced per thermal kWh at that boundary, not as an hourly holding cost.
Use a final-boundary target and price to preserve terminal readiness.
Repeated targets price repeated misses, so their weights must be chosen intentionally when changing time resolution.
Starting above a comfort target does not require cooling.
Impossible physical energy balances still fail; this model does not manufacture heat to satisfy demand.

## Outputs and updates

The element exposes stored thermal energy, heat-pump power, element power and readiness shortfall as model outputs.
Its offline `temperatures()` method converts the solved boundary states to C.
Initial temperature, both COPs, both power limits, loss, draw, targets and prices are reactive parameters.
Structural capacity, reference temperature, physical maximum and heat-pump ceiling require a rebuild.
Changing the number of intervals also requires a rebuild.
Capacity and physical temperature bounds are validated at construction; the flow also rejects a ceiling above the physical maximum.
Every constraint and cost validates finite, correctly sized reactive inputs before building expressions.
COPs, interval durations and shortfall prices must be positive; loss and draw must be nonnegative; power limits must be nonnegative (zero disables a stage).
Strictly positive shortfall prices make the reported slack minimize to the actual missed target.

## v1.7 migration

A single-stage thermal store saved before v1.7 keeps its old `cop` as `heat_pump.hp_cop`, its old `max_power` as `heat_pump.hp_max_power`, and uses its old `maximum_temperature` as `heat_pump.hp_ceiling_temperature`.
The new `element` section is added with `element_max_power = 0` and `element_cop = 1`, so existing plans behave exactly as before until the element is deliberately enabled.

## Limitations and next gate

This is a continuous average-power relaxation, not a guarantee that on/off heating equipment can execute the schedule.
It has no minimum run/off constraints, stratification, temperature-dependent draw, calibrated COP or hygiene verification.
The experimental device adapter supplies a configuration flow and forecast sensors for a separately configured shadow hub.
It is not installed in the live instance.
Readiness shortfall may reflect prescribed draw exceeding available heat; future demand modeling must distinguish unmet hot-water service from physically impossible extraction.

Before a control trial, validate inputs, add realistic PV/base-load scenarios, test parameter and horizon updates, and assess thermostat/run-request tracking.
Then decide whether native thermal elements or a supported external provider interface is the smaller maintainable HAEO change.

## Verified offline scenarios

Synthetic tests include simultaneous heat-pump and element operation below the ceiling, heat-pump capping at the ceiling, element-only heating above the ceiling, free pre-charge into the upper band, loss/draw handling, variable-duration updates, COP and power-limit updates, malformed reactive forecasts, and terminal readiness.
Other tests cover battery supply, grid-export trade-offs and migration from the single-stage schema.
These are controlled fixtures, not replayed household measurements or claims of bill savings.

A tracking counterexample needs 0.05 electrical kWh, or 2.5 minutes at 0.8 kW with a COP of 3.
That continuous plan cannot be delivered as a single cycle if the equipment requires a hypothetical 10-minute minimum run.
The equipment's actual minimum run time is not yet established.
The next execution gate must compare a dwell-aware on/off realization against the thermal trajectory and physical maximum, rather than simply thresholding average power.
If adequate tracking cannot be achieved, the planner must represent discrete run decisions or reject the plan for automatic execution.
