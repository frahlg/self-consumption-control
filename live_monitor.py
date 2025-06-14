#!/usr/bin/env python3
"""
Live Energy Management System Monitor
Producer-Consumer architecture with Rich Live context for smooth 5fps UI updates.
"""

import asyncio
import signal
from datetime import datetime
from typing import Optional

from rich.console import Console
from rich.live import Live
from rich.text import Text
from rich.align import Align

from telemetry import TelemetryCollector, create_telemetry_system
from analysis import AnalysisSnapshot, analyze_from_collector
from ui_renderer import render


class LiveEnergyMonitor:
    """
    Live energy monitor with producer-consumer architecture.
    
    Producer: Analysis kernel generating snapshots from telemetry data
    Consumer: UI renderer consuming snapshots at 5fps refresh rate
    """
    
    def __init__(self, telemetry_collector: TelemetryCollector):
        self.collector = telemetry_collector
        self.running = False
        self.current_snapshot: Optional[AnalysisSnapshot] = None
        
        # UI refresh rate (5fps = 200ms intervals)
        self.ui_refresh_interval = 0.2  # seconds
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
    
    def signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        self.running = False
    
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
                # This doesn't need to match UI refresh rate
                await asyncio.sleep(0.5)  # 2Hz snapshot generation
                
            except Exception as e:
                # Continue on errors to keep monitoring running
                print(f"Error in snapshot producer: {e}")
                await asyncio.sleep(1.0)
    
    def get_current_renderable(self):
        """
        Get current renderable for UI.
        Called by Rich Live context at 5fps.
        """
        if self.current_snapshot is None:
            # Show loading state
            loading_text = Text("🔄 Initializing Energy Management System...", style="bold bright_cyan")
            return Align.center(loading_text, vertical="middle")
        
        # Convert snapshot to Rich renderable
        return render(self.current_snapshot)
    
    async def run_live_monitor(self):
        """
        Main monitor loop with Rich Live context.
        UI updates at 5fps regardless of data collection rate.
        """
        console = Console()
        
        with Live(
            self.get_current_renderable(),
            console=console,
            screen=True,
            auto_refresh=False,  # Manual refresh control
            refresh_per_second=5  # 5fps target
        ) as live:
            
            print("🚀 Starting Live Energy Management Monitor")
            print(f"📊 UI Refresh Rate: {1/self.ui_refresh_interval}fps")
            print(f"📡 Data Collection: {self.collector.get_buffer_info()['sample_rate']}Hz")
            print("Press Ctrl+C to stop\n")
            
            self.running = True
            
            # Start snapshot producer task
            producer_task = asyncio.create_task(self.snapshot_producer_task())
            
            try:
                # Consumer loop: Update UI at 5fps
                while self.running:
                    # Update Live display with current renderable
                    live.update(self.get_current_renderable())
                    
                    # Sleep for UI refresh interval (200ms = 5fps)
                    await asyncio.sleep(self.ui_refresh_interval)
                    
            except KeyboardInterrupt:
                print("\n🛑 Keyboard interrupt received")
                self.running = False
            except Exception as e:
                print(f"\n❌ Error in live monitor: {e}")
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
        Start the complete live monitoring system.
        """
        try:
            # Start telemetry collector
            if not await self.collector.start():
                print("❌ Failed to start telemetry collector")
                return
            
            # Start collector task
            collector_task = asyncio.create_task(self.collector.run_collector())
            
            try:
                # Run live monitor
                await self.run_live_monitor()
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
    """Main entry point for live energy monitor."""
    
    # Create telemetry system
    print("🔧 Initializing telemetry system...")
    collector = await create_telemetry_system()
    
    # Create and run live monitor
    monitor = LiveEnergyMonitor(collector)
    await monitor.run()
    
    print("\n✅ Live monitor stopped gracefully")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}") 