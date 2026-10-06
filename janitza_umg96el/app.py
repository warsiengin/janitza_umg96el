"""Poll Janitza UMG 96-EL Modbus registers and publish Home Assistant MQTT sensors.

At runtime, Home Assistant supplies add-on configuration at
``/data/options.json``. The sensor map below uses the meter's documented
register addresses and expects each value as a big-endian IEEE-754 float
spanning two holding registers.
"""

import json
import logging
import math
import signal
import struct
import time

import paho.mqtt.client as mqtt
from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusException


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
LOGGER = logging.getLogger("janitza_umg96el")
RUNNING = True
DEVICE_ID = "janitza_umg96el"

# Each address points to a 32-bit float stored across two holding registers.
SENSORS = [
    {"key": "voltage_l1_n", "name": "Voltage L1-N", "address": 19000, "unit": "V", "device_class": "voltage", "icon": "mdi:sine-wave"},
    {"key": "voltage_l2_n", "name": "Voltage L2-N", "address": 19002, "unit": "V", "device_class": "voltage", "icon": "mdi:sine-wave"},
    {"key": "voltage_l3_n", "name": "Voltage L3-N", "address": 19004, "unit": "V", "device_class": "voltage", "icon": "mdi:sine-wave"},
    {"key": "voltage_l1_l2", "name": "Voltage L1-L2", "address": 19006, "unit": "V", "device_class": "voltage", "icon": "mdi:sine-wave"},
    {"key": "voltage_l2_l3", "name": "Voltage L2-L3", "address": 19008, "unit": "V", "device_class": "voltage", "icon": "mdi:sine-wave"},
    {"key": "voltage_l3_l1", "name": "Voltage L3-L1", "address": 19010, "unit": "V", "device_class": "voltage", "icon": "mdi:sine-wave"},
    {"key": "current_l1", "name": "Current I L1", "address": 19012, "unit": "A", "device_class": "current"},
    {"key": "current_l2", "name": "Current I L2", "address": 19014, "unit": "A", "device_class": "current"},
    {"key": "current_l3", "name": "Current I L3", "address": 19016, "unit": "A", "device_class": "current"},
    {"key": "current_neutral", "name": "Neutral return current", "address": 19018, "unit": "A", "device_class": "current"},
    {"key": "frequency", "name": "Grid frequency", "address": 19050, "unit": "Hz", "device_class": "frequency", "icon": "mdi:sine-wave"},
    {"key": "active_power", "name": "Total real power", "address": 19026, "unit": "kW", "scale": 0.001, "device_class": "power"},
    {"key": "apparent_power", "name": "Total apparent power", "address": 19034, "unit": "VA", "device_class": "apparent_power"},
    {"key": "reactive_power", "name": "Fundamental reactive power", "address": 19042, "unit": "var", "device_class": "reactive_power"},
    {"key": "power_factor_l1", "name": "Power factor L1", "address": 19044, "icon": "mdi:angle-acute"},
    {"key": "power_factor_l2", "name": "Power factor L2", "address": 19046, "icon": "mdi:angle-acute"},
    {"key": "power_factor_l3", "name": "Power factor L3", "address": 19048, "icon": "mdi:angle-acute"},
    {
        "key": "real_energy_consumed",
        "name": "Real energy consumed",
        "address": 19068,
        "unit": "kWh",
        "scale": 0.001,
        "device_class": "energy",
        "state_class": "total_increasing",
    },
    {
        "key": "real_energy_delivered",
        "name": "Real energy delivered",
        "address": 19076,
        "unit": "kWh",
        "scale": 0.001,
        "device_class": "energy",
        "state_class": "total_increasing",
    },
    {
        "key": "apparent_energy",
        "name": "Apparent energy",
        "address": 19084,
        "unit": "VAh",
        "state_class": "total_increasing",
        "icon": "mdi:alpha-s-circle-outline",
    },
    {
        "key": "reactive_energy",
        "name": "Fundamental reactive energy",
        "address": 19092,
        "unit": "varh",
        "state_class": "total_increasing",
        "icon": "mdi:alpha-q-circle-outline",
    },
    {"key": "voltage_thd_l1", "name": "Voltage THD L1-N", "address": 19110, "unit": "%", "icon": "mdi:sine-wave"},
    {"key": "voltage_thd_l2", "name": "Voltage THD L2-N", "address": 19112, "unit": "%", "icon": "mdi:sine-wave"},
    {"key": "voltage_thd_l3", "name": "Voltage THD L3-N", "address": 19114, "unit": "%", "icon": "mdi:sine-wave"},
    {"key": "current_thd_l1", "name": "Current THD L1", "address": 19116, "unit": "%", "icon": "mdi:current-ac"},
    {"key": "current_thd_l2", "name": "Current THD L2", "address": 19118, "unit": "%", "icon": "mdi:current-ac"},
    {"key": "current_thd_l3", "name": "Current THD L3", "address": 19120, "unit": "%", "icon": "mdi:current-ac"},
]


def stop(_signum, _frame):
    """Request a clean shutdown after the current polling operation."""
    global RUNNING
    RUNNING = False


def read_options():
    """Load and validate the required Home Assistant add-on options."""
    options_path = "/data/options.json"
    try:
        with open(options_path, encoding="utf-8") as options_file:
            options = json.load(options_file)
    except (OSError, json.JSONDecodeError) as err:
        raise RuntimeError(f"Unable to read add-on settings from {options_path}: {err}") from err

    for key in (
        "host",
        "port",
        "unit_id",
        "mqtt_host",
        "mqtt_port",
        "mqtt_username",
        "mqtt_password",
        "mqtt_topic_prefix",
        "scan_interval",
    ):
        if key not in options:
            raise RuntimeError(f"Required add-on setting '{key}' is missing")
    return options


def make_mqtt_client(options):
    """Create the MQTT client and configure its availability callback."""
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"{DEVICE_ID}_addon",
    )
    if options["mqtt_username"]:
        client.username_pw_set(options["mqtt_username"], options["mqtt_password"])

    status_topic = f'{options["mqtt_topic_prefix"]}/status'
    client.will_set(status_topic, payload="offline", qos=1, retain=True)

    def on_connect(mqtt_client, _userdata, _flags, reason_code, _properties):
        if reason_code.is_failure:
            LOGGER.error("MQTT connection failed: %s", reason_code)
            return
        LOGGER.info("Connected to MQTT broker")
        mqtt_client.publish(status_topic, "online", qos=1, retain=True)
        publish_discovery(mqtt_client, options)

    client.on_connect = on_connect
    return client


def publish_discovery(client, options):
    """Publish retained Home Assistant MQTT Discovery configs for all sensors."""
    prefix = options["mqtt_topic_prefix"]
    device = {
        "identifiers": [DEVICE_ID],
        "name": "Janitza UMG 96-EL",
        "manufacturer": "Janitza",
        "model": "UMG 96-EL",
    }
    for sensor in SENSORS:
        key = sensor["key"]
        config = {
            "name": sensor["name"],
            "unique_id": f"{DEVICE_ID}_{key}",
            "state_topic": f"{prefix}/{key}/state",
            "availability_topic": f"{prefix}/status",
            "payload_available": "online",
            "payload_not_available": "offline",
            "device": device,
        }
        if "unit" in sensor:
            config["unit_of_measurement"] = sensor["unit"]
        if "device_class" in sensor:
            config["device_class"] = sensor["device_class"]
        if "icon" in sensor:
            config["icon"] = sensor["icon"]
        config["state_class"] = sensor.get("state_class", "measurement")
        client.publish(
            f"homeassistant/sensor/{DEVICE_ID}/{key}/config",
            json.dumps(config),
            qos=1,
            # Keep discovery available when Home Assistant reconnects.
            retain=True,
        )


def read_sensor(client, sensor, unit_id):
    """Read and decode one sensor's two holding registers as a float."""
    response = client.read_holding_registers(
        address=sensor["address"],
        count=2,
        slave=unit_id,
    )
    if response.isError():
        raise RuntimeError(f"Modbus error reading register {sensor['address']}: {response}")
    if len(response.registers) != 2:
        raise RuntimeError(f"Expected two registers at {sensor['address']}, got {len(response.registers)}")

    # Convert two big-endian registers into the meter's 32-bit float format.
    value = struct.unpack(">f", struct.pack(">HH", *response.registers))[0]
    value *= sensor.get("scale", 1)
    if not math.isfinite(value):
        raise RuntimeError(f"Invalid non-finite value at register {sensor['address']}")
    return value


def poll_device(options, mqtt_client):
    """Connect to the meter, publish sensor states, and always close the client."""
    modbus = ModbusTcpClient(options["host"], port=options["port"], timeout=5)
    try:
        if not modbus.connect():
            raise ConnectionError(f'Could not connect to Modbus device at {options["host"]}:{options["port"]}')
        for sensor in SENSORS:
            try:
                value = read_sensor(modbus, sensor, options["unit_id"])
                mqtt_client.publish(
                    f'{options["mqtt_topic_prefix"]}/{sensor["key"]}/state',
                    payload=format(value, ".2f"),
                    qos=1,
                    # Retained state gives Home Assistant the latest value on reconnect.
                    retain=True,
                )
            except (OSError, ModbusException, RuntimeError, struct.error) as err:
                LOGGER.error(
                    "Unable to read or publish %s (register %s): %s",
                    sensor["name"],
                    sensor["address"],
                    err,
                )
    finally:
        modbus.close()


def main():
    """Load settings and run the MQTT-connected polling loop until stopped."""
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    options = read_options()
    mqtt_client = make_mqtt_client(options)

    while RUNNING:
        try:
            mqtt_client.connect(options["mqtt_host"], options["mqtt_port"], keepalive=60)
            break
        except OSError:
            LOGGER.exception("Unable to connect to MQTT broker; retrying in 10 seconds")
            time.sleep(10)

    if not RUNNING:
        return
    mqtt_client.loop_start()
    try:
        while RUNNING:
            if mqtt_client.is_connected():
                try:
                    poll_device(options, mqtt_client)
                except (ConnectionError, OSError, ModbusException) as err:
                    LOGGER.error("Unable to poll the Janitza meter: %s", err)
            else:
                LOGGER.warning("MQTT is disconnected; waiting for automatic reconnection")
            # scan_interval is a delay after polling, not a fixed start-to-start period.
            time.sleep(options["scan_interval"])
    finally:
        mqtt_client.publish(f'{options["mqtt_topic_prefix"]}/status', "offline", qos=1, retain=True)
        mqtt_client.disconnect()
        mqtt_client.loop_stop()


if __name__ == "__main__":
    main()
