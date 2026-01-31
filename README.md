# OTbeat to Home Assistant

A Raspberry Pi BLE relay that connects Orangetheory Fitness (OTbeat) heart rate sensors to Home Assistant via MQTT. Supports multiple sensors simultaneously with automatic discovery.

## Features

- 🔄 Automatic discovery and connection to multiple OTbeat sensors
- 📡 Real-time heart rate data publishing via MQTT
- 🏠 Home Assistant auto-discovery (sensors appear automatically)
- 🔌 Reconnects automatically if sensors disconnect
- 🆔 Unique device IDs based on MAC address for multi-sensor support
- ⚡ Lightweight and efficient - runs great on Raspberry Pi

## Supported Devices

- OTbeat Burn
- OTbeat Core
- OTbeat Flex
- OTbeat Link
- Any Bluetooth heart rate monitor using the standard Heart Rate Service (UUID: 0x180D)

## Hardware Requirements

- Raspberry Pi (any model with Bluetooth or USB Bluetooth dongle)
- Bluetooth 4.0+ adapter (built-in or USB dongle)
- OTbeat heart rate sensor(s)
- Home Assistant with MQTT broker

## Quick Start

```bash
# Clone the repository
git clone https://github.com/yourusername/otbeat-homeassistant.git
cd otbeat-homeassistant

# Install dependencies
pip3 install -r requirements.txt

# Configure MQTT settings
cp config.py.example config.py
nano config.py

# Run the relay
python3 otbeat_mqtt_relay.py
```

## Installation on Raspberry Pi

1. **Update your system:**
```bash
sudo apt update
sudo apt upgrade -y
```

2. **Install Python dependencies:**
```bash
sudo apt install python3-pip python3-dev libbluetooth-dev -y
```

3. **Install Python packages:**
```bash
pip3 install -r requirements.txt
```

## Configuration

**Create your config file:**
```bash
cp config.py.example config.py
nano config.py
```

Update these settings in `config.py`:

```python
MQTT_BROKER = "192.168.1.100"  # Your Home Assistant IP or hostname
MQTT_PORT = 1883
MQTT_USERNAME = "your_username"  # Add username if required (or keep as None)
MQTT_PASSWORD = "your_password"  # Add password if required (or keep as None)
```

**Note:** The `config.py` file is in `.gitignore` so your credentials won't be accidentally committed to git.

## Running the Script

1. **Make sure your OTbeat sensor is on** (wear it or press the button)

2. **Run the script:**
```bash
python3 otbeat_mqtt_relay.py
```

3. **The script will:**
   - Scan for your OTbeat sensor
   - Connect automatically
   - Create a sensor in Home Assistant called `sensor.otbeat_heart_rate`

## Setting Up Automatic Start (systemd service)

1. **Create a service file:**
```bash
sudo nano /etc/systemd/system/otbeat-relay.service
```

2. **Paste this content** (update the path and user):
```ini
[Unit]
Description=OTbeat MQTT Relay
After=network.target bluetooth.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi
ExecStart=/usr/bin/python3 /home/pi/otbeat_mqtt_relay.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

3. **Enable and start the service:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable otbeat-relay.service
sudo systemctl start otbeat-relay.service
```

4. **Check status:**
```bash
sudo systemctl status otbeat-relay.service
```

## Home Assistant Automation for Light Color

Once the sensor appears in Home Assistant, create an automation:

```yaml
automation:
  - alias: "Heart Rate Light Color"
    trigger:
      - platform: state
        entity_id: sensor.otbeat_heart_rate
    action:
      - choose:
          # Resting (< 100 bpm) - Blue
          - conditions:
              - condition: numeric_state
                entity_id: sensor.otbeat_heart_rate
                below: 100
            sequence:
              - service: light.turn_on
                target:
                  entity_id: light.your_light
                data:
                  rgb_color: [0, 100, 255]
          
          # Light activity (100-130 bpm) - Green
          - conditions:
              - condition: numeric_state
                entity_id: sensor.otbeat_heart_rate
                above: 99
                below: 131
            sequence:
              - service: light.turn_on
                target:
                  entity_id: light.your_light
                data:
                  rgb_color: [0, 255, 0]
          
          # Moderate (130-160 bpm) - Orange
          - conditions:
              - condition: numeric_state
                entity_id: sensor.otbeat_heart_rate
                above: 130
                below: 161
            sequence:
              - service: light.turn_on
                target:
                  entity_id: light.your_light
                data:
                  rgb_color: [255, 165, 0]
          
          # High intensity (160+ bpm) - Red
          - conditions:
              - condition: numeric_state
                entity_id: sensor.otbeat_heart_rate
                above: 160
            sequence:
              - service: light.turn_on
                target:
                  entity_id: light.your_light
                data:
                  rgb_color: [255, 0, 0]
```

## Troubleshooting

**Script can't find the sensor:**
- Make sure the OTbeat sensor is on and in pairing mode
- Check Bluetooth is enabled: `sudo systemctl status bluetooth`
- Try scanning manually: `sudo bluetoothctl` then `scan on`

**MQTT connection fails:**
- Verify broker IP/hostname
- Check firewall settings on Home Assistant
- Test with: `mosquitto_pub -h homeassistant.local -t test -m "hello"`

**Permission errors:**
- Add your user to bluetooth group: `sudo usermod -a -G bluetooth pi`
- Reboot after adding to group

**View logs:**
```bash
sudo journalctl -u otbeat-relay.service -f
```

## Contributing

Contributions are welcome! Feel free to:
- Report bugs or issues
- Suggest new features
- Submit pull requests

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Built for the Home Assistant community
- Uses the [bleak](https://github.com/hbldh/bleak) library for Bluetooth LE
- Uses [paho-mqtt](https://github.com/eclipse/paho.mqtt.python) for MQTT communication
