#!/usr/bin/env python3
"""
Async Enhanced Sungrow Monitor
Producer-Consumer architecture with Rich Live UI at 5fps.
"""

import asyncio
from telemetry import create_telemetry_system
from simple_live_monitor import SimpleEnergyMonitor


async def main():
    """Enhanced async monitor with producer-consumer UI architecture."""
    
    # Create telemetry system
    print("🔧 Initializing enhanced energy management system...")
    collector = await create_telemetry_system()
    
    # Create and run simple monitor (fixed version without Rich Live hanging)
    monitor = SimpleEnergyMonitor(collector) 
    await monitor.run()
    
    print("\n✅ Enhanced monitor stopped gracefully")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")


# Legacy compatibility class (deprecated)
class AsyncSungrowMonitor:
    """Enhanced async monitor that gets all data from telemetry queue and uses ring buffers."""
    
    def __init__(self, telemetry_collector: TelemetryCollector):
        self.collector = telemetry_collector
        self.running = False
        
        # Get ring buffer info for statistics window sizing
        buffer_info = self.collector.get_buffer_info()
        self.sample_rate = buffer_info['sample_rate']
        self.stats_window = int(10 * self.sample_rate)  # 10 seconds for real-time stats
        
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
    
    def calculate_statistics(self, data_key: str) -> Dict[str, float]:
        """
        Calculate comprehensive statistics using ring buffers from collector.
        O(1) time complexity due to bounded ring buffer size.
        """
        # Get read-only reference to ring buffer (O(1))
        buffer = self.collector.get_short_buffer(data_key)
        
        if len(buffer) < 2:
            return {
                'current': 0, 'avg': 0, 'max': 0, 'min': 0, 
                'std_dev': 0, 'range': 0, 'trend': 0
            }
        
        # Convert deque to list for statistics operations (O(k) where k is constant buffer size)
        data = list(buffer)
        recent_data = data[-min(self.stats_window, len(data)):]
        
        current = data[-1] if data else 0
        avg = statistics.mean(recent_data)
        max_val = max(recent_data)
        min_val = min(recent_data)
        std_dev = statistics.stdev(recent_data) if len(recent_data) > 1 else 0
        range_val = max_val - min_val
        
        # Calculate trend (slope of last 20 points) - O(1) due to fixed window size
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
                trend *= self.sample_rate  # Scale to per-second trend
        
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
    
    def display_thermodynamic_balance(self, sample: TelemetrySample):
        """Display thermodynamically correct energy balance equation with clear sign conventions."""
        print("\n" + "="*80)
        print("🌡️  THERMODYNAMIC ENERGY BALANCE - SITE BOUNDARY")
        print("="*80)
        
        # Site boundary components with clear sign conventions
        P_sun = sample.solar_power          # Always positive (generation)
        P_grid = sample.grid_power         # + = export, - = import  
        P_batt = sample.battery_power      # + = charging, - = discharging
        P_load = sample.load_power         # House consumption
        
        print(f"📊 SIGN CONVENTIONS:")
        print(f"   P_sun  > 0: Solar generation     | P_batt > 0: Battery charging")
        print(f"   P_grid > 0: Grid export          | P_batt < 0: Battery discharging") 
        print(f"   P_grid < 0: Grid import          | P_load > 0: House consumption")
        
        print(f"\n⚖️  FUNDAMENTAL ENERGY BALANCE:")
        print(f"   P_grid = P_sun - P_load - P_batt")
        
        # Show with actual values and clear signs
        batt_sign = "+" if P_batt >= 0 else ""
        grid_sign = "+" if P_grid >= 0 else ""
        
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
    
    def display_enhanced_statistics_table(self, stats: Dict, sample: TelemetrySample):
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
            ('House Load', 'load_power', 'W'),
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
            ('Inverter Temp', 'inverter_temperature', '°C'),
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
        ems_description = self.get_ems_mode_description(sample.ems_mode)
        print(f"   • EMS Mode: {ems_description}")
        print(f"   • System State: {sample.system_state}")
        print(f"   • Running State: {sample.running_state}")
        print(f"   • Connection: {sample.connection_status}")
        print(f"   • Data Valid: {sample.data_valid}")
        
        # Telemetry system status
        collector_stats = self.collector.get_stats()
        buffer_info = self.collector.get_buffer_info()
        print(f"   • Sample Rate: {collector_stats['sample_rate_hz']:.1f} Hz")
        print(f"   • Queue: {collector_stats['queue_size']}/{collector_stats['queue_maxsize']}")
        print(f"   • Samples: {collector_stats['sample_count']} (Errors: {collector_stats['error_count']})")
        print(f"   • Ring Buffer: {buffer_info['short_buffer_lengths'].get('solar_power', 0)}/{buffer_info['short_buffer_size']} (last {buffer_info['short_window_seconds']}s)")
        print(f"   • Memory: O(1) bounded buffers, {len(buffer_info['buffer_keys'])} metrics tracked")
    
    def process_telemetry_sample(self, sample: TelemetrySample) -> Dict[str, Dict[str, float]]:
        """
        Process a telemetry sample and calculate statistics.
        Data storage is handled by the collector's ring buffers.
        """
        # Calculate statistics for all tracked parameters using ring buffers
        stats = {}
        buffer_info = self.collector.get_buffer_info()
        
        for key in buffer_info['buffer_keys']:
            stats[key] = self.calculate_statistics(key)
        
        return stats
    
    async def run(self):
        """Main async monitoring loop."""
        print("🔌 Connected to telemetry system. Starting async monitoring...")
        await asyncio.sleep(1)
        
        self.running = True
        
        try:
            while self.running:
                # Get telemetry sample from queue
                sample = await self.collector.get_sample()
                
                # Process sample and calculate statistics
                stats = self.process_telemetry_sample(sample)
                
                # Clear screen and display
                os.system('clear' if os.name == 'posix' else 'cls')
                
                print("🏠 ASYNC ENHANCED SUNGROW MONITOR - TELEMETRY QUEUE ARCHITECTURE")
                print(f"⏰ {sample.datetime.strftime('%Y-%m-%d %H:%M:%S')} | Queue-Based Data Acquisition")
                
                # Display thermodynamic balance
                self.display_thermodynamic_balance(sample)
                
                # Display enhanced statistics table
                self.display_enhanced_statistics_table(stats, sample)
                
                # Show data quality indicators
                if not sample.data_valid:
                    print(f"\n⚠️  DATA QUALITY WARNING:")
                    print(f"   Status: {sample.connection_status}")
                    print(f"   Errors: {sample.read_errors}")
                
        except KeyboardInterrupt:
            print("\n🛑 Monitoring stopped by user")
        except Exception as e:
            print(f"\n❌ Error during monitoring: {e}")
            logger.exception("Monitor error")
        finally:
            self.running = False
            print("🔌 Async monitor stopped")


    # (Legacy implementation kept for backward compatibility) 