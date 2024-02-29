import bitstring
import configparser
import json
import logging
import os
import paho.mqtt.client as mqtt
from pyModbusTCP.client import ModbusClient
import struct
from time import sleep

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("debug.log"),
        logging.StreamHandler()
    ]
)


def get_config():
    cfg = configparser.ConfigParser()
    if os.path.exists('settings.ini'):
        cfg.read('settings.ini')
    else:
        cfg['DEFAULT'] = {
            'log_level': os.getenv("SOFAR_LOG_LEVEL", "info"),
        }
        cfg['MQTT'] = {
            'host': os.getenv("MQTT_HOST", "sofar_mqtt"),
            'port': os.getenv("MQTT_PORT", 1883),
            'username': os.getenv("MQTT_USERNAME", ""),
            'password': os.getenv("MQTT_PASSWORD", ""),
            'topic': os.getenv("MQTT_TOPIC", "sofar2mqtt/state"),
            'cmd_topic': os.getenv("MQTT_CMD_TOPIC", "sofar2mqtt/cmd"),
        }
        cfg['MODBUS'] = {
            'host': os.getenv("MODBUS_HOST", "localhost"),
            'port': os.getenv("MODBUS_PORT", 8234),
            'polling_interval': os.getenv("MODBUS_POLLING_INTERVAL", 5),
            'modbus_debug': os.getenv("MODBUS_DEBUG", False),
            'sofar_slave_id': os.getenv("SOFAR_SLAVE_ID", 0x01),
            'max_power': os.getenv("MAX_POWER", 3000)
        }
        with open('settings.ini', 'w') as configfile:
            cfg.write(configfile)
    return cfg


config = get_config()

SERVER_HOST = config['MODBUS']['host']
SERVER_PORT = config.getint('MODBUS', 'port')
SLEEP_TIME = config.getint('MODBUS', 'polling_interval')
MODBUS_DEBUG = config.getboolean('MODBUS', 'modbus_debug')
SOFAR_SLAVE_ID = config['MODBUS']['sofar_slave_id']
MAX_POWER = config.getint('MODBUS', 'max_power')

MQTT_HOST = config['MQTT']['host']
MQTT_PORT = config.getint('MQTT', 'port')
MQTT_USER = config['MQTT']['username']
MQTT_PASS = config['MQTT']['password']
MQTT_TOPIC = config['MQTT']['topic']
MQTT_CMD_TOPIC = config['MQTT']['cmd_topic']

logger = logging.getLogger("sofar_to_mqtt")
logger.setLevel(getattr(logging, config['DEFAULT']['log_level'].upper()))


class CustomModbusClient(ModbusClient):
    def write_work_mode_cmd(self, reg_addr, reg_value):
        if not 0 <= int(reg_addr) <= 0xffff:
            raise ValueError('reg_addr out of range (valid from 0 to 65535)')
        if not 0 <= int(reg_value) <= 0xffff:
            raise ValueError('reg_value out of range (valid from 0 to 65535)')
        try:
            tx_pdu = struct.pack('>BHH', 0x42, reg_addr, reg_value)
            rx_pdu = self._req_pdu(tx_pdu=tx_pdu, rx_min_len=3)
            byte_count = rx_pdu[1]
            f_regs = rx_pdu[2:]
            if byte_count < 2 * 1 or byte_count != len(f_regs):
                raise ModbusClient._NetworkError(4, 'rx byte count mismatch')
            registers = [0] * 1
            for i in range(1):
                registers[i] = struct.unpack('>H', f_regs[i * 2:i * 2 + 2])[0]
            return registers
        except ModbusClient._InternalError as e:
            self._req_except_handler(e)
            return False


c = CustomModbusClient()

c.debug = MODBUS_DEBUG
c.host = SERVER_HOST
c.port = SERVER_PORT
c.mode = 2
c.timeout = 5
c.auto_open = True
c.auto_close = True


def get_bin_from_hex(hex_string):
    return int(f"{hex_string}", 16)


def get_sofar_running_state(cl):
    running_states = ["WaitState", "CheckState", "NormalState", "CheckDischargeState", "DischargeState", "EPSState",
                      "FaultState", "PermanentState"]
    reg = cl.read_holding_registers(512, 1)
    if reg:
        if int(str(reg[0])) <= 7:
            return True, running_states[reg[0]], reg[0]
        else:
            return False, "Unknown", 9


def get_reg_value(cl, address, multiplier=None, bs=False, reg_type="holding"):
    if reg_type == "input":
        r = cl.read_input_registers(get_bin_from_hex(address))
    else:
        r = cl.read_holding_registers(get_bin_from_hex(address))
    val = r[0]
    if bs:
        val = bitstring.Bits(uint=val, length=16)
        val = val.unpack('int')[0]
    if multiplier:
        return val * multiplier
    return val


def on_connect(client, userdata, flags, rc, props):
    print("Connected with result code " + str(rc))
    client.subscribe(f"{MQTT_CMD_TOPIC}/#")


def on_message(client, userdata, msg):
    data = msg.payload.decode()
    get_cmd = msg.topic.replace(MQTT_CMD_TOPIC + "/", "")

    if get_cmd == "charge":
        if 0 < int(data) <= int(MAX_POWER):
            logger.debug(f"Sending charge command to Sofar Solar Controller for {data} W")
            print(c.write_work_mode_cmd(get_bin_from_hex("0x0102"), int(data)))

    if get_cmd == "auto":
        logger.debug(f"Sending auto command to Sofar Solar Controller")
        print(c.write_work_mode_cmd(get_bin_from_hex("0x0103"), get_bin_from_hex("0x5555")))

    if get_cmd == "discharge":
        if 0 < int(data) <= int(MAX_POWER):
            logger.debug(f"Sending discharge command to Sofar Solar Controller for {data} W")
            print(c.write_work_mode_cmd(get_bin_from_hex("0x0101"), int(data)))

    if get_cmd == "standby":
        logger.debug(f"Sending standby command to Sofar Solar Controller")
        print(c.write_work_mode_cmd(get_bin_from_hex("0x0100"), get_bin_from_hex("0x5555")))


def publish(client, data):
    client.publish(MQTT_TOPIC, data)
    logger.debug(f"Published message: {data}")


if __name__ == "__main__":
    mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    mqttc.username_pw_set(MQTT_USER, MQTT_PASS)
    mqttc.on_connect = on_connect
    mqttc.on_message = on_message
    mqttc.enable_bridge_mode()
    mqttc.connect(MQTT_HOST, MQTT_PORT)

    RUNNING = True

    while RUNNING:
        mqttc.loop_start()
        out = {}
        if c.open():
            state_bool, running_state, state_int = get_sofar_running_state(c)
            out["state"] = running_state
            out["running_state"] = state_int
            logger.info(f"state_bool: {state_bool} - running_state: {running_state} - running_state_int: {state_int}")
            if state_bool:

                num_of_regs = 52
                reg = c.read_holding_registers(get_bin_from_hex("0x0206"), num_of_regs)
                if reg and len(reg) == num_of_regs:
                    logger.debug(f"reg response: {reg}")
                    out = {
                        'state': running_state,
                        'running_state': state_int,
                        'grid_voltage': round(reg[0] * 0.1, 2),
                        'grid_current': round(bitstring.Bits(uint=reg[1], length=16).unpack('int')[0] * 0.01, 2),
                        'grid_freq': round(reg[6] * 0.01, 2),
                        'battery_power': round(bitstring.Bits(uint=reg[7], length=16).unpack('int')[0] * 10, 2),
                        'battery_voltage': round(reg[8] * 0.01, 2),
                        'battery_current': round(bitstring.Bits(uint=reg[9], length=16).unpack('int')[0] * 0.01, 2),
                        'batterySOC': reg[10],
                        'bat_temperature': reg[11],
                        'feed_in_out_power': round(bitstring.Bits(uint=reg[12], length=16).unpack('int')[0] * 0.01, 2),
                        'load_power': round(reg[13] * 0.01, 2),
                        'in_out_power': bitstring.Bits(uint=reg[14], length=16).unpack('int')[0] * 0.01,
                        'generation_power': round(reg[15] * 0.01, 2),
                        'today_generation': round(reg[18] * 0.01, 2),
                        'today_exported': round(reg[17] * 0.01, 2),
                        'today_purchase': round(reg[20] * 0.01, 2),
                        'today_consumption_of_load': round(reg[21] * 0.01),
                        'bat_cycles': reg[38],
                        'inverter_bus_voltage': round(reg[39] * 0.01, 2),
                        'llc_bus_voltage': round(reg[40] * 0.01, 2),
                        'generation_current': reg[48],
                        'inner_temperature': reg[50],
                        'heatsink_temperature': reg[51],
                    }

                num_of_regs = 13
                reg = c.read_input_registers(get_bin_from_hex("0x10B0"), num_of_regs)
                if reg and len(reg) == num_of_regs:
                    logger.debug(f"reg response: {reg}")
                    battery_types = {
                        0: 'Darfon',
                        1: 'Pylontech',
                        2: 'Soltaro',
                        3: 'Soltaro or Alpha.ess',
                        4: 'General',
                        80: 'Tele',
                        100: 'Default'
                    }
                    out['battery_type'] = battery_types[reg[0]]
                    out['battery_capacity'] = reg[1]
                    out['max_charge_voltage'] = round(reg[3] * 0.1, 2)
                    out['max_charge_current'] = round(reg[4] * 0.01, 2)
                    out['over_voltage_protection'] = round(reg[5] * 0.1, 2)
                    out['min_discharge_voltage'] = round(reg[6] * 0.1, 2)
                    out['max_discharge_current'] = round(reg[7] * 0.01, 2)
                    out['under_volt_protection_point'] = round(reg[8] * 0.1, 2)
                    out['discharge_depth'] = reg[9]
                    out['empty_battery_voltage'] = round(reg[11] * 0.01, 2)
                    out['full_battery_voltage'] = round(reg[12] * 0.01, 2)

            c.close()

            publish(mqttc, json.dumps(out))

        logger.debug(out)
        sleep(SLEEP_TIME)
        mqttc.loop_stop()
