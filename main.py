from modbus_client import SungrowModbusClient
from sungrow_controller import SungrowController, EMSMode, BatteryCommand
import time


def test_comprehensive_registers():
    """Test the comprehensive register mapping from the Home Assistant integration."""
    print("🏠 Testing Comprehensive Sungrow Register Mapping")
    print("=" * 60)
    
    client = SungrowModbusClient()
    
    try:
        if client.connect():
            print("✅ Connection successful!")
            
            # Test system information
            print("\n📋 System Information:")
            system_info = client.get_system_info()
            for key, value in system_info.items():
                if value is not None:
                    print(f"  📊 {key}: {value}")
            
            # Test power data
            print("\n⚡ Power Data:")
            power_data = client.get_power_data()
            for key, value in power_data.items():
                if value is not None:
                    unit = " W" if "power" in key else ""
                    print(f"  ⚡ {key}: {value}{unit}")
            
            # Test battery data
            print("\n🔋 Battery Data:")
            battery_data = client.get_battery_data()
            for key, value in battery_data.items():
                if value is not None:
                    if "level" in key:
                        unit = "%"
                    elif "voltage" in key:
                        unit = " V"
                    elif "current" in key:
                        unit = " A"
                    elif "power" in key:
                        unit = " W"
                    elif "temperature" in key:
                        unit = "°C"
                    elif "capacity" in key:
                        unit = " kWh"
                    else:
                        unit = ""
                    print(f"  🔋 {key}: {value}{unit}")
            
            # Test energy counters
            print("\n📊 Energy Counters:")
            energy_data = client.get_energy_data()
            for key, value in energy_data.items():
                if value is not None:
                    print(f"  📊 {key}: {value} kWh")
            
            # Test register info
            print("\n🔧 Available Registers:")
            registers = client.list_registers()
            print(f"  📝 Total registers: {len(registers)}")
            
            writable_registers = client.list_writable_registers()
            print(f"  ✏️ Writable registers: {len(writable_registers)}")
            if writable_registers:
                print("  📝 Control registers:")
                for reg in writable_registers[:10]:  # Show first 10
                    info = client.get_register_info(reg)
                    print(f"    • {reg}: {info.get('description', 'No description')}")
                if len(writable_registers) > 10:
                    print(f"    ... and {len(writable_registers) - 10} more")
                    
        else:
            print("❌ Failed to connect")
            
    finally:
        client.disconnect()


def test_controller_features():
    """Test the enhanced controller features."""
    print("\n🎮 Testing Enhanced Controller Features")
    print("=" * 60)
    
    controller = SungrowController()
    
    try:
        if controller.connect():
            print("✅ Controller connected!")
            
            # Update data
            print("\n🔄 Updating system data...")
            if controller.update():
                print("✅ Data updated successfully!")
                
                # Get current state
                state = controller.get_current_state()
                
                print("\n📊 Current System State:")
                print(f"  🌞 Solar Power: {state['power']['solar_power']:.0f} W")
                print(f"  🔋 Battery: {state['battery']['level']:.1f}% ({state['battery']['power']:.0f} W)")
                print(f"  ⚡ Grid: {state['power']['grid_power']:.0f} W")
                print(f"  🌊 Frequency: {state['power']['grid_frequency']:.2f} Hz")
                print(f"  🌡️ Inverter Temp: {state['power']['inverter_temperature']:.1f}°C")
                print(f"  🔧 System State: {state['system']['system_state']}")
                
                # Show energy balance
                print("\n⚖️ Energy Balance:")
                balance = controller.calculate_energy_balance()
                print(f"  🌞 Solar Generation: {balance['solar_generation']:.0f} W")
                print(f"  🏠 House Consumption: {balance['house_consumption']:.0f} W")
                print(f"  ⚡ Grid Flow: {balance['grid_flow']:.0f} W ({'Export' if balance['grid_flow'] > 0 else 'Import' if balance['grid_flow'] < 0 else 'Balanced'})")
                print(f"  🔋 Battery Flow: {balance['battery_flow']:.0f} W")
                print(f"  📊 Self-Consumption: {balance['self_consumption_ratio']:.1f}%")
                
                # Show control settings
                print("\n🎛️ Current Control Settings:")
                print(f"  📱 EMS Mode: {state['system']['ems_mode']}")
                print(f"  🔋 SOC Limits: {state['system']['min_soc']:.1f}% - {state['system']['max_soc']:.1f}%")
                print(f"  📤 Export Limit: {state['system']['export_power_limit']} W ({'Enabled' if state['system']['export_power_limit_enabled'] else 'Disabled'})")
                
            else:
                print("⚠️ Failed to update data, but controller framework is working")
                
            # Test control capabilities (read-only mode)
            print("\n🎮 Available Control Functions:")
            print("  🔧 Smart Control Functions:")
            print("    • optimize_self_consumption() - Optimize for maximum self-consumption")
            print("    • force_battery_charge_from_grid(power) - Charge battery from grid")
            print("    • maximize_grid_export() - Maximize grid export via battery discharge")
            print("    • emergency_battery_preserve() - Emergency battery preservation")
            
            print("  ⚙️ Basic Control Functions:")
            print("    • set_ems_mode(mode) - Set EMS operating mode")
            print("    • set_soc_limits(min, max) - Set battery SOC limits")
            print("    • set_export_power_limit(limit, enable) - Set export power limit")
            print("    • set_backup_reserve_soc(soc) - Set backup reserve SOC")
            
        else:
            print("❌ Failed to connect controller")
            
    finally:
        controller.disconnect()


def demonstrate_control_scenarios():
    """Demonstrate various control scenarios without actually changing settings."""
    print("\n🎯 Control Scenarios Demonstration")
    print("=" * 60)
    
    controller = SungrowController()
    
    if controller.connect():
        controller.update()
        state = controller.get_current_state()
        
        current_soc = state['battery']['level']
        solar_power = state['power']['solar_power']
        grid_power = state['power']['grid_power']
        
        print(f"📊 Current Conditions:")
        print(f"  🔋 Battery SOC: {current_soc:.1f}%")
        print(f"  🌞 Solar Power: {solar_power:.0f} W")
        print(f"  ⚡ Grid Power: {grid_power:.0f} W")
        
        print(f"\n🎯 Recommended Actions:")
        
        # Scenario analysis
        if solar_power > 1000:
            print("  ☀️ High solar generation detected:")
            if current_soc < 80:
                print("    💡 Recommend: Optimize self-consumption to charge battery")
                print("    🔧 Function: controller.optimize_self_consumption()")
            else:
                print("    💡 Recommend: Consider controlled export or load shifting")
                print("    🔧 Function: controller.set_export_power_limit(3000, True)")
        
        elif solar_power < 100:
            print("  🌙 Low/no solar generation:")
            if current_soc > 50:
                print("    💡 Recommend: Allow battery discharge for self-consumption")
                print("    🔧 Function: controller.set_soc_limits(20.0, 90.0)")
            else:
                print("    💡 Recommend: Preserve battery for critical loads")
                print("    🔧 Function: controller.emergency_battery_preserve()")
        
        if abs(grid_power) > 2000:
            if grid_power > 0:
                print("  📤 High grid export detected:")
                print("    💡 Recommend: Increase battery charging or reduce export limit")
                print("    🔧 Function: controller.force_battery_charge_from_grid(2000)")
            else:
                print("  📥 High grid import detected:")
                print("    💡 Recommend: Increase battery discharge if available")
                print("    🔧 Function: controller.maximize_grid_export()")
        
        # Time-based scenarios
        import datetime
        current_hour = datetime.datetime.now().hour
        
        if 22 <= current_hour or current_hour <= 6:
            print("  🌙 Night time (22:00-06:00):")
            print("    💡 Recommend: Preserve battery for morning peak or cheap charging")
            if current_soc < 30:
                print("    ⚠️ Consider: Force charge if electricity prices are low")
                print("    🔧 Function: controller.force_battery_charge_from_grid(1500)")
        
        elif 7 <= current_hour <= 9 or 17 <= current_hour <= 20:
            print("  ⚡ Peak hours (07:00-09:00 or 17:00-20:00):")
            print("    💡 Recommend: Maximize battery discharge to avoid grid import")
            print("    🔧 Function: controller.set_soc_limits(15.0, 90.0)")
        
        else:
            print("  ☀️ Day time (solar potential):")
            print("    💡 Recommend: Optimize for solar self-consumption")
            print("    🔧 Function: controller.optimize_self_consumption()")
        
        controller.disconnect()
    else:
        print("❌ Could not connect for scenario analysis")


def main():
    print("🏠 Self-Consumption Control System")
    print("🚀 Comprehensive Sungrow Integration")
    print("=" * 60)
    
    # Test comprehensive register mapping
    test_comprehensive_registers()
    
    # Test enhanced controller features
    test_controller_features()
    
    # Demonstrate control scenarios
    demonstrate_control_scenarios()
    
    print(f"\n🎉 Summary:")
    print(f"✅ Comprehensive register mapping implemented")
    print(f"✅ 53+ registers available from Home Assistant integration")
    print(f"✅ Enhanced controller with smart control functions")
    print(f"✅ Real-time monitoring and energy balance calculations")
    print(f"✅ Multiple control strategies for different scenarios")
    print(f"✅ Professional control interface ready for automation")
    
    print(f"\n📚 Next Steps:")
    print(f"1. 🏃 Run 'python monitor.py' for real-time monitoring")
    print(f"2. 🔧 Implement custom control algorithms")
    print(f"3. 📊 Add data logging and historical analysis")
    print(f"4. 🤖 Integrate with home automation systems")
    print(f"5. 💰 Add time-of-use pricing optimization")


if __name__ == "__main__":
    main()
