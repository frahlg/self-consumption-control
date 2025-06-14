#!/usr/bin/env python3
"""
Debug version of InfluxDB pusher to troubleshoot data collection issues
"""

import asyncio
import time
import logging
from datetime import datetime
from typing import Dict, Any, Optional
import yaml
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from sungrow_controller import SungrowController

# Configure detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_data_collection():
    """Test data collection from Sungrow controller."""
    print("🔍 Testing Sungrow Controller Data Collection")
    print("=" * 50)
    
    controller = SungrowController()
    
    try:
        print("🔌 Connecting to Sungrow controller...")
        if not controller.connect():
            print("❌ Failed to connect to Sungrow controller")
            return False
        
        print("✅ Connected successfully")
        
        print("\n📊 Updating data from controller...")
        if not controller.update():
            print("❌ Failed to update data from controller")
            return False
        
        print("✅ Data update successful")
        
        print("\n📋 Getting current state...")
        state = controller.get_current_state()
        
        if not state:
            print("❌ No state data received")
            return False
        
        print("✅ State data received")
        
        print("\n🔍 Raw State Data:")
        print("-" * 30)
        for category, data in state.items():
            print(f"\n{category.upper()}:")
            for key, value in data.items():
                print(f"  {key}: {value}")
        
        print("\n🔍 Individual Data Objects:")
        print("-" * 30)
        print(f"Power Data: {controller.power_data}")
        print(f"Battery Data: {controller.battery_data}")
        print(f"Energy Data: {controller.energy_data}")
        print(f"System Info: {controller.system_info}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error during data collection test: {e}")
        return False
    finally:
        controller.disconnect()


def test_influxdb_connection():
    """Test InfluxDB connection and write a test point."""
    print("\n🔍 Testing InfluxDB Connection")
    print("=" * 50)
    
    # Load config
    with open('influxdb_config.yaml', 'r') as file:
        config = yaml.safe_load(file)
    
    influxdb_url = config['influxdb']['url']
    token = config['influxdb']['token']
    org = config['influxdb']['org']
    bucket = config['influxdb']['bucket']
    
    print(f"📡 Connecting to: {influxdb_url}")
    print(f"📡 Organization: {org}")
    print(f"📡 Bucket: {bucket}")
    
    try:
        client = InfluxDBClient(url=influxdb_url, token=token, org=org)
        write_api = client.write_api(write_options=SYNCHRONOUS)
        
        # Test health
        health = client.health()
        print(f"✅ InfluxDB Health: {health.status}")
        
        # Create a test point
        test_point = Point("test_measurement") \
            .time(datetime.now(), WritePrecision.MS) \
            .field("test_value", 42.0) \
            .tag("source", "debug_test")
        
        print("📝 Writing test point...")
        write_api.write(bucket=bucket, org=org, record=test_point)
        print("✅ Test point written successfully")
        
        client.close()
        return True
        
    except Exception as e:
        print(f"❌ InfluxDB test failed: {e}")
        return False


def test_full_data_flow():
    """Test the complete data flow from Sungrow to InfluxDB."""
    print("\n🔍 Testing Complete Data Flow")
    print("=" * 50)
    
    # Load config
    with open('influxdb_config.yaml', 'r') as file:
        config = yaml.safe_load(file)
    
    controller = SungrowController()
    
    try:
        # Connect to controller
        if not controller.connect():
            print("❌ Failed to connect to Sungrow controller")
            return False
        
        # Update data
        if not controller.update():
            print("❌ Failed to update controller data")
            return False
        
        # Get state
        state = controller.get_current_state()
        
        # Extract measurements like the pusher does
        timestamp = time.time()
        measurements = {
            'timestamp': timestamp,
            'datetime': datetime.fromtimestamp(timestamp),
            'solar_power': state['power']['solar_power'],
            'battery_power': state['power']['battery_power'],
            'grid_power': state['power']['grid_power'],
            'load_power': state['power']['load_power'],
            'battery_soc': state['battery']['level'],
            'grid_frequency': state['power']['grid_frequency'],
            'running_state': state['system']['running_state'],
            'ems_mode': state['system']['ems_mode'],
        }
        
        print("📊 Extracted Measurements:")
        for key, value in measurements.items():
            if key not in ['timestamp', 'datetime']:
                print(f"  {key}: {value}")
        
        # Test InfluxDB write
        influxdb_url = config['influxdb']['url']
        token = config['influxdb']['token']
        org = config['influxdb']['org']
        bucket = config['influxdb']['bucket']
        
        client = InfluxDBClient(url=influxdb_url, token=token, org=org)
        write_api = client.write_api(write_options=SYNCHRONOUS)
        
        # Create point
        point = Point("energy_system_debug") \
            .time(measurements['datetime'], WritePrecision.MS)
        
        # Add fields
        for field in ['solar_power', 'battery_power', 'grid_power', 'load_power', 'battery_soc', 'grid_frequency']:
            if field in measurements and measurements[field] is not None:
                point = point.field(field, float(measurements[field]))
                print(f"  Added field: {field} = {measurements[field]}")
        
        for field in ['running_state', 'ems_mode']:
            if field in measurements and measurements[field] is not None:
                point = point.field(field, int(measurements[field]))
                print(f"  Added field: {field} = {measurements[field]}")
        
        point = point.tag("source", "debug_test")
        
        print("📝 Writing data point to InfluxDB...")
        write_api.write(bucket=bucket, org=org, record=point)
        print("✅ Data written successfully!")
        
        client.close()
        controller.disconnect()
        
        return True
        
    except Exception as e:
        print(f"❌ Full data flow test failed: {e}")
        controller.disconnect()
        return False


def main():
    """Run all debug tests."""
    print("🚀 InfluxDB Pusher Debug Tool")
    print("=" * 60)
    
    # Test 1: Data collection
    if not test_data_collection():
        print("\n❌ Data collection test failed - stopping")
        return
    
    # Test 2: InfluxDB connection
    if not test_influxdb_connection():
        print("\n❌ InfluxDB connection test failed - stopping")
        return
    
    # Test 3: Full data flow
    if not test_full_data_flow():
        print("\n❌ Full data flow test failed")
        return
    
    print("\n🎉 All tests passed! The system should be working.")
    print("\nNext steps:")
    print("1. Check your InfluxDB dashboard/UI for the test data")
    print("2. Look for measurements: 'test_measurement' and 'energy_system_debug'")
    print("3. Run the main influxdb_pusher.py service")


if __name__ == "__main__":
    main() 