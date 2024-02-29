# Sofar ME3000SP RS485 TCP to MQTT

This is a script that can be used to read and write to the Sofar ME3000SP controller, connected through a RS485 TCP adaptor. (For example with a PUSR USR-TCP232-304)

## Deployment
### 1. Using Docker compose
- Copy the `default.env` file to `override.venv` and modify the values according to your desire in the `override.env` file.


- Deploy with MQTT server:
  - `docker compose --profile mqtt up`
- Deployo without MQTT server (if you are running one you like to use for example):
  - `docker compose up`

### 2. Running it as a service
- Create a Python3 Virtual Environment: `python3 -m venv venv`
- Activate the virtual environment: `source venv/bin/activate`
- Install requirements: `pip3 install -r requirements.txt`
- Run script first time: `python3 sofar_poller/sofar_rs485_to_mqtt.py`
- Modify generated `settings.ini` file accordingly.
- If wanted, create a service based on the `systemd/system/sofar_rs485_tcp_to_mqtt.service` file included.

### 3. ???

### 4. Profit!

## Usage
### 1. Reading
Message will be pushed to configured MQTT broker at defined interval.
This could be used for Home Assistant. Perhaps an example will be added later.

### 2. Commands
- To put the Sofar ME3000SP in **standby** mode, send an MQTT message to te defined CMD topic appended with `/charge` in the configuration with a payload of `true`

  _Example using mosquitto_pub:_ `mosquitto_pub -h localhost -m true -t sofarsolar/cmd/standby`


- To put the Sofar ME3000SP in **auto** mode, send an MQTT message to te defined CMD topic appended with `/charge` in the configuration with a payload of `true`

  _Example using mosquitto_pub:_ `mosquitto_pub -h localhost -m true -t sofarsolar/cmd/auto`


- To put the Sofar ME3000SP in **charging** mode, send an MQTT message to te defined CMD topic appended with `/charge` in the configuration with a integer payload of the amount of watts to charge with.

  _Example using mosquitto_pub:_ `mosquitto_pub -h localhost -m "1500" -t sofarsolar/cmd/charge`


- To put the Sofar ME3000SP in **discharging** mode, send an MQTT message to te defined CMD topic appended with `/charge` in the configuration with a integer payload of the amount of watts to discharge with.

  _Example using mosquitto_pub:_ `mosquitto_pub -h localhost -m "1500" -t sofarsolar/cmd/discharge`

## Donations
#### Bitcoin: bc1qyr2q4r6df0v4eje6ktr4lsmtrl08u2wxx8my0t
#### Eth: 0x6f1B76464cD0a75b9a26Ca4Bc099567DFAb01d5a

