# Appliance

An appliance is a load that runs once through a single unbroken cycle: a dishwasher, a washing machine, a tumble dryer.
You say how much energy one run takes and how long it lasts, give it the hours of the day it may run in, and HAEO picks the cheapest block of that length inside those hours.
An external switch or input boolean arms it, so a run only appears in the plan when you want one.

The plan is re-solved every 30 seconds and the appliance carries no memory between solves.
The run reports where it would start now, and moves if the prices or the forecasts change, so an automation should follow the planned start rather than assume the first answer stands.

For the mathematical details, see [Appliance modeling](../../modeling/model-layer/elements/appliance.md).

## Configuration

### Overview

An appliance element holds:

- **Armed** switch: the entity that says whether a run is wanted
- **Energy per run**: kWh one cycle takes
- **Run duration**: hours one cycle lasts
- **Allowed hours**: the earliest hour a run may start and the latest hour it must finish, in local time

### Name

Choose a descriptive, friendly name.
Home Assistant uses it for sensor names, so avoid symbols or abbreviations you would not want to see in the UI.

### Connection

Select the [endpoint](connection.md#connection-endpoint-selection) the appliance draws from, typically your main switchboard.
Its planned consumption adds to that endpoint's load, so the grid, battery, or solar that supplies the endpoint covers the run.

### Armed

Select the switch, input boolean, or other on/off entity that arms the appliance, or set a constant.

- **On**: the plan includes one run of the configured energy inside the allowed hours.
- **Off**: the plan draws nothing and the planned start reads unavailable.

Arming does not start anything by itself.
It only tells the optimizer that a run is wanted, and the sensors describe when that run would be cheapest.

### Energy per run

Enter the energy one cycle takes in kWh, such as `1.2` for an eco dishwasher program.
The default is `1.0` kWh.
The plan delivers the whole amount inside the planning horizon; anything the allowed hours cannot fit shows up as a priced shortfall in the optimization, not as a failed solve.

### Run duration

Enter how long one cycle takes in hours, such as `2.0`.
The default is `2.0` hours.
The plan uses the run as one contiguous block of this length, drawing at most its energy divided by its duration.

### Allowed hours

Enter two hours of the day in local time:

- **Earliest start**: the first hour a run may begin.
- **Latest finish**: the hour a run must be over by.

A period belongs to the window by the hour it starts at.
The defaults of `0` and `24` allow the whole day.

- **Same-day window**: when the earliest start is before the latest finish, such as `9` to `17`, the run fits between those hours.
- **Overnight window**: when the latest finish is earlier than the earliest start, such as `20` to `6`, the window wraps past midnight.
- **Equal bounds**: an earliest start equal to the latest finish allows the whole day, so `0` to `0` means any time.

A run's periods must all start inside the window and inside the planning horizon.
The last period may run past the latest-finish hour, because the window is read from each period's start hour.
A window shorter than the run duration leaves no room for the block, so the planned start reads unavailable and the power stays at zero.

## How the run is chosen

The optimizer plans a continuous relaxation: power may fill any allowed period, up to the run's energy over its duration.
That keeps the problem a linear program with no on/off decisions.
The element then picks the single block of the configured length that a device could actually run:

- Only starts whose every period begins inside the allowed hours are considered.
- The block is priced at the connected endpoint's marginal price for each period it covers, which is the grid's import price while the endpoint draws from the grid and its export price while the endpoint exports.
- The cheapest block wins, and the earliest start wins a tie.
- The plan is solved again with that block fixed, so the rest of the plan matches the run. A block the network cannot supply is skipped for the next cheapest one.

The planned power sensor reports only the committed block, so it steps from zero to the run's power and back to zero rather than following the relaxed plan.
If the endpoint reports no marginal price, every block costs the same and the earliest one that fits is shown.

## Input entities

Each field creates an input entity on the appliance's device.
Input entities appear with the `config` entity category, and their IDs combine the appliance's name with the entity's name.

| Input                          | Unit | Description                           |
| ------------------------------ | ---- | ------------------------------------- |
| `switch.{name}_armed`          | -    | Whether a run is wanted now           |
| `number.{name}_energy_per_run` | kWh  | Energy one cycle takes                |
| `number.{name}_run_duration`   | h    | Length of one cycle                   |
| `number.{name}_earliest_start` | h    | First hour of the day a run may start |
| `number.{name}_latest_finish`  | h    | Hour of the day a run must finish by  |

An armed field set to a constant, or to an entity whose state is on, counts as armed.

## Sensors created

The appliance element creates one device with the following sensors:

| Sensor                        | Unit | Description                                                                 |
| ----------------------------- | ---- | --------------------------------------------------------------------------- |
| `sensor.{name}_planned_power` | kW   | Planned power of the committed run in each period                           |
| `sensor.{name}_planned_start` | -    | Planned start of the committed run, unavailable when disarmed or infeasible |

The planned start is a timestamp sensor, so it reads as a date and time rather than a number.
It is unavailable while the appliance is disarmed or when no block of the run length fits the allowed hours, which is how the plan says "nothing to run".
The planned power forecast attribute carries the same committed block over the planning horizon.

## Next steps

<div class="grid cards" markdown>

- **Appliance formulation**

    ---

    Review the relaxation, the shortfall pricing, and how the committed block is chosen.

    [Appliance model](../../modeling/model-layer/elements/appliance.md)

</div>
