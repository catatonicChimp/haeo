# Room

A room contributes one temperature prediction and a soft comfort objective to a shared HVAC appliance.
Rooms are observations of an unzoned system, not independently controllable zones.
Any number of rooms can reference one HVAC element without duplicating electrical demand.

## Configuration

- Connection: the whole-house HVAC appliance this room responds to.
- Measured temperature: the room sensor used as the initial state.
- Outdoor temperature: an ambient forecast or observation.
  A current observation is a persistence assumption, not a weather forecast.
- Comfort minimum and maximum: boundaries in degrees Celsius.
  These may be constants or forecast sensors carrying day, night or presence policy.
- Heat loss rate: first-order loss in 1/h.
- HVAC response: temperature change in K per electrical kWh delivered to the shared appliance.
- Comfort price: cost per Kelvin-hour outside the band.

Comfort boundaries are soft.
A room above its maximum while the system is heating does not make the optimization infeasible; it reports a hot shortfall and recovers through passive loss.
Conflicting rooms are resolved by priced compromise, not independent heating and cooling.

## Sensors

The room creates predicted temperature, cold comfort shortfall and hot comfort shortfall sensors, each with a forecast.
Shortfalls are in Kelvin, not Celsius, and represent distance outside the band.

## Coefficients

Loss rate and response are explicit calibration inputs.
They are not inferred from a room name, area or device.
Start with conservative estimates and refine them against periods where the measured HVAC power and room temperatures are known.
The model does not include solar gains, internal gains, humidity, door state, air distribution or inter-room heat exchange.

## Next steps

<div class="grid cards" markdown>

-   **Shared appliance**

    ---

    Review the electrical load and mode the room responds to.

    [:material-arrow-right: Whole-house HVAC](hvac.md)

</div>
