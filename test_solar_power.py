#!/usr/bin/env python3
"""
Simple test to verify solar power reading from Sungrow inverter.
Based on the Home Assistant configuration that works.
"""

from modbus_client import SungrowModbusClient
import time


def test_solar_power():
    """Test reading solar power with the exact HA configuration."""
    print("🌞 Testing Solar Power Reading")
    print("=" * 50)
    
    client = SungrowModbusClient()
    
    try:
        if client.connect():
            print("✅ Connected to Sungrow inverter")
            
            # Test the solar power register specifically
            print("\n📊 Reading Total DC Power (Solar):")
            
            # Read the register
            solar_power = client.read_register('total_dc_power')
            
            if solar_power is not None:
                print(f"  🌞 Solar Power: {solar_power:.0f} W")
                
                # Validate the reading
                if 0 <= solar_power <= 15000:  # Reasonable range for solar power
                    print(f"  ✅ Reading looks valid (0-15kW range)")
                else:
                    print(f"  ⚠️ Reading seems out of range")
                    
            else:
                print("  ❌ Failed to read solar power")
                
            # Also test some other key registers
            print("\n📋 Other Key Readings:")
            
            test_registers = [
                'grid_frequency',
                'battery_level', 
                'export_power_raw',
                'running_state'
            ]
            
            for reg_name in test_registers:
                value = client.read_register(reg_name)
                if value is not None:
                    reg_info = client.get_register_info(reg_name)
                    unit = reg_info.get('unit', '') if reg_info else ''
                    print(f"  📊 {reg_name}: {value} {unit}")
                else:
                    print(f"  ❌ {reg_name}: Failed to read")
                    
            # Show register configuration for debugging
            print("\n🔧 Solar Power Register Configuration:")
            reg_info = client.get_register_info('total_dc_power')
            if reg_info:
                for key, value in reg_info.items():
                    print(f"  {key}: {value}")
                    
        else:
            print("❌ Failed to connect to inverter")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        client.disconnect()


def test_raw_register_read():
    """Test reading the raw register values for debugging."""
    print("\n🔧 Raw Register Debug")
    print("=" * 50)
    
    client = SungrowModbusClient()
    
    try:
        if client.connect():
            print("✅ Connected for raw register test")
            
            # Read raw registers at address 5016-5017 (total_dc_power)
            from pymodbus.client.tcp import ModbusTcpClient
            
            # Read 2 registers starting at 5016
            result = client.client.read_input_registers(address=5016, count=2, slave=1)
            
            if not result.isError():
                reg1 = result.registers[0]
                reg2 = result.registers[1]
                
                print(f"  Raw register 5016: {reg1} (0x{reg1:04X})")
                print(f"  Raw register 5017: {reg2} (0x{reg2:04X})")
                
                # Test different interpretations
                big_endian = (reg1 << 16) | reg2
                little_endian = (reg2 << 16) | reg1
                word_swap = (reg2 << 16) | reg1  # Same as little endian for this case
                
                print(f"\n  Interpretations:")
                print(f"    Big endian: {big_endian} W")
                print(f"    Little endian: {little_endian} W")
                print(f"    Word swap: {word_swap} W")
                print(f"    With scale 0.1: {word_swap * 0.1} W")
                print(f"    With scale 0.01: {word_swap * 0.01} W")
                
            else:
                print(f"  ❌ Error reading raw registers: {result}")
                
        else:
            print("❌ Failed to connect for raw test")
            
    except Exception as e:
        print(f"❌ Raw test error: {e}")
        
    finally:
        client.disconnect()


if __name__ == "__main__":
    test_solar_power()
    test_raw_register_read() 