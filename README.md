# Janitza UMG 96-EL Home Assistant add-on

This add-on polls a Janitza UMG 96-EL over Modbus TCP and publishes its
measurements to an MQTT broker. Home Assistant MQTT Discovery automatically
creates one device with 27 sensors.

## Requirements

- Home Assistant with support for local add-ons.
- A configured MQTT integration and reachable MQTT broker.
- Network access from the add-on to both the meter and broker.
- Modbus TCP enabled on the meter.

## Install

1. In Home Assistant, open **Settings → Add-ons → Add-on Store** and select
   **⋮ → Repositories**.
2. Add `https://github.com/warsiengin/janitza_umg96el` and save.
3. Find **Janitza UMG 96-EL** in the store and install it.
4. Open its **Configuration** tab, set the MQTT password, and confirm the
   meter and broker settings.
5. Save, start the app, and check its log for connection or polling errors.

Alternatively, copy the `janitza_umg96el` directory into Home Assistant's local
apps directory, for example `/addons/janitza_umg96el`, then reload local apps
in the store.

The broker must permit the add-on to publish under the configured topic prefix
and `homeassistant/sensor/` discovery topics. MQTT over TLS is not currently
configured by this add-on.

## Configuration

| Option | Default | Description |
| --- | --- | --- |
| `host` | `192.168.1.110` | Meter IP address or hostname |
| `port` | `502` | Meter's Modbus TCP port |
| `unit_id` | `1` | Modbus unit/slave ID |
| `mqtt_host` | `192.168.100.15` | MQTT broker IP address or hostname |
| `mqtt_port` | `1883` | MQTT broker port |
| `mqtt_username` | `warsiengin` | MQTT username; clear if the broker does not require authentication |
| `mqtt_password` | empty | MQTT password; set this in the add-on configuration |
| `mqtt_topic_prefix` | `janitza_umg96el` | Prefix for state and availability topics |
| `scan_interval` | `30` | Delay after each polling pass in seconds (5–3600) |

Credentials are supplied through the add-on settings and should not be added to
the source files.

## MQTT and Home Assistant

For the default prefix, the add-on publishes:

- State values to `janitza_umg96el/<sensor_key>/state`.
- Availability to `janitza_umg96el/status` (`online` or `offline`).
- Retained Discovery config to
  `homeassistant/sensor/janitza_umg96el/<sensor_key>/config`.

Discovery and state messages are retained so Home Assistant can recover the
entities and their latest readings after reconnecting. The device appears as
**Janitza UMG 96-EL**. Sensor icons are included in Discovery: sine-wave icons
for voltage, voltage THD, and grid frequency; an angle icon for power factor;
`S`/`Q` icons for apparent/reactive energy; and an AC-current icon for current
THD.

## Measurements

Every value is read as an IEEE-754 32-bit float from two consecutive holding
registers. Register addresses below are the addresses supplied for this meter.
The decoder uses big-endian byte and word order.

| Measurement | Register | Unit |
| --- | ---: | --- |
| Voltage L1-N | 19000 | V |
| Voltage L2-N | 19002 | V |
| Voltage L3-N | 19004 | V |
| Voltage L1-L2 | 19006 | V |
| Voltage L2-L3 | 19008 | V |
| Voltage L3-L1 | 19010 | V |
| Current I L1 | 19012 | A |
| Current I L2 | 19014 | A |
| Current I L3 | 19016 | A |
| Neutral return current | 19018 | A |
| Total real power | 19026 | W |
| Total apparent power | 19034 | VA |
| Fundamental reactive power | 19042 | var |
| Power factor L1 | 19044 | — |
| Power factor L2 | 19046 | — |
| Power factor L3 | 19048 | — |
| Grid frequency | 19050 | Hz |
| Real energy consumed | 19068 | Wh |
| Real energy delivered | 19076 | Wh |
| Apparent energy | 19084 | VAh |
| Fundamental reactive energy | 19092 | varh |
| Voltage THD L1-N | 19110 | % |
| Voltage THD L2-N | 19112 | % |
| Voltage THD L3-N | 19114 | % |
| Current THD L1 | 19116 | % |
| Current THD L2 | 19118 | % |
| Current THD L3 | 19120 | % |

Energy accumulators use the `total_increasing` state class. Other values are
published as measurements.

## Troubleshooting

- **MQTT connection/authentication errors:** confirm broker address, port,
  credentials, and ACL permissions. The broker must allow Discovery publishing.
- **Meter connection errors:** confirm Modbus TCP is enabled, the IP/port are
  reachable from Home Assistant, and the unit ID matches the meter.
- **Unavailable sensors:** check add-on logs and confirm the MQTT integration is
  connected to the same broker.
- **Unexpected values:** verify the meter's register map and float byte/word
  order. The implementation expects the supplied register addresses and
  big-endian 32-bit floats.
- **Entities do not appear:** confirm MQTT Discovery is enabled in Home
  Assistant and that retained configs exist under the `homeassistant/sensor/`
  topic.

## Development

The add-on image is built from `janitza_umg96el/Dockerfile`. Python package
versions are pinned in `janitza_umg96el/requirements.txt`. The polling and
Discovery implementation is in `janitza_umg96el/app.py`.
