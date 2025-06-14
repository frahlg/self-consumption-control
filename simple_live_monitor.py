#!/usr/bin/env python3
"""
Simple Live Energy Monitor
Producer-Consumer architecture without Rich Live (which was causing hanging)
"""

import asyncio
import signal
import os
from datetime import datetime
from typing import Optional

from telemetry import TelemetryCollector, create_telemetry_system
from analysis import AnalysisSnapshot, analyze_from_collector


class SimpleEnergyMonitor:
    """
    Simple energy monitor with producer-consumer architecture.
    Uses basic console output instead of Rich Live to avoid hanging issues.
    """
    
    def __init__(self, telemetry_collector: TelemetryCollector):
        self.collector = telemetry_collector
        self.running = False
        self.current_snapshot: Optional[AnalysisSnapshot] = None
        
        # UI refresh rate (2fps = 500ms intervals)
        self.ui_refresh_interval = 0.5  # seconds
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
    
    def signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        print("\n🛑 Shutdown signal received. Stopping monitor...")
        self.running = False
    
    def format_power(self, watts: float) -> str:
        """Format power values with appropriate units."""
        if abs(watts) >= 1_000_000:
            return f"{watts/1_000_000:.2f} MW"
        elif abs(watts) >= 1000:
            return f"{watts/1000:.2f} kW"
        else:
            return f"{watts:.0f} W"
    
    def format_percentage(self, ratio: float) -> str:
        """Format ratio as percentage."""
        return f"{ratio * 100:.1f}%"
    
    async def snapshot_producer_task(self):
        """
        Producer task: Generate analysis snapshots from telemetry data.
        Runs independently of UI refresh rate.
        """
        while self.running:
            try:
                # Generate analysis snapshot from current telemetry data
                snapshot = analyze_from_collector(self.collector, datetime.now())
                
                # Update current snapshot (thread-safe assignment)
                self.current_snapshot = snapshot
                
                # Sleep for a bit to avoid excessive CPU usage
                await asyncio.sleep(0.5)  # 2Hz snapshot generation
                
            except Exception as e:
                # Continue on errors to keep monitoring running
                print(f"Error in snapshot producer: {e}")
                await asyncio.sleep(1.0)
    
    def display_snapshot(self, snapshot: AnalysisSnapshot):
        """
        Display snapshot using simple console output.
        """
        # Clear screen
        os.system('clear' if os.name == 'posix' else 'cls')
        
        print("🏠 ENERGY MANAGEMENT SYSTEM - PRODUCER-CONSUMER ARCHITECTURE")
        print("=" * 80)
        print(f"📅 {snapshot.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"📊 Analysis Window: {snapshot.analysis_window_seconds}s with {snapshot.sample_count} samples")
        print(f"🎯 Data Quality: {self.format_percentage(snapshot.data_quality_score)}")
        print(f"⭐ System Stability: {snapshot.system_stability_index:.3f}")
        
        # System operating mode
        ratios = snapshot.energy_ratios
        modes = []
        if ratios.self_consuming: modes.append("🔄 SELF-CONSUMING")
        if ratios.grid_feeding: modes.append("⬇️ GRID-FEEDING")
        if ratios.grid_dependent: modes.append("⬆️ GRID-DEPENDENT")
        if ratios.battery_active: modes.append("🔋 BATTERY-ACTIVE")
        
        primary_mode = " + ".join(modes) if modes else "⚪ STANDBY"
        print(f"🚦 Operating Mode: {primary_mode}")
        
        # Energy balance with thermodynamic equation
        print("\n⚖️ ENERGY BALANCE - THERMODYNAMIC EQUATION")
        print("-" * 50)
        balance = snapshot.energy_balance
        print(f"P_solar + P_grid = P_load + P_battery")
        print(f"[Generation: NEGATIVE, Load: POSITIVE]")
        print(f"{self.format_power(balance.solar_power)} + {self.format_power(balance.grid_power)} = {self.format_power(balance.load_power)} + {self.format_power(balance.battery_power)}")
        
        left_side = balance.solar_power + balance.grid_power
        right_side = balance.load_power + balance.battery_power
        print(f"{self.format_power(left_side)} = {self.format_power(right_side)}")
        print(f"Balance Error: {self.format_power(balance.balance_error)} {'✅' if balance.balance_valid else '❌'}")
        
        # Show actual generation amount (positive for clarity)
        print(f"Solar Generation: {self.format_power(-balance.solar_power)} (shown as negative: {self.format_power(balance.solar_power)})")
        
        # Energy flow status
        if balance.grid_importing:
            grid_status = "🏭➡️🏠 Grid Importing"
        elif balance.grid_exporting:
            grid_status = "🏠➡️🏭 Grid Exporting"
        else:
            grid_status = "🏭⚖️🏠 Grid Balanced"
        
        if balance.battery_charging:
            battery_status = "🔋⬆️ Battery Charging"
        elif balance.battery_discharging:
            battery_status = "🔋⬇️ Battery Discharging"
        else:
            battery_status = "🔋⏸️ Battery Idle"
        
        print(f"Energy Flow: {grid_status}  |  {battery_status}")
        
        # Power stream analysis
        print("\n⚡ POWER STREAM ANALYSIS")
        print("-" * 80)
        
        def display_power_stream(name: str, emoji: str, stats, trend_suffix: str = "W/s"):
            trend_indicator = "📈" if stats.first_derivative > 0 else "📉" if stats.first_derivative < 0 else "➡️"
            oscillation_indicator = "🔴" if stats.oscillation_index > 0.2 else "🟡" if stats.oscillation_index > 0.1 else "🟢"
            
            print(f"{emoji} {name:15} Current: {self.format_power(stats.current):>8}  |  "
                  f"Avg: {self.format_power(stats.mean):>8}  |  "
                  f"Trend: {trend_indicator} {stats.first_derivative:+.1f} {trend_suffix}  |  "
                  f"Stability: {oscillation_indicator} {stats.oscillation_index:.3f}")
        
        display_power_stream("Solar", "☀️", snapshot.solar_stats)
        display_power_stream("Battery", "🔋", snapshot.battery_stats)
        display_power_stream("Grid", "🏭", snapshot.grid_stats)
        display_power_stream("Load", "🏠", snapshot.load_stats)
        
        # Energy efficiency metrics
        print("\n📊 ENERGY EFFICIENCY METRICS")
        print("-" * 50)
        print(f"🎯 Self-Consumption:    {self.format_percentage(ratios.self_consumption_ratio):>8}")
        print(f"☀️ Solar Coverage:      {self.format_percentage(ratios.solar_coverage_ratio):>8}")
        print(f"🔋 Battery Utilization: {self.format_percentage(ratios.battery_utilization_ratio):>8}")
        print(f"🏭 Grid Dependency:     {self.format_percentage(ratios.grid_dependency_ratio):>8}")
        
        # Producer-consumer info
        print(f"\n📡 SYSTEM INFO")
        print("-" * 30)
        buffer_info = self.collector.get_buffer_info()
        collector_stats = self.collector.get_stats()
        print(f"Data Collection: {buffer_info['sample_rate']:.1f} Hz")
        print(f"UI Updates: {1/self.ui_refresh_interval:.1f} fps")
        print(f"Queue: {collector_stats['queue_size']}/{collector_stats['queue_maxsize']}")
        print(f"Ring Buffer: {buffer_info['short_buffer_lengths'].get('solar_power', 0)}/{buffer_info['short_buffer_size']}")
    
    async def run_monitor(self):
        """
        Main monitor loop with console output.
        UI updates at configurable rate regardless of data collection rate.
        """
        print("🚀 Starting Simple Live Energy Management Monitor")
        print(f"📊 UI Refresh Rate: {1/self.ui_refresh_interval:.1f}fps")
        print(f"📡 Data Collection: {self.collector.get_buffer_info()['sample_rate']:.1f}Hz")
        print("Press Ctrl+C to stop\n")
        
        self.running = True
        
        # Start snapshot producer task
        producer_task = asyncio.create_task(self.snapshot_producer_task())
        
        try:
            # Consumer loop: Update UI at specified rate
            while self.running:
                if self.current_snapshot is not None:
                    self.display_snapshot(self.current_snapshot)
                else:
                    print("🔄 Initializing Energy Management System...")
                
                # Sleep for UI refresh interval
                await asyncio.sleep(self.ui_refresh_interval)
                
        except KeyboardInterrupt:
            print("\n🛑 Keyboard interrupt received")
            self.running = False
        except Exception as e:
            print(f"\n❌ Error in monitor: {e}")
            self.running = False
        finally:
            # Cleanup
            producer_task.cancel()
            try:
                await producer_task
            except asyncio.CancelledError:
                pass
    
    async def run(self):
        """
        Start the complete monitoring system.
        """
        try:
            # Start telemetry collector
            if not await self.collector.start():
                print("❌ Failed to start telemetry collector")
                return
            
            # Start collector task
            collector_task = asyncio.create_task(self.collector.run_collector())
            
            try:
                # Run monitor
                await self.run_monitor()
            finally:
                # Stop collector
                await self.collector.stop()
                collector_task.cancel()
                try:
                    await collector_task
                except asyncio.CancelledError:
                    pass
        
        except Exception as e:
            print(f"❌ Error in monitor: {e}")


async def main():
    """Main entry point for simple energy monitor."""
    
    # Create telemetry system
    print("🔧 Initializing telemetry system...")
    collector = await create_telemetry_system()
    
    # Create and run simple monitor
    monitor = SimpleEnergyMonitor(collector)
    await monitor.run()
    
    print("\n✅ Simple monitor stopped gracefully")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}") 