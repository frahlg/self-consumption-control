"""
Sungrow Controller - Adapted from SungrowDeeDecoder for modbus control systems.
Handles battery, solar, and grid power management.
"""

from modbus_client import SungrowModbusClient
import logging
import time
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class EMSMode(Enum):
    """EMS operating modes."""
    SELF_CONSUMPTION = 0
    FORCED = 2
    EXTERNAL_EMS = 3


class BatteryCommand(Enum):
    """Battery forced charge/discharge commands."""
    STOP = 0xCC
    CHARGE = 0xAA
    DISCHARGE = 0xBB


class SystemState(Enum):
    """System state codes."""
    RUNNING = 0x0000
    RUNNING_ALT = 0x0040
    OFF_GRID_CHARGE = 0x0410
    UPDATE_FAILED = 0x0200
    MAINTAIN_MODE = 0x0400
    FORCED_MODE = 0x0800
    OFF_GRID_MODE = 0x1000
    UNINITIALIZED = 0x1111
    INITIAL_STANDBY = 0x0010
    INITIAL_STANDBY_ALT = 0x12000
    SHUTDOWN = 0x1300
    SHUTDOWN_ALT = 0x0002
    STANDBY = 0x1400
    STANDBY_ALT = 0x0008
    EMERGENCY_STOP = 0x1500
    EMERGENCY_STOP_ALT = 0x0004
    STARTUP = 0x1600
    STARTUP_ALT = 0x0020
    AFCI_SELF_TEST = 0x1700
    INTELLIGENT_STATION = 0x1800
    SAFE_MODE = 0x1900
    OPEN_LOOP = 0x2000
    RESTARTING = 0x2501
    EXTERNAL_EMS_MODE = 0x4000
    EMERGENCY_BATTERY_CHARGING = 0x4001
    FAULT = 0x5500
    FAULT_ALT = 0x0100
    STOP = 0x8000
    STOP_ALT = 0x0001
    DERATING_RUNNING = 0x8100
    DERATING_RUNNING_ALT = 0x0080
    DISPATCH_RUN = 0x8200
    WARN_RUNNING = 0x9100


@dataclass
class PowerData:
    """Power measurements data structure."""
    solar_power: float = 0.0      # DC power from solar panels (W)
    grid_power: float = 0.0       # Grid power (+ = export, - = import) (W)
    load_power: float = 0.0       # House load consumption (W)
    battery_power: float = 0.0    # Battery power (+ = charge, - = discharge) (W)
    total_power: float = 0.0      # Total AC power output (W)
    
    # Phase data
    phase_a_voltage: float = 0.0
    phase_b_voltage: float = 0.0
    phase_c_voltage: float = 0.0
    phase_a_current: float = 0.0
    phase_b_current: float = 0.0
    phase_c_current: float = 0.0
    
    # Environmental
    grid_frequency: float = 0.0
    inverter_temperature: float = 0.0


@dataclass
class BatteryData:
    """Battery data structure."""
    level: float = 0.0            # SOC (%)
    voltage: float = 0.0          # Battery voltage (V)
    current: float = 0.0          # Battery current (A)
    power: float = 0.0            # Battery power (W)
    temperature: float = 0.0      # Battery temperature (°C)
    state_of_health: float = 0.0  # SOH (%)
    capacity: float = 0.0         # Battery capacity (kWh)
    
    # Charging state (derived from running_state register)
    is_charging: bool = False
    is_discharging: bool = False


@dataclass
class EnergyData:
    """Energy counters data structure."""
    # Daily counters
    daily_pv_generation: float = 0.0
    daily_imported_energy: float = 0.0
    daily_exported_energy: float = 0.0
    daily_battery_charge: float = 0.0
    daily_battery_discharge: float = 0.0
    
    # Total counters
    total_pv_generation: float = 0.0
    total_imported_energy: float = 0.0
    total_exported_energy: float = 0.0
    total_battery_charge: float = 0.0
    total_battery_discharge: float = 0.0


@dataclass
class SystemInfo:
    """System information data structure."""
    inverter_serial: str = ""
    device_type_code: int = 0
    system_state: int = 0
    running_state: int = 0
    system_state_text: str = ""
    
    # Control settings
    ems_mode: int = 0
    min_soc: float = 0.0
    max_soc: float = 0.0
    export_power_limit: int = 0
    export_power_limit_enabled: bool = False


class SungrowController:
    """
    Enhanced Sungrow inverter controller using the comprehensive register mapping
    from the Home Assistant integration.
    """
    
    def __init__(self, config_file: str = "config.yaml"):
        """Initialize the Sungrow controller."""
        self.client = SungrowModbusClient(config_file)
        self.connected = False
        
        # Control parameters
        self.grid_power_limit = 5000  # W
        self.battery_max_charge_discharge_power = 5000  # W
        self.min_battery_soc = 10.0  # %
        self.max_battery_soc = 90.0  # %
        
        # Data storage
        self.power_data = PowerData()
        self.battery_data = BatteryData()
        self.energy_data = EnergyData()
        self.system_info = SystemInfo()
        
    def connect(self) -> bool:
        """Connect to the Sungrow inverter."""
        self.connected = self.client.connect()
        return self.connected
    
    def disconnect(self):
        """Disconnect from the Sungrow inverter."""
        self.client.disconnect()
        self.connected = False
    
    def update(self) -> bool:
        """Update all data from the inverter."""
        if not self.connected:
            logger.error("Controller not connected")
            return False
        
        try:
            # Update all data categories
            self._update_power_data()
            self._update_battery_data()
            self._update_energy_data()
            self._update_system_info()
            
            return True
            
        except Exception as e:
            logger.error(f"Error updating data: {e}")
            return False
    
    def _update_power_data(self):
        """Update power measurements."""
        data = self.client.get_power_data()
        
        self.power_data.solar_power = data.get('total_dc_power', 0.0) or 0.0
        self.power_data.total_power = data.get('total_active_power', 0.0) or 0.0
        self.power_data.load_power = data.get('load_power', 0.0) or 0.0
        
        # Grid power (export_power_raw: + = export, - = import)
        export_power = data.get('export_power_raw', 0.0) or 0.0
        self.power_data.grid_power = export_power
        
        # Battery power (raw value, sign depends on firmware)
        battery_raw = data.get('battery_power_raw', 0.0) or 0.0
        self.power_data.battery_power = battery_raw
        
        # Get additional measurements
        system_data = self.client.get_system_info()
        self.power_data.grid_frequency = system_data.get('grid_frequency', 0.0) or 0.0
        self.power_data.inverter_temperature = system_data.get('inverter_temperature', 0.0) or 0.0
        
        # Phase voltages and currents
        phase_data = self.client.read_multiple_registers([
            'phase_a_voltage', 'phase_b_voltage', 'phase_c_voltage',
            'phase_a_current', 'phase_b_current', 'phase_c_current'
        ])
        
        self.power_data.phase_a_voltage = phase_data.get('phase_a_voltage', 0.0) or 0.0
        self.power_data.phase_b_voltage = phase_data.get('phase_b_voltage', 0.0) or 0.0
        self.power_data.phase_c_voltage = phase_data.get('phase_c_voltage', 0.0) or 0.0
        self.power_data.phase_a_current = phase_data.get('phase_a_current', 0.0) or 0.0
        self.power_data.phase_b_current = phase_data.get('phase_b_current', 0.0) or 0.0
        self.power_data.phase_c_current = phase_data.get('phase_c_current', 0.0) or 0.0
    
    def _update_battery_data(self):
        """Update battery measurements."""
        data = self.client.get_battery_data()
        
        self.battery_data.level = data.get('battery_level', 0.0) or 0.0
        self.battery_data.voltage = data.get('battery_voltage', 0.0) or 0.0
        self.battery_data.current = data.get('battery_current', 0.0) or 0.0
        self.battery_data.power = data.get('battery_power_raw', 0.0) or 0.0
        self.battery_data.temperature = data.get('battery_temperature', 0.0) or 0.0
        self.battery_data.state_of_health = data.get('battery_state_of_health', 0.0) or 0.0
        self.battery_data.capacity = data.get('battery_capacity', 0.0) or 0.0
        
        # Determine charging/discharging state from running_state
        running_state = self.client.read_register('running_state')
        if running_state is not None:
            # Bit 1: Charging, Bit 2: Discharging
            self.battery_data.is_charging = bool(running_state & 0x2)
            self.battery_data.is_discharging = bool(running_state & 0x4)
        else:
            # Fallback: determine from current
            if self.battery_data.current > 0.1:
                self.battery_data.is_charging = True
                self.battery_data.is_discharging = False
            elif self.battery_data.current < -0.1:
                self.battery_data.is_charging = False
                self.battery_data.is_discharging = True
            else:
                self.battery_data.is_charging = False
                self.battery_data.is_discharging = False
    
    def _update_energy_data(self):
        """Update energy counters."""
        data = self.client.get_energy_data()
        
        # Daily counters
        self.energy_data.daily_pv_generation = data.get('daily_pv_generation', 0.0) or 0.0
        self.energy_data.daily_imported_energy = data.get('daily_imported_energy', 0.0) or 0.0
        self.energy_data.daily_exported_energy = data.get('daily_exported_energy', 0.0) or 0.0
        self.energy_data.daily_battery_charge = data.get('daily_battery_charge', 0.0) or 0.0
        self.energy_data.daily_battery_discharge = data.get('daily_battery_discharge', 0.0) or 0.0
        
        # Total counters
        self.energy_data.total_pv_generation = data.get('total_pv_generation', 0.0) or 0.0
        self.energy_data.total_imported_energy = data.get('total_imported_energy', 0.0) or 0.0
        self.energy_data.total_exported_energy = data.get('total_exported_energy', 0.0) or 0.0
        self.energy_data.total_battery_charge = data.get('total_battery_charge', 0.0) or 0.0
        self.energy_data.total_battery_discharge = data.get('total_battery_discharge', 0.0) or 0.0
    
    def _update_system_info(self):
        """Update system information."""
        data = self.client.get_system_info()
        
        self.system_info.inverter_serial = data.get('inverter_serial', '') or ''
        self.system_info.device_type_code = data.get('device_type_code', 0) or 0
        self.system_info.system_state = data.get('system_state', 0) or 0
        self.system_info.running_state = data.get('running_state', 0) or 0
        
        # Convert system state to text
        self.system_info.system_state_text = self._get_system_state_text(self.system_info.system_state)
        
        # Read control settings
        control_data = self.client.read_multiple_registers([
            'ems_mode_selection', 'min_soc', 'max_soc', 
            'export_power_limit', 'export_power_limit_mode'
        ])
        
        self.system_info.ems_mode = control_data.get('ems_mode_selection', 0) or 0
        self.system_info.min_soc = control_data.get('min_soc', 0.0) or 0.0
        self.system_info.max_soc = control_data.get('max_soc', 0.0) or 0.0
        self.system_info.export_power_limit = control_data.get('export_power_limit', 0) or 0
        
        limit_mode = control_data.get('export_power_limit_mode', 0) or 0
        self.system_info.export_power_limit_enabled = (limit_mode == 0xAA)
    
    def _get_system_state_text(self, state_code: int) -> str:
        """Convert system state code to readable text."""
        try:
            state = SystemState(state_code)
            return state.name.replace('_', ' ').title()
        except ValueError:
            return f"Unknown State (0x{state_code:04X})"
    
    def get_current_state(self) -> Dict[str, Any]:
        """Get current system state as a dictionary."""
        return {
            'power': {
                'solar_power': self.power_data.solar_power,
                'grid_power': self.power_data.grid_power,
                'load_power': self.power_data.load_power,
                'battery_power': self.power_data.battery_power,
                'total_power': self.power_data.total_power,
                'grid_frequency': self.power_data.grid_frequency,
                'inverter_temperature': self.power_data.inverter_temperature,
            },
            'battery': {
                'level': self.battery_data.level,
                'voltage': self.battery_data.voltage,
                'current': self.battery_data.current,
                'power': self.battery_data.power,
                'temperature': self.battery_data.temperature,
                'state_of_health': self.battery_data.state_of_health,
                'capacity': self.battery_data.capacity,
                'is_charging': self.battery_data.is_charging,
                'is_discharging': self.battery_data.is_discharging,
            },
            'energy': {
                'daily_pv_generation': self.energy_data.daily_pv_generation,
                'daily_imported_energy': self.energy_data.daily_imported_energy,
                'daily_exported_energy': self.energy_data.daily_exported_energy,
                'daily_battery_charge': self.energy_data.daily_battery_charge,
                'daily_battery_discharge': self.energy_data.daily_battery_discharge,
            },
            'system': {
                'inverter_serial': self.system_info.inverter_serial,
                'system_state': self.system_info.system_state_text,
                'running_state': self.system_info.running_state,
                'ems_mode': self.system_info.ems_mode,
                'min_soc': self.system_info.min_soc,
                'max_soc': self.system_info.max_soc,
                'export_power_limit': self.system_info.export_power_limit,
                'export_power_limit_enabled': self.system_info.export_power_limit_enabled,
            }
        }
    
    # Control Methods
    def set_ems_mode(self, mode: EMSMode) -> bool:
        """Set EMS operating mode."""
        return self.client.write_register('ems_mode_selection', mode.value)
    
    def set_battery_forced_charge(self, power: int = 0) -> bool:
        """Enable forced battery charging."""
        return self.client.set_battery_forced_mode('charge', power)
    
    def set_battery_forced_discharge(self, power: int = 0) -> bool:
        """Enable forced battery discharging."""
        return self.client.set_battery_forced_mode('discharge', power)
    
    def stop_battery_forced_mode(self) -> bool:
        """Stop forced battery charge/discharge."""
        return self.client.set_battery_forced_mode('stop')
    
    def set_self_consumption_mode(self) -> bool:
        """Set to self-consumption mode (normal operation)."""
        return self.client.set_ems_mode('self_consumption')
    
    def set_soc_limits(self, min_soc: float, max_soc: float) -> bool:
        """Set battery SOC limits."""
        return self.client.set_soc_limits(min_soc, max_soc)
    
    def set_export_power_limit(self, limit: int, enable: bool = True) -> bool:
        """Set export power limit."""
        return self.client.set_export_power_limit(limit, enable)
    
    def enable_backup_mode(self) -> bool:
        """Enable backup mode."""
        return self.client.write_register('backup_mode', 0xAA)
    
    def disable_backup_mode(self) -> bool:
        """Disable backup mode."""
        return self.client.write_register('backup_mode', 0x55)
    
    def set_backup_reserve_soc(self, soc: float) -> bool:
        """Set reserved SOC for backup mode."""
        if not (0 <= soc <= 100):
            logger.error("SOC must be between 0 and 100")
            return False
        return self.client.write_register('reserved_soc_for_backup', int(soc))
    
    # Smart Control Functions
    def optimize_self_consumption(self) -> bool:
        """
        Optimize for maximum self-consumption.
        - Switch to self-consumption mode
        - Allow battery discharge when needed
        - Set reasonable SOC limits
        """
        logger.info("🎯 Optimizing for self-consumption")
        
        success = True
        success &= self.set_self_consumption_mode()
        success &= self.set_soc_limits(10.0, 90.0)  # Allow good range
        
        if success:
            logger.info("✅ Self-consumption optimization applied")
        else:
            logger.error("❌ Failed to apply self-consumption optimization")
            
        return success
    
    def force_battery_charge_from_grid(self, power: int = 2000) -> bool:
        """
        Force battery charging from grid (useful during cheap energy periods).
        """
        logger.info(f"🔌 Forcing battery charge from grid at {power}W")
        
        success = self.client.set_battery_forced_mode('charge', power)
        
        if success:
            logger.info("✅ Forced battery charging enabled")
        else:
            logger.error("❌ Failed to enable forced battery charging")
            
        return success
    
    def maximize_grid_export(self) -> bool:
        """
        Maximize grid export by forcing battery discharge.
        """
        logger.info("📤 Maximizing grid export")
        
        success = self.client.set_battery_forced_mode('discharge', 3000)
        
        if success:
            logger.info("✅ Grid export maximization enabled")
        else:
            logger.error("❌ Failed to enable grid export maximization")
            
        return success
    
    def emergency_battery_preserve(self) -> bool:
        """
        Emergency mode: preserve battery by setting high minimum SOC.
        """
        logger.info("🚨 Emergency battery preservation mode")
        
        success = True
        success &= self.set_self_consumption_mode()
        success &= self.set_soc_limits(80.0, 90.0)  # High minimum to preserve battery
        
        if success:
            logger.info("✅ Emergency battery preservation enabled")
        else:
            logger.error("❌ Failed to enable emergency preservation")
            
        return success
    
    def calculate_energy_balance(self) -> Dict[str, float]:
        """Calculate current energy balance."""
        solar = self.power_data.solar_power
        grid = self.power_data.grid_power  # + = export, - = import
        battery = self.power_data.battery_power
        load = self.power_data.load_power
        
        # Calculate house consumption
        # Energy balance: Solar = Load + Battery_charge + Grid_export
        if grid >= 0:  # Exporting
            house_consumption = solar - abs(battery) - grid
        else:  # Importing
            house_consumption = solar + abs(grid) - abs(battery)
        
        return {
            'solar_generation': solar,
            'house_consumption': max(0, house_consumption),  # Can't be negative
            'grid_flow': grid,  # + = export, - = import
            'battery_flow': battery,  # + = charge, - = discharge
            'self_consumption_ratio': min(100, (house_consumption / solar * 100)) if solar > 0 else 0
        }


def test_controller():
    """Test the controller functionality."""
    controller = SungrowController()
    
    try:
        if controller.connect():
            print("🎮 Sungrow Controller Test (Corrected Registers)")
            print("=" * 50)
            
            # Get current state
            data = controller.update()
            
            if data:
                print("\n📊 Current System State:")
                state = controller.get_current_state()
                
                print(f"🌞 Solar Power: {state['power']['solar_power']:.0f} W")
                print(f"🔋 Battery Power: {state['power']['battery_power']:.0f} W "
                      f"({'Charging' if state['battery']['is_charging'] else 'Discharging' if state['battery']['is_discharging'] else 'Idle'})")
                print(f"🔋 Battery SOC: {state['battery']['level']:.1f}%")
                print(f"⚡ Grid Power: {state['power']['grid_power']:.0f} W "
                      f"({'Exporting' if state['power']['grid_power'] > 0 else 'Importing' if state['power']['grid_power'] < 0 else 'Balanced'})")
                print(f"🌊 Grid Frequency: {state['power']['grid_frequency']:.2f} Hz")
                print(f"🔧 Running State: {state['system']['system_state']}")
                
                print("\n🔋 Battery Capabilities:")
                battery_caps = controller.get_available_battery_power()
                print(f"  Max Charge: {battery_caps['max_charge_power']} W")
                print(f"  Max Discharge: {battery_caps['max_discharge_power']} W")
                
                print("\n📋 Detailed Data:")
                for key, value in state.items():
                    if key != '_calculate_derived_values':
                        print(f"  {key}: {value}")
                        
            else:
                print("❌ Failed to read controller data")
                
        else:
            print("❌ Failed to connect to controller")
            
    except Exception as e:
        print(f"❌ Controller test error: {e}")
        
    finally:
        controller.disconnect()


if __name__ == "__main__":
    test_controller() 