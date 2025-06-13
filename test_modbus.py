#!/usr/bin/env python3
"""
Standalone test script for Sungrow modbus communication.
Use this to quickly test individual registers and debug communication issues.
"""

from modbus_client import SungrowModbusClient
import sys


def test_individual_registers():
    """Test reading individual registers to debug potential issues."""
    client = SungrowModbusClient()
    
    if not client.connect():
        print("❌ Failed to connect")
        return
    
    # Test registers that are most likely to work with basic values
    basic_registers = {
        'active_power': 'Should show current power output (negative = consuming)',
        'daily_energy': 'Daily energy generation',
        'total_energy': 'Total energy since installation'
    }
    
    print("🔍 Testing basic registers:")
    print("=" * 50)
    
    for reg_name, description in basic_registers.items():
        print(f"\n📊 Testing {reg_name}:")
        print(f"   Description: {description}")
        
        reg_info = client.get_register_info(reg_name)
        print(f"   Address: {reg_info['address']}")
        print(f"   Data type: {reg_info['data_type']}")
        print(f"   Scale: {reg_info['scale']}")
        
        value = client.read_register(reg_name)
        if value is not None:
            print(f"   ✅ Value: {value} {reg_info['unit']}")
        else:
            print(f"   ❌ Failed to read")
    
    client.disconnect()


def test_raw_register(address: int, data_type: str = 'uint16', count: int = 1):
    """Test reading a raw register address."""
    client = SungrowModbusClient()
    
    if not client.connect():
        print("❌ Failed to connect")
        return
    
    try:
        from pymodbus.client import ModbusTcpClient
        
        result = client.client.read_holding_registers(
            address=address,
            count=count,
            slave=1
        )
        
        if not result.isError():
            print(f"✅ Raw register {address}: {result.registers}")
            
            # Try to convert based on data type
            if data_type == 'uint16' and len(result.registers) >= 1:
                print(f"   As uint16: {result.registers[0]}")
            elif data_type == 'int16' and len(result.registers) >= 1:
                value = result.registers[0]
                signed = value if value < 32768 else value - 65536
                print(f"   As int16: {signed}")
            elif data_type == 'uint32' and len(result.registers) >= 2:
                value = (result.registers[0] << 16) | result.registers[1]
                print(f"   As uint32: {value}")
                
        else:
            print(f"❌ Error reading register {address}: {result}")
            
    except Exception as e:
        print(f"❌ Exception: {e}")
    
    finally:
        client.disconnect()


def main():
    if len(sys.argv) > 1:
        if sys.argv[1] == 'raw':
            if len(sys.argv) >= 3:
                address = int(sys.argv[2])
                data_type = sys.argv[3] if len(sys.argv) > 3 else 'uint16'
                count = int(sys.argv[4]) if len(sys.argv) > 4 else 1
                print(f"🔍 Testing raw register {address} as {data_type}")
                test_raw_register(address, data_type, count)
            else:
                print("Usage: python test_modbus.py raw <address> [data_type] [count]")
        else:
            print("Unknown command. Use 'raw' to test raw registers.")
    else:
        test_individual_registers()


if __name__ == "__main__":
    main() 