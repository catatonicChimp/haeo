# Appliance

An appliance is an armed sink that must receive one run's energy as a single unbroken cycle inside the hours of the day it is allowed to run in.
This model is a continuous relaxation: power may fill any allowed period, so the optimization stays a linear program, and the adapter then commits one contiguous block of the configured length.
The [device layer](../../device-layer/index.md) wiring, the config flow, and the sensors are described on the [appliance page](../../../user-guide/elements/appliance.md).

## Parameters

| Parameter       | Symbol     | Unit | Meaning                                                      |
| --------------- | ---------- | ---- | ------------------------------------------------------------ |
| Run energy      | $E$        | kWh  | Energy one cycle must receive                                |
| Run duration    | $D$        | h    | Length of one cycle                                          |
| Armed           | $a$        | -    | 1 while a run is wanted, 0 otherwise                         |
| Window mask     | $w_t$      | -    | 1 when period $t$ starts inside the allowed hours, 0 outside |
| Period duration | $\Delta_t$ | h    | Length of period $t$                                         |

The window mask is derived from the earliest-start and latest-finish hours of the day.
A period belongs to the window by the hour it starts at, in the home's local zone.
A latest finish earlier than the earliest start wraps past midnight, and equal bounds cover the whole day.

## Variables

The element adds two decision variables and no integer variables:

- $p_t \ge 0$: electrical power drawn in period $t$, in kW
- $s \ge 0$: energy the window could not deliver, in kWh, one value for the horizon

## Constraints

Power is bounded by the run's average power, and is zero outside the allowed hours and while disarmed:

$$
0 \le p_t \le \frac{E}{D} \, w_t \, a
$$

The run's energy is delivered inside the horizon, or the miss is reported as shortfall:

$$
\sum_t p_t \Delta_t + s = a E
$$

The shortfall equality is soft rather than enforced, so a window that physically cannot fit the run leaves the optimization feasible and reports how much of the run is missing.
It also keeps the element a plain linear program.

When the coordinator has committed a run, it pins the block it chose and the second solve fixes the power to it in every period:

$$
p_t = p_t^{\text{pin}}
$$

The pin is released once that solve's outputs are read, so the next optimization starts from the relaxation again.

## Cost

Each kWh the window cannot deliver is priced at a fixed shortfall price:

$$
\text{Cost} = P_{\text{shortfall}} \, s
$$

$P_{\text{shortfall}}$ is high enough that an armed appliance runs whenever the window allows it, and finite so an impossible run never fails the solve.

## Outputs

The model exposes:

- `appliance_power`: the relaxed power $p_t$ in each period (kW)
- `element_power_balance`: the marginal cost of drawing one more kWh at this element, in currency per kWh

`appliance_power` is the relaxation, not the committed run, until the coordinator pins a run onto $p_t$.
The element also consumes power through the network balance, so the run is supplied by whatever the connected endpoint draws from the grid, battery, or solar.

## Committed run

The optimizer may spread the run across the whole window, which an actuator cannot follow.
The adapter therefore chooses the run an actual device would execute:

1. Each candidate start is a period whose start hour is inside the window, and every period the block covers must start inside the window too.
    The block may end partway through its last period, and because the mask is read from start hours, that period can extend past the latest-finish hour.
2. Each candidate is priced at the connected endpoint's `element_power_balance` value in every period it covers, in currency per kWh.
    That dual is the marginal value of one more kWh at the endpoint, so it is the grid's import price while the endpoint draws from the grid and its export price while the endpoint exports.
3. The cheapest candidate wins. A tie goes to the earliest start.

When the endpoint reports no price, such as an unpriced node, every candidate costs the same and the earliest that fits is committed.

Only the committed block appears on the planned power sensor and its forecast attribute; the relaxed $p_t$ stays inside the model.
The coordinator then pins the chosen block on $p_t$ and solves the network again, so every other output — grid import, battery flow, and prices — describes the plan with the run in place.
A block the network cannot supply is skipped for the next cheapest one, and when no block can be supplied the plan stays as the relaxed solve reported it and the appliance reports no run.
Commitments are chosen one appliance at a time, each priced from the relaxed solve, and nothing carries over between optimizations, so the reported block can move when prices or forecasts change.

A run that is disarmed, or whose window cannot fit the block, commits no power and reports an unavailable planned start.
