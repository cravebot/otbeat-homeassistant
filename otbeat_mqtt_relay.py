#!/usr/bin/env python3
"""
OTbeat Heart Rate BLE to MQTT Relay for Home Assistant
Connects to multiple OTbeat sensors via Bluetooth and publishes heart rate to MQTT
"""

import asyncio
import json
import logging
from typing import Dict, Optional
from bleak import BleakScanner, BleakClient
from bleak.backends.device import BLEDevice
import paho.mqtt.client as mqtt

# Import configuration from config.py
try:
    from config import (
        MQTT_BROKER,
        MQTT_PORT,
        MQTT_USERNAME,
        MQTT_PASSWORD,
        MQTT_TOPIC_PREFIX,
        SCAN_DURATION,
        RESCAN_INTERVAL
    )
except ImportError:
    print("ERROR: config.py not found!")
    print("Please create a config.py file with your MQTT settings.")
    print("See config.py.example for reference.")
    exit(1)

# Bluetooth Heart Rate Service UUIDs
HR_SERVICE_UUID = "0000180d-0000-1000-8000-00805f9b34fb"
HR_MEASUREMENT_UUID = "00002a37-0000-1000-8000-00805f9b34fb"

# Logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class OTbeatMQTTRelay:
    def __init__(self):
        self.mqtt_client = None
        self.running = False
        self.sensor_tasks: Dict[str, asyncio.Task] = {}  # MAC address -> task
        self.connected_devices: Dict[str, BLEDevice] = {}  # MAC address -> device info
        
    def setup_mqtt(self):
        """Initialize MQTT client and connect to broker"""
        self.mqtt_client = mqtt.Client()
        
        if MQTT_USERNAME and MQTT_PASSWORD:
            self.mqtt_client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
        
        self.mqtt_client.on_connect = self.on_mqtt_connect
        self.mqtt_client.on_disconnect = self.on_mqtt_disconnect
        
        logger.info(f"Connecting to MQTT broker at {MQTT_BROKER}:{MQTT_PORT}")
        self.mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
        self.mqtt_client.loop_start()
    
    def on_mqtt_connect(self, client, userdata, flags, rc):
        """Callback when MQTT connects"""
        if rc == 0:
            logger.info("Connected to MQTT broker")
        else:
            logger.error(f"MQTT connection failed with code {rc}")
    
    def on_mqtt_disconnect(self, client, userdata, rc):
        """Callback when MQTT disconnects"""
        logger.warning(f"Disconnected from MQTT broker (code {rc})")
    
    def publish_discovery(self, device_address: str, device_name: str):
        """Publish Home Assistant MQTT discovery message"""
        # Get last 4 characters of MAC address (without colons)
        mac_suffix = device_address.replace(":", "")[-4:].lower()
        device_id = f"otbeat_{mac_suffix}"
        
        # Create device-specific topics
        discovery_topic = f"{MQTT_TOPIC_PREFIX}_{mac_suffix}/config"
        state_topic = f"{MQTT_TOPIC_PREFIX}_{mac_suffix}/state"
        
        discovery_payload = {
            "name": f"OTbeat HR ({mac_suffix.upper()})",
            "state_topic": state_topic,
            "unit_of_measurement": "bpm",
            "icon": "mdi:heart-pulse",
            "unique_id": f"{device_id}_hr",
            "device": {
                "identifiers": [device_id],
                "name": f"{device_name or 'OTbeat'} ({mac_suffix.upper()})",
                "model": "Heart Rate Monitor",
                "manufacturer": "Orangetheory"
            }
        }
        
        self.mqtt_client.publish(discovery_topic, json.dumps(discovery_payload), retain=True)
        logger.info(f"Published Home Assistant discovery for device {mac_suffix.upper()}")
    
    def publish_heart_rate(self, device_address: str, heart_rate: int):
        """Publish heart rate to MQTT"""
        mac_suffix = device_address.replace(":", "")[-4:].lower()
        state_topic = f"{MQTT_TOPIC_PREFIX}_{mac_suffix}/state"
        self.mqtt_client.publish(state_topic, str(heart_rate))
        logger.debug(f"[{mac_suffix.upper()}] Published heart rate: {heart_rate} bpm")
    
    def parse_heart_rate(self, data: bytearray) -> int:
        """Parse heart rate from BLE notification data"""
        # First byte contains flags
        flags = data[0]
        
        # Check if heart rate is 16-bit (bit 0 of flags)
        if flags & 0x01:
            # 16-bit heart rate value
            heart_rate = int.from_bytes(data[1:3], byteorder='little')
        else:
            # 8-bit heart rate value
            heart_rate = data[1]
        
        return heart_rate
    
    def create_heart_rate_callback(self, device_address: str):
        """Create a callback function for a specific device"""
        def heart_rate_callback(sender, data: bytearray):
            """Callback when heart rate notification is received"""
            try:
                heart_rate = self.parse_heart_rate(data)
                mac_suffix = device_address.replace(":", "")[-4:].upper()
                logger.info(f"[{mac_suffix}] Heart rate: {heart_rate} bpm")
                self.publish_heart_rate(device_address, heart_rate)
            except Exception as e:
                logger.error(f"Error parsing heart rate data: {e}")
        return heart_rate_callback
    
    async def find_otbeat_devices(self):
        """Scan for all OTbeat devices"""
        logger.info("Scanning for OTbeat devices...")
        
        devices = await BleakScanner.discover(timeout=SCAN_DURATION)
        
        otbeat_devices = []
        
        # Look for devices with Heart Rate Service
        for device in devices:
            # Check by name
            if device.name and ("OTbeat" in device.name or "HR" in device.name):
                logger.info(f"Found device by name: {device.name} ({device.address})")
                otbeat_devices.append(device)
                continue
            
            # Check by service UUID
            if device.metadata.get("uuids") and HR_SERVICE_UUID in device.metadata.get("uuids", []):
                logger.info(f"Found HR device: {device.name or 'Unknown'} ({device.address})")
                otbeat_devices.append(device)
        
        if not otbeat_devices:
            logger.warning("No OTbeat devices found. Make sure sensors are on and nearby.")
        else:
            logger.info(f"Found {len(otbeat_devices)} OTbeat device(s)")
        
        return otbeat_devices
    
    async def monitor_single_device(self, device: BLEDevice):
        """Connect to and monitor a single OTbeat sensor"""
        mac_suffix = device.address.replace(":", "")[-4:].upper()
        
        try:
            logger.info(f"[{mac_suffix}] Connecting to {device.name} ({device.address})")
            
            async with BleakClient(device.address) as client:
                logger.info(f"[{mac_suffix}] Connected to OTbeat sensor")
                
                # Publish discovery
                self.publish_discovery(device.address, device.name or "OTbeat")
                
                # Create device-specific callback
                callback = self.create_heart_rate_callback(device.address)
                
                # Subscribe to heart rate notifications
                await client.start_notify(HR_MEASUREMENT_UUID, callback)
                logger.info(f"[{mac_suffix}] Subscribed to heart rate notifications")
                
                # Keep connection alive
                while self.running and client.is_connected:
                    await asyncio.sleep(1)
                    
        except Exception as e:
            logger.error(f"[{mac_suffix}] Connection error: {e}")
        finally:
            logger.info(f"[{mac_suffix}] Disconnected")
            
            # Publish heart rate as 0 when disconnected
            self.publish_heart_rate(device.address, 0)
            logger.info(f"[{mac_suffix}] Published HR as 0 (disconnected)")
            
            # Remove from connected devices
            if device.address in self.connected_devices:
                del self.connected_devices[device.address]
            if device.address in self.sensor_tasks:
                del self.sensor_tasks[device.address]
    
    async def scan_and_connect_devices(self):
        """Scan for new devices and connect to them"""
        devices = await self.find_otbeat_devices()
        
        for device in devices:
            # Skip if already connected
            if device.address in self.connected_devices:
                continue
            
            # Store device info
            self.connected_devices[device.address] = device
            
            # Create a task to monitor this device
            task = asyncio.create_task(self.monitor_single_device(device))
            self.sensor_tasks[device.address] = task
            
            mac_suffix = device.address.replace(":", "")[-4:].upper()
            logger.info(f"[{mac_suffix}] Started monitoring task")
    
    async def run(self):
        """Main run loop"""
        self.setup_mqtt()
        self.running = True
        
        try:
            while self.running:
                # Scan for devices and connect to new ones
                await self.scan_and_connect_devices()
                
                # Wait before next scan
                logger.info(f"Next scan in {RESCAN_INTERVAL} seconds. Currently monitoring {len(self.connected_devices)} device(s).")
                
                # Sleep in chunks so we can respond to interrupts
                for _ in range(RESCAN_INTERVAL):
                    if not self.running:
                        break
                    await asyncio.sleep(1)
                    
        except KeyboardInterrupt:
            logger.info("Shutdown requested")
        finally:
            self.running = False
            
            # Cancel all sensor tasks
            for address, task in list(self.sensor_tasks.items()):
                mac_suffix = address.replace(":", "")[-4:].upper()
                logger.info(f"[{mac_suffix}] Stopping...")
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            
            logger.info("All sensors disconnected")


if __name__ == "__main__":
    relay = OTbeatMQTTRelay()
    try:
        asyncio.run(relay.run())
    except KeyboardInterrupt:
        logger.info("Shutdown requested")
    finally:
        if relay.mqtt_client:
            relay.mqtt_client.loop_stop()
            relay.mqtt_client.disconnect()
