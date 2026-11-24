# Whole-house HVAC

The HVAC element represents one ducted or unzoned air conditioner as a single electrical load.
It creates one connection and one consumption forecast, regardless of how many rooms observe it.
Rooms attach to the HVAC element and cannot create separate electrical loads or zone commands.

## Configuration

- Connection: the switchboard or bus that supplies the appliance.
- Operating mode: a numeric input where 1 means heating, -1 cooling and 0 off.
    Use a template helper derived from your climate policy when no numeric mode already exists.
- Maximum electrical power: the appliance's verified maximum input, in kW.

Mode is a single value for the whole optimization horizon.
The model does not schedule a heating-to-cooling changeover; choose the mode from policy or observation.
When mode is off, planned power is forced to zero.
Heating and cooling cannot occur simultaneously.

## Sensors

The element creates a planned HVAC power sensor with a forecast attribute.
It is a counterfactual average power for the shared appliance, not a command and not a thermostat signal.
It does not enforce compressor minimum run times, defrost cycles or thermostat deadbands.
Existing HVAC controls and safety automations remain authoritative.

## Rooms

Add one room per measured space that should influence comfort.
Each room selects this HVAC element as its connection.
Room inputs and their interpretation are described in [Room](room.md).

## Next steps

<div class="grid cards" markdown>

- :material-home-thermometer:{ .lg .middle } **Configure rooms**

    ---

    Attach temperature sensors and comfort bands to the shared appliance.

    [:material-arrow-right: Room setup](room.md)

- **Thermal formulation**

    ---

    Review room dynamics and comfort handling.

    [Whole-house HVAC and room models](../../modeling/device-layer/hvac.md)

</div>
