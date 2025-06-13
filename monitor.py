#!/usr/bin/env python3
"""
Enhanced Real-time Sungrow Inverter Monitor
Thermodynamically correct energy balance with comprehensive statistics
"""

import time
import signal
import sys
import os
from collections import deque, defaultdict
import statistics
import math
from sungrow_controller import SungrowController


class EnhancedSungrowMonitor:
    def __init__(self, update_frequency=2.0):  # 2 Hz - realistic for Modbus TCP
        self.controller = SungrowController()
        self.running = False
        self.update_frequency = update_frequency
        self.update_interval = 1.0 / update_frequency  # 0.5 seconds for 2 Hz
        
        # Enhanced data storage for statistics  
        self.data_history = defaultdict(lambda: deque(maxlen=60))   # 30 seconds at 2 Hz
        self.long_history = defaultdict(lambda: deque(maxlen=600))  # 5 minutes at 2 Hz
        
        # Statistics tracking
        self.stats_window = 20  # Last 10 seconds for real-time stats (20 samples at 2 Hz)
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
    
    def signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        print("\n🛑 Shutdown signal received. Stopping monitor...")
        self.running = False
    
    def format_power(self, watts):
        """Format power values with appropriate units."""
        if abs(watts) >= 1000:
            return f"{watts/1000:.2f} kW"
        else:
            return f"{watts:.0f} W"
    
    def format_energy(self, kwh):
        """Format energy values."""
        if kwh >= 1000:
            return f"{kwh/1000:.2f} MWh"
        else:
            return f"{kwh:.2f} kWh"
    
    def calculate_statistics(self, data_key):
        """Calculate comprehensive statistics for a data series."""
        if data_key not in self.data_history or len(self.data_history[data_key]) < 2:
            return {
                'current': 0, 'avg': 0, 'max': 0, 'min': 0, 
                'std_dev': 0, 'range': 0, 'trend': 0
            }
        
        data = list(self.data_history[data_key])
        recent_data = data[-min(self.stats_window, len(data)):]
        
        current = data[-1] if data else 0
        avg = statistics.mean(recent_data)
        max_val = max(recent_data)
        min_val = min(recent_data)
        std_dev = statistics.stdev(recent_data) if len(recent_data) > 1 else 0
        range_val = max_val - min_val
        
        # Calculate trend (slope of last 20 points)
        trend = 0
        if len(recent_data) >= 20:
            x = list(range(len(recent_data[-20:])))
            y = recent_data[-20:]
            n = len(x)
            sum_x = sum(x)
            sum_y = sum(y)
            sum_xy = sum(x[i] * y[i] for i in range(n))
            sum_x2 = sum(x[i] * x[i] for i in range(n))
            
            if n * sum_x2 - sum_x * sum_x != 0:
                trend = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x * sum_x)
                trend *= self.update_frequency  # Scale to per-second trend
        
        return {
            'current': current,
            'avg': avg,
            'max': max_val,
            'min': min_val,
            'std_dev': std_dev,
            'range': range_val,
            'trend': trend
        }
    
    def get_ems_mode_description(self, mode_value):
        """Get human-readable EMS mode description."""
        mode_map = {
            0: "Self Consumption",
            1: "Forced Time",
            2: "Backup Mode",
            3: "Feed-in Priority",
            4: "Off-Grid Mode",
            5: "External EMS"
        }
        return mode_map.get(mode_value, f"Unknown ({mode_value})")
    
    def display_thermodynamic_balance(self, stats):
        """Display thermodynamically correct energy balance equation with clear sign conventions."""
        print("\n" + "="*80)
        print("🌡️  THERMODYNAMIC ENERGY BALANCE - SITE BOUNDARY")
        print("="*80)
        
        # Site boundary components with clear sign conventions
        P_sun = stats['solar_power']['current']          # Always positive (generation)
        P_grid = stats['grid_power']['current']         # + = export, - = import  
        P_batt = stats['battery_power']['current']      # + = charging, - = discharging
        
        # Calculate house load from energy balance: P_grid = P_sun - P_load - P_batt
        # Rearranged: P_load = P_sun - P_batt - P_grid
        P_load = P_sun - P_batt - P_grid
        
        print(f"📊 SIGN CONVENTIONS:")
        print(f"   P_sun  > 0: Solar generation     | P_batt > 0: Battery charging")
        print(f"   P_grid > 0: Grid export          | P_batt < 0: Battery discharging") 
        print(f"   P_grid < 0: Grid import          | P_load > 0: House consumption")
        
        print(f"\n⚖️  FUNDAMENTAL ENERGY BALANCE:")
        print(f"   P_grid = P_sun - P_load - P_batt")
        
        # Show with actual values and clear signs
        batt_sign = "+" if P_batt >= 0 else ""
        grid_sign = "+" if P_grid >= 0 else ""
        load_sign = "+" if P_load >= 0 else ""
        
        print(f"   {grid_sign}{self.format_power(P_grid)} = {self.format_power(P_sun)} - {self.format_power(P_load)} - ({batt_sign}{self.format_power(P_batt)})")
        
        # Verification
        calculated_grid = P_sun - P_load - P_batt
        balance_error = abs(P_grid - calculated_grid)
        
        print(f"   Verification: {self.format_power(P_grid)} ≈ {self.format_power(calculated_grid)} (Error: {self.format_power(balance_error)})")
        
        # Energy flows with clear descriptions
        print(f"\n🔄 ENERGY FLOWS:")
        print(f"   🌞 Solar Generation:    {self.format_power(P_sun):>10}")
        print(f"   🏠 House Consumption:   {self.format_power(P_load):>10}")
        
        # Battery status with clear direction
        if P_batt > 10:
            batt_status = f"Charging at {self.format_power(P_batt)}"
        elif P_batt < -10:
            batt_status = f"Discharging at {self.format_power(-P_batt)}"
        else:
            batt_status = "Idle"
        print(f"   🔋 Battery Flow:        {self.format_power(P_batt):>10} ({batt_status})")
        
        # Grid status with clear direction
        if P_grid > 10:
            grid_status = f"Exporting {self.format_power(P_grid)}"
        elif P_grid < -10:
            grid_status = f"Importing {self.format_power(-P_grid)}"
        else:
            grid_status = "Balanced"
        print(f"   ⚡ Grid Flow:           {self.format_power(P_grid):>10} ({grid_status})")
        
        # Efficiency metrics
        if P_sun > 0:
            grid_export = max(0, P_grid)
            self_consumption_ratio = min(100, (P_sun - grid_export) / P_sun * 100)
            print(f"   📈 Self-Consumption:    {self_consumption_ratio:>9.1f}%")
        
        if P_load > 0:
            solar_coverage = min(100, P_sun / P_load * 100)
            print(f"   ☀️ Solar Coverage:      {solar_coverage:>9.1f}%")
    
    def display_enhanced_statistics_table(self, stats, system_info):
        """Display enhanced statistics table with comprehensive metrics."""
        print("\n" + "="*120)
        print("📊 COMPREHENSIVE SYSTEM STATISTICS")
        print("="*120)
        
        # Header
        print(f"│ {'Parameter':<20} │ {'Current':<12} │ {'Average':<12} │ {'Max':<12} │ {'Min':<12} │ {'Std Dev':<10} │ {'Range':<12} │ {'Trend/s':<10} │")
        print("├" + "─"*21 + "┼" + "─"*13 + "┼" + "─"*13 + "┼" + "─"*13 + "┼" + "─"*13 + "┼" + "─"*11 + "┼" + "─"*13 + "┼" + "─"*11 + "┤")
        
        # Power parameters
        power_params = [
            ('Solar Power', 'solar_power', 'W'),
            ('Battery Power', 'battery_power', 'W'),
            ('Grid Power', 'grid_power', 'W'),
            ('House Load', 'house_load', 'W'),
        ]
        
        for name, key, unit in power_params:
            s = stats.get(key, {})
            current = s.get('current', 0)
            avg = s.get('avg', 0)
            max_val = s.get('max', 0)
            min_val = s.get('min', 0)
            std_dev = s.get('std_dev', 0)
            range_val = s.get('range', 0)
            trend = s.get('trend', 0)
            
            print(f"│ {name:<20} │ {self.format_power(current):>11} │ {self.format_power(avg):>11} │ {self.format_power(max_val):>11} │ {self.format_power(min_val):>11} │ {std_dev:>9.1f}W │ {self.format_power(range_val):>11} │ {trend:>+9.1f}W │")
        
        print("├" + "─"*21 + "┼" + "─"*13 + "┼" + "─"*13 + "┼" + "─"*13 + "┼" + "─"*13 + "┼" + "─"*11 + "┼" + "─"*13 + "┼" + "─"*11 + "┤")
        
        # System parameters
        system_params = [
            ('Battery SOC', 'battery_soc', '%'),
            ('Grid Frequency', 'grid_frequency', 'Hz'),
            ('Inverter Temp', 'inverter_temp', '°C'),
        ]
        
        for name, key, unit in system_params:
            s = stats.get(key, {})
            current = s.get('current', 0)
            avg = s.get('avg', 0)
            max_val = s.get('max', 0)
            min_val = s.get('min', 0)
            std_dev = s.get('std_dev', 0)
            range_val = s.get('range', 0)
            trend = s.get('trend', 0)
            
            if unit == '%':
                print(f"│ {name:<20} │ {current:>10.1f}% │ {avg:>10.1f}% │ {max_val:>10.1f}% │ {min_val:>10.1f}% │ {std_dev:>9.2f}% │ {range_val:>10.1f}% │ {trend:>+8.3f}%/s │")
            elif unit == 'Hz':
                print(f"│ {name:<20} │ {current:>10.2f}Hz │ {avg:>10.2f}Hz │ {max_val:>10.2f}Hz │ {min_val:>10.2f}Hz │ {std_dev:>8.3f}Hz │ {range_val:>10.3f}Hz │ {trend:>+7.4f}Hz/s │")
            elif unit == '°C':
                print(f"│ {name:<20} │ {current:>10.1f}°C │ {avg:>10.1f}°C │ {max_val:>10.1f}°C │ {min_val:>10.1f}°C │ {std_dev:>8.2f}°C │ {range_val:>10.1f}°C │ {trend:>+7.3f}°C/s │")
        
        print("└" + "─"*21 + "┴" + "─"*13 + "┴" + "─"*13 + "┴" + "─"*13 + "┴" + "─"*13 + "┴" + "─"*11 + "┴" + "─"*13 + "┴" + "─"*11 + "┘")
        
        # System status
        print(f"\n🎛️  SYSTEM STATUS:")
        ems_mode = system_info.get('ems_mode', 0)
        ems_description = self.get_ems_mode_description(ems_mode)
        print(f"   • EMS Mode: {ems_description}")
        print(f"   • System State: {system_info.get('system_state', 'Unknown')}")
        print(f"   • Running State: {system_info.get('running_state', 'Unknown')}")
        print(f"   • Update Rate: {1/self.update_interval:.1f} Hz")
        print(f"   • Data Points: {len(self.data_history.get('solar_power', []))}/300 (last 30s)")
    
    def run(self):
        """Main monitoring loop with enhanced statistics."""
        if not self.controller.connect():
            print("❌ Failed to connect to Sungrow inverter")
            return
        
        print(f"🔌 Connected to Sungrow inverter. Starting enhanced monitoring at {1/self.update_interval:.1f} Hz...")
        time.sleep(1)
        
        self.running = True
        
        try:
            while self.running:
                start_time = time.time()
                
                # Read current data
                self.controller.update()
                nested_data = self.controller.get_current_state()
                
                # Flatten and calculate derived values
                current_data = {
                    'solar_power': nested_data['power'].get('solar_power', 0),
                    'battery_power': nested_data['power'].get('battery_power', 0),  # + = charging, - = discharging
                    'grid_power': nested_data['power'].get('grid_power', 0),  # + = import, - = export
                    'battery_soc': nested_data['battery'].get('level', 0),
                    'grid_frequency': nested_data['power'].get('grid_frequency', 0),
                    'inverter_temp': nested_data['power'].get('inverter_temperature', 0),
                    'ems_mode': nested_data['system'].get('ems_mode', 0),
                    'system_state': nested_data['system'].get('system_state', 'Unknown'),
                    'running_state': nested_data['system'].get('running_state', 0),
                }
                
                # Calculate house load from energy balance
                solar = current_data['solar_power']
                grid = current_data['grid_power']
                battery = current_data['battery_power']
                
                grid_import = max(0, grid)
                grid_export = max(0, -grid)
                battery_charge = max(0, battery)
                battery_discharge = max(0, -battery)
                
                house_load = solar + grid_import - battery_charge + battery_discharge - grid_export
                current_data['house_load'] = house_load
                
                # Store data in history
                timestamp = time.time()
                for key, value in current_data.items():
                    if isinstance(value, (int, float)):
                        self.data_history[key].append(value)
                        self.long_history[key].append((timestamp, value))
                
                # Calculate statistics for all parameters
                stats = {}
                for key in ['solar_power', 'battery_power', 'grid_power', 'house_load', 
                           'battery_soc', 'grid_frequency', 'inverter_temp']:
                    stats[key] = self.calculate_statistics(key)
                
                # Clear screen and display
                os.system('clear' if os.name == 'posix' else 'cls')
                
                print("🏠 ENHANCED SUNGROW MONITOR - THERMODYNAMIC ANALYSIS")
                print(f"⏰ {time.strftime('%Y-%m-%d %H:%M:%S')} | Update Rate: {1/self.update_interval:.1f} Hz")
                
                # Display thermodynamic balance
                self.display_thermodynamic_balance(stats)
                
                # Display enhanced statistics table
                system_info = {
                    'ems_mode': current_data['ems_mode'],
                    'system_state': current_data['system_state'],
                    'running_state': current_data['running_state']
                }
                self.display_enhanced_statistics_table(stats, system_info)
                
                # Maintain update frequency
                elapsed = time.time() - start_time
                sleep_time = max(0, self.update_interval - elapsed)
                if sleep_time > 0:
                    time.sleep(sleep_time)
                
        except KeyboardInterrupt:
            print("\n🛑 Monitoring stopped by user")
        except Exception as e:
            print(f"\n❌ Error during monitoring: {e}")
        finally:
            self.controller.disconnect()
            print("🔌 Disconnected from inverter")


def main():
    print("🏠 Enhanced Sungrow Monitor")
    print("🌡️ Thermodynamically Correct Energy Balance Analysis")
    print("📊 Real-Time Statistics at 2 Hz (Realistic Modbus TCP Rate)")
    print("=" * 60)
    
    monitor = EnhancedSungrowMonitor(update_frequency=2.0)  # 2 Hz - realistic for Modbus
    monitor.run()


if __name__ == "__main__":
    main() 