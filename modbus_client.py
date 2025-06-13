import yaml
import struct
from pymodbus.client import ModbusTcpClient
from pymodbus.constants import Endian
# Note: BinaryPayloadDecoder is deprecated in pymodbus 3.7+, but we'll keep it for compatibility
import logging
import time
from typing import Optional, Dict, Any, Union

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SungrowModbusClient:
    """
    Enhanced Sungrow Modbus client with comprehensive register support based on
    the official Home Assistant Sungrow integration.
    """
    
    def __init__(self, config_file: str = "config.yaml"):
        """Initialize the Sungrow Modbus client."""
        self.config_file = config_file
        self.client = None
        self.host = None
        self.port = None
        self.slave_id = None
        self.timeout = None
        self.delay = None
        self.registers = {}
        self.legacy_registers = {}
        
        self._load_config()
        
    def _load_config(self):
        """Load configuration from YAML file."""
        try:
            with open(self.config_file, 'r') as file:
                config = yaml.safe_load(file)
                
            modbus_config = config.get('modbus', {})
            self.host = modbus_config.get('host')
            self.port = modbus_config.get('port', 502)
            self.slave_id = modbus_config.get('slave_id', 1)
            self.timeout = modbus_config.get('timeout', 10)
            self.delay = modbus_config.get('delay', 0.1)
            
            self.registers = config.get('registers', {})
            self.legacy_registers = config.get('legacy_registers', {})
            
            logger.info(f"Loaded configuration: {self.host}:{self.port}, slave_id={self.slave_id}")
            logger.info(f"Loaded {len(self.registers)} registers and {len(self.legacy_registers)} legacy registers")
            
        except FileNotFoundError:
            logger.error(f"Configuration file {self.config_file} not found")
            raise
        except Exception as e:
            logger.error(f"Error loading configuration: {e}")
            raise
            
    def connect(self) -> bool:
        """Connect to the Modbus device."""
        try:
            self.client = ModbusTcpClient(host=self.host, port=self.port, timeout=self.timeout)
            connected = self.client.connect()
            if connected:
                logger.info(f"✅ Connected to Sungrow inverter at {self.host}:{self.port}")
                return True
            else:
                logger.error(f"❌ Failed to connect to {self.host}:{self.port}")
                return False
        except Exception as e:
            logger.error(f"❌ Connection error: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from the Modbus device."""
        if self.client:
            self.client.close()
            logger.info("🔌 Disconnected from Sungrow inverter")
    
    def _get_endianness(self, reg_config: dict) -> Endian:
        """Get endianness configuration."""
        endian = reg_config.get('endian', reg_config.get('endianness', 'big')).lower()
        if endian == 'little':
            return Endian.LITTLE
        return Endian.BIG
    
    def _decode_value(self, registers: list, reg_config: dict) -> Optional[Union[int, float, str]]:
        """Decode register values based on data type and configuration."""
        try:
            data_type = reg_config.get('data_type', 'uint16')
            scale = reg_config.get('scale', 1)
            endianness = self._get_endianness(reg_config)
            swap_word = reg_config.get('swap') == 'word'
            
            # Use new pymodbus API for decoding
            if hasattr(self.client, 'convert_from_registers'):
                # New API (pymodbus 3.7+)
                if data_type == 'uint16':
                    value = registers[0]
                elif data_type == 'int16':
                    value = registers[0] if registers[0] < 32768 else registers[0] - 65536
                elif data_type == 'uint32':
                    if swap_word:
                        # Swap word order: second register becomes high word
                        value = (registers[1] << 16) | registers[0]
                    elif endianness == Endian.BIG:
                        value = (registers[0] << 16) | registers[1]
                    else:
                        value = (registers[1] << 16) | registers[0]
                elif data_type == 'int32':
                    if swap_word:
                        # Swap word order: second register becomes high word
                        value = (registers[1] << 16) | registers[0]
                    elif endianness == Endian.BIG:
                        value = (registers[0] << 16) | registers[1]
                    else:
                        value = (registers[1] << 16) | registers[0]
                    # Convert to signed
                    if value >= 2147483648:
                        value -= 4294967296
                elif data_type == 'float32':
                    # For float, we'd need struct manipulation
                    import struct
                    if endianness == Endian.BIG:
                        packed = struct.pack('>HH', registers[0], registers[1])
                    else:
                        packed = struct.pack('<HH', registers[0], registers[1])
                    value = struct.unpack('>f' if endianness == Endian.BIG else '<f', packed)[0]
                elif data_type == 'string':
                    count = reg_config.get('count', 1)
                    chars = []
                    for i in range(min(count, len(registers))):
                        char_val = registers[i]
                        if char_val != 0:
                            chars.append(chr(char_val & 0xFF))
                            if char_val >> 8 != 0:
                                chars.append(chr(char_val >> 8))
                    return ''.join(chars).strip()
                else:
                    logger.warning(f"Unknown data type: {data_type}")
                    return None
            else:
                # Fallback to old API
                from pymodbus.payload import BinaryPayloadDecoder
                decoder = BinaryPayloadDecoder.fromRegisters(registers, byteorder=endianness, wordorder=endianness)
            
                # Decode based on data type (old API)
                if data_type == 'uint16':
                    value = decoder.decode_16bit_uint()
                elif data_type == 'int16':
                    value = decoder.decode_16bit_int()
                elif data_type == 'uint32':
                    value = decoder.decode_32bit_uint()
                elif data_type == 'int32':
                    value = decoder.decode_32bit_int()
                elif data_type == 'float32':
                    value = decoder.decode_32bit_float()
                elif data_type == 'string':
                    count = reg_config.get('count', 1)
                    # For string, decode as sequence of 16-bit values
                    chars = []
                    for _ in range(count):
                        if decoder._payload:
                            char_val = decoder.decode_16bit_uint()
                            if char_val != 0:  # Skip null characters
                                chars.append(chr(char_val & 0xFF))
                                if char_val >> 8 != 0:
                                    chars.append(chr(char_val >> 8))
                    return ''.join(chars).strip()
                else:
                    logger.warning(f"Unknown data type: {data_type}")
                    return None
                
            # Apply scaling
            if scale != 1 and isinstance(value, (int, float)):
                value = value * scale
                
            return value
            
        except Exception as e:
            logger.error(f"Error decoding value: {e}")
            return None
    
    def _encode_value(self, value: Union[int, float], reg_config: dict) -> list:
        """Encode value for writing to register."""
        try:
            data_type = reg_config.get('data_type', 'uint16')
            scale = reg_config.get('scale', 1)
            endianness = self._get_endianness(reg_config)
            
            # Apply inverse scaling
            if scale != 1:
                value = int(value / scale)
            
            # Use new or old API for encoding
            if hasattr(self.client, 'convert_to_registers'):
                # New API approach (manual encoding)
                if data_type == 'uint16':
                    return [int(value) & 0xFFFF]
                elif data_type == 'int16':
                    val = int(value)
                    return [val & 0xFFFF]
                elif data_type == 'uint32':
                    val = int(value)
                    if endianness == Endian.BIG:
                        return [(val >> 16) & 0xFFFF, val & 0xFFFF]
                    else:
                        return [val & 0xFFFF, (val >> 16) & 0xFFFF]
                elif data_type == 'int32':
                    val = int(value)
                    if val < 0:
                        val += 4294967296  # Convert to unsigned
                    if endianness == Endian.BIG:
                        return [(val >> 16) & 0xFFFF, val & 0xFFFF]
                    else:
                        return [val & 0xFFFF, (val >> 16) & 0xFFFF]
                elif data_type == 'float32':
                    import struct
                    if endianness == Endian.BIG:
                        packed = struct.pack('>f', float(value))
                        return list(struct.unpack('>HH', packed))
                    else:
                        packed = struct.pack('<f', float(value))
                        return list(struct.unpack('<HH', packed))
                else:
                    logger.warning(f"Unknown data type for writing: {data_type}")
                    return []
            else:
                # Fallback to old API
                from pymodbus.payload import BinaryPayloadBuilder
                builder = BinaryPayloadBuilder(byteorder=endianness, wordorder=endianness)
                
                # Encode based on data type
                if data_type == 'uint16':
                    builder.add_16bit_uint(int(value))
                elif data_type == 'int16':
                    builder.add_16bit_int(int(value))
                elif data_type == 'uint32':
                    builder.add_32bit_uint(int(value))
                elif data_type == 'int32':
                    builder.add_32bit_int(int(value))
                elif data_type == 'float32':
                    builder.add_32bit_float(float(value))
                else:
                    logger.warning(f"Unknown data type for writing: {data_type}")
                    return []
                    
                return builder.to_registers()
            
        except Exception as e:
            logger.error(f"Error encoding value: {e}")
            return []
    
    def read_register(self, register_name: str) -> Optional[Union[int, float, str]]:
        """Read a single register by name."""
        if not self.client:
            logger.error("Not connected to Modbus device")
            return None
            
        # Check if register exists
        reg_config = None
        if register_name in self.registers:
            reg_config = self.registers[register_name]
        elif register_name in self.legacy_registers:
            reg_config = self.legacy_registers[register_name]
        else:
            logger.error(f"Register '{register_name}' not found in configuration")
            return None
        
        try:
            address = reg_config['address']
            data_type = reg_config.get('data_type', 'uint16')
            function_code = reg_config.get('function_code', 4)  # Default to input registers
            count = reg_config.get('count', 1)
            
            # Determine register count based on data type
            if data_type in ['uint32', 'int32', 'float32']:
                register_count = 2
            elif data_type == 'string':
                register_count = count
            else:
                register_count = 1
            
            # Add delay between requests
            if self.delay:
                time.sleep(self.delay)
            
            # Read registers based on function code
            if function_code == 3:  # Holding registers
                result = self.client.read_holding_registers(address=address, count=register_count, slave=self.slave_id)
            elif function_code == 4:  # Input registers
                result = self.client.read_input_registers(address=address, count=register_count, slave=self.slave_id)
            else:
                logger.error(f"Unsupported function code: {function_code}")
                return None
            
            if result.isError():
                logger.error(f"Error reading register {register_name} at address {address}: {result}")
                return None
            
            # Decode the value
            value = self._decode_value(result.registers, reg_config)
            
            if value is not None:
                logger.debug(f"Read {register_name}: {value} {reg_config.get('unit', '')}")
            
            return value
            
        except Exception as e:
            logger.error(f"Exception reading register {register_name}: {e}")
            return None
    
    def write_register(self, register_name: str, value: Union[int, float]) -> bool:
        """Write a value to a register."""
        if not self.client:
            logger.error("Not connected to Modbus device")
            return False
            
        # Check if register exists and is writable
        if register_name not in self.registers:
            logger.error(f"Register '{register_name}' not found in configuration")
            return False
            
        reg_config = self.registers[register_name]
        
        if not reg_config.get('writable', False):
            logger.error(f"Register '{register_name}' is not writable")
            return False
        
        try:
            address = reg_config['address']
            function_code = reg_config.get('function_code', 3)  # Default to holding registers
            
            if function_code != 3:
                logger.error(f"Cannot write to register with function code {function_code}")
                return False
            
            # Encode the value
            encoded_registers = self._encode_value(value, reg_config)
            if not encoded_registers:
                return False
            
            # Add delay between requests
            if self.delay:
                time.sleep(self.delay)
            
            # Write to register(s)
            if len(encoded_registers) == 1:
                result = self.client.write_register(address=address, value=encoded_registers[0], slave=self.slave_id)
            else:
                result = self.client.write_registers(address=address, values=encoded_registers, slave=self.slave_id)
            
            if result.isError():
                logger.error(f"Error writing register {register_name} at address {address}: {result}")
                return False
            
            logger.info(f"✅ Wrote {register_name}: {value} {reg_config.get('unit', '')}")
            return True
            
        except Exception as e:
            logger.error(f"Exception writing register {register_name}: {e}")
            return False
    
    def read_multiple_registers(self, register_names: list) -> Dict[str, Any]:
        """Read multiple registers efficiently."""
        results = {}
        
        for register_name in register_names:
            value = self.read_register(register_name)
            results[register_name] = value
            
        return results
    
    def get_register_info(self, register_name: str) -> Optional[dict]:
        """Get register configuration information."""
        if register_name in self.registers:
            return self.registers[register_name].copy()
        elif register_name in self.legacy_registers:
            return self.legacy_registers[register_name].copy()
        return None
    
    def list_registers(self) -> list:
        """List all available registers."""
        return list(self.registers.keys()) + list(self.legacy_registers.keys())
    
    def list_writable_registers(self) -> list:
        """List all writable registers."""
        writable = []
        for name, config in self.registers.items():
            if config.get('writable', False):
                writable.append(name)
        return writable
    
    def get_system_info(self) -> Dict[str, Any]:
        """Get basic system information."""
        info_registers = [
            'inverter_serial', 'device_type_code', 'system_state', 'running_state',
            'inverter_temperature', 'grid_frequency'
        ]
        
        return self.read_multiple_registers(info_registers)
    
    def get_power_data(self) -> Dict[str, Any]:
        """Get power-related data."""
        power_registers = [
            'total_dc_power', 'total_active_power', 'load_power', 'export_power_raw',
            'meter_active_power', 'battery_power_raw'
        ]
        
        return self.read_multiple_registers(power_registers)
    
    def get_battery_data(self) -> Dict[str, Any]:
        """Get battery-related data."""
        battery_registers = [
            'battery_level', 'battery_voltage', 'battery_current', 'battery_power_raw',
            'battery_temperature', 'battery_state_of_health', 'battery_capacity'
        ]
        
        return self.read_multiple_registers(battery_registers)
    
    def get_energy_data(self) -> Dict[str, Any]:
        """Get energy counter data."""
        energy_registers = [
            'daily_pv_generation', 'total_pv_generation',
            'daily_imported_energy', 'total_imported_energy',
            'daily_exported_energy', 'total_exported_energy',
            'daily_battery_charge', 'total_battery_charge',
            'daily_battery_discharge', 'total_battery_discharge'
        ]
        
        return self.read_multiple_registers(energy_registers)
    
    # Control functions for common operations
    def set_ems_mode(self, mode: str) -> bool:
        """Set EMS mode. Options: 'self_consumption', 'forced', 'external_ems'"""
        mode_values = {
            'self_consumption': 0,
            'forced': 2,
            'external_ems': 3
        }
        
        if mode not in mode_values:
            logger.error(f"Invalid EMS mode: {mode}. Valid options: {list(mode_values.keys())}")
            return False
            
        return self.write_register('ems_mode_selection', mode_values[mode])
    
    def set_battery_forced_mode(self, command: str, power: int = 0) -> bool:
        """Set battery forced charge/discharge mode."""
        commands = {
            'stop': 0xCC,
            'charge': 0xAA,
            'discharge': 0xBB
        }
        
        if command not in commands:
            logger.error(f"Invalid command: {command}. Valid options: {list(commands.keys())}")
            return False
        
        # First set EMS to forced mode
        if not self.set_ems_mode('forced'):
            return False
        
        # Set the command
        if not self.write_register('battery_forced_charge_discharge_cmd', commands[command]):
            return False
        
        # Set power if specified
        if power > 0:
            return self.write_register('battery_forced_charge_discharge_power', power)
            
        return True
    
    def set_soc_limits(self, min_soc: float, max_soc: float) -> bool:
        """Set battery SOC limits."""
        if not (0 <= min_soc <= 100) or not (0 <= max_soc <= 100):
            logger.error("SOC values must be between 0 and 100")
            return False
            
        if min_soc >= max_soc:
            logger.error("Min SOC must be less than Max SOC")
            return False
        
        min_success = self.write_register('min_soc', min_soc)
        max_success = self.write_register('max_soc', max_soc)
        
        return min_success and max_success
    
    def set_export_power_limit(self, limit: int, enable: bool = True) -> bool:
        """Set export power limit."""
        # Set the limit value
        limit_success = self.write_register('export_power_limit', limit)
        
        # Enable or disable the limit
        mode_value = 0xAA if enable else 0x55
        mode_success = self.write_register('export_power_limit_mode', mode_value)
        
        return limit_success and mode_success


def test_connection():
    """Test function to verify modbus connection and read some basic registers."""
    client = SungrowModbusClient()
    
    try:
        if client.connect():
            print("✅ Successfully connected to Sungrow inverter!")
            
            # Read a few test registers
            test_registers = ['active_power', 'daily_energy', 'total_energy']
            
            print("\n📊 Reading test registers:")
            for register in test_registers:
                value = client.read_register(register)
                if value is not None:
                    reg_info = client.get_register_info(register)
                    unit = reg_info.get('unit', '') if reg_info else ''
                    print(f"  {register}: {value} {unit}")
                else:
                    print(f"  {register}: Failed to read")
                    
        else:
            print("❌ Failed to connect to Sungrow inverter")
            print("Please check:")
            print("  - Network connection")
            print("  - IP address and port in config.yaml")
            print("  - Modbus proxy is running")
            
    except Exception as e:
        print(f"❌ Error during test: {e}")
        
    finally:
        client.disconnect()


if __name__ == "__main__":
    test_connection() 