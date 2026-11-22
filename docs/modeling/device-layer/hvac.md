# Whole-house HVAC and room models

HVAC is a single electrical load connected to the switchboard.
Each room observes the same delivered electrical power and the same operating mode.
Rooms never create electrical sinks or independent zone commands.
Electrical demand is therefore counted exactly once, regardless of the number of rooms.

## Temperature dynamics

For loss rate `k` in 1/h, interval duration `dt` in hours, outdoor temperature `O`, electrical power `P` in kW, response `r` in K/kWh, and mode `m`:

```text
a = exp(-k * dt)
g = (1 - a) / k, or dt when k = 0
T[next] = a * T[now] + (1 - a) * O + r * m * g * P
```

This exact first-order discretization assumes constant outdoor temperature and power during each interval.
It is stable on coarse intervals, unlike a forward Euler approximation.
Each room has its own initial temperature, loss rate, response and comfort bands.
The HVAC model owns one externally selected mode: 1 heating, -1 cooling, 0 off.
Off forces shared power to zero; heating and cooling cannot occur simultaneously.
Mode changes update every room through reactive dependency tracking.

Two nonnegative slack variables per boundary measure degrees below and above the comfort band.
They are priced in degree-hours using interval durations; the terminal boundary uses the final interval duration as its reserve weight.
An already-warm room in heating mode remains feasible and recovers naturally when heating cannot help.
Conflicting rooms produce a priced compromise rather than fictitious independent control.

## Scope and limitations

Mode selection is an external policy input, not an optimized heating-to-cooling changeover schedule.
Room coefficients are explicit assumptions until calibrated against measured HVAC power and temperatures.
The model does not infer internal gains, sun exposure, door position, humidity, air distribution or inter-room heat exchange.
A constant outdoor observation is a persistence scenario, not a weather forecast; select a temperature forecast source when available.
Comfort deviations are K, not absolute C, and must not be offset-converted as Fahrenheit temperatures.
No climate or relay services are called by these elements.
The planned power is an average continuous relaxation and does not enforce compressor dwell times or thermostat tracking.
Existing independent safety controls remain responsible for actual equipment and pet protection.

## Configuration

Add one whole-house HVAC device, connected to the switchboard, then add rooms selecting that HVAC appliance.
Set mode from a numeric policy entity or explicit constant; select current room temperature entities and outdoor forecasts.
Comfort minimum and maximum can be entity-backed forecasts, including existing presence/night policy values.
Room references participate in normal rename and missing-dependency checks through the connection-target mechanism.
Removing the HVAC leaves a reported missing dependency rather than silently assigning rooms to a different appliance.
