# Experimental thermal store

This model is an offline hot-water feasibility prototype, not a user-configurable device or an appliance controller.
It reads an existing electrical connection, so battery discharge, grid imports and thermal storage participate in the same network solve.
It adds no electrical power variables and provides no external plugin API.

## State and units

Boundary energy `E` is thermal kWh above a fixed reference temperature `R`.
Thermal capacity `C` is kWh/K, so temperature is `R + E / C`.
For a well-mixed water approximation, capacity can be estimated from litres times density times specific heat, with joules converted to kWh.
The physical tank volume and effective capacity still require verification; the prototype tests use synthetic parameters.

For each interval of duration `dt` hours:

```text
E[next] = E[now] + P[electrical] * COP * dt - loss_power * dt - draw_energy
```

COP is a forecast coefficient, not a decision variable.
Standing loss is thermal kW; draw is prescribed thermal kWh per interval and is not multiplied by duration again.
The initial temperature fixes the first energy state.
Zero stored energy and the configured physical maximum are hard bounds.
Invalid physical telemetry needs explicit input validation before any future live integration.

## Readiness and cost

At each boundary, nonnegative thermal shortfall permits energy below a desired temperature.
Shortfall is priced per thermal kWh at that boundary, not as an hourly holding cost.
Use a final-boundary target and price to preserve terminal readiness.
Repeated targets price repeated misses, so their weights must be chosen intentionally when changing time resolution.
Starting above a comfort target does not require cooling.
Impossible physical energy balances still fail; this model does not manufacture heat to satisfy demand.

## Outputs and updates

The element exposes stored thermal energy and readiness shortfall as model outputs.
Its offline `temperatures()` method converts the solved boundary states to C.
Initial temperature, COP, loss, draw, targets and prices are reactive parameters.
Structural capacity, reference temperature and physical maximum require a rebuild.
Changing the number of intervals also requires a rebuild.
Capacity and physical temperature bounds are validated at construction.
Every constraint and cost validates finite, correctly sized reactive inputs before building expressions.
COP, interval durations and shortfall prices must be positive; loss and draw must be nonnegative.
Strictly positive shortfall prices make the reported slack minimize to the actual missed target.

## Limitations and next gate

This is a continuous average-power relaxation, not a guarantee that an on/off heat pump can execute the schedule.
It has no minimum run/off constraints, stratification, temperature-dependent draw, calibrated COP or hygiene verification.
The experimental device adapter supplies a configuration flow and forecast sensors for a separately configured shadow hub.
It is not installed in the live instance.
Readiness shortfall may reflect prescribed draw exceeding available heat; future demand modeling must distinguish unmet hot-water service from physically impossible extraction.

Before a control trial, validate inputs, add realistic PV/base-load scenarios, test parameter and horizon updates, and assess thermostat/run-request tracking.
Then decide whether native thermal elements or a supported external provider interface is the smaller maintainable HAEO change.

## Verified offline scenarios

Synthetic tests include fixed solar production and baseline demand with bounded grid exports.
Low export revenue favors heating with solar surplus; high export revenue favors exporting now and heating from cheaper imports later.
Other tests cover battery supply, variable-duration updates, COP updates, malformed reactive forecasts and terminal readiness.
These are controlled fixtures, not replayed household measurements or claims of bill savings.

A tracking counterexample needs 0.05 electrical kWh, or 3.75 minutes at 0.8 kW.
That continuous plan cannot be delivered as a single cycle if the equipment requires a hypothetical 10-minute minimum run.
The equipment's actual minimum run time is not yet established.
The next execution gate must compare a dwell-aware on/off realization against the thermal trajectory and physical maximum, rather than simply thresholding average power.
If adequate tracking cannot be achieved, the planner must represent discrete run decisions or reject the plan for automatic execution.
