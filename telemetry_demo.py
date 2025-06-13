#!/usr/bin/env python3
"""
Telemetry Architecture Demonstration
Shows how the queue abstraction enables replay, stubbing, and testing.
"""

import asyncio
import json
import time
import math
import logging
from typing import List, Dict, Any
from datetime import datetime, timedelta
from telemetry import TelemetrySample, TelemetryCollector
from sungrow_controller import SungrowController

logger = logging.getLogger(__name__)


class MockTelemetryCollector(TelemetryCollector):
    """
    Mock telemetry collector for testing/replay.
    Shows how the abstraction enables stubbing.
    """
    
    def __init__(self, sample_data: List[Dict[str, Any]], sample_rate: float = 2.0):
        # Don't call super().__init__ to avoid creating real controller
        self.sample_data = sample_data
        self.sample_interval = 1.0 / sample_rate
        self.queue = asyncio.Queue(maxsize=100)
        self.running = False
        self.sample_count = 0
        self.error_count = 0
        self.current_index = 0
    
    async def start(self) -> bool:
        """Mock start - always succeeds."""
        self.running = True
        logger.info(f"🎬 Mock telemetry collector started with {len(self.sample_data)} samples")
        return True
    
    async def stop(self):
        """Mock stop."""
        self.running = False
        logger.info("🎬 Mock telemetry collector stopped")
    
    async def collect_sample(self) -> TelemetrySample:
        """Collect sample from mock data."""
        if self.current_index >= len(self.sample_data):
            # Loop back to beginning for continuous replay
            self.current_index = 0
        
        sample_dict = self.sample_data[self.current_index]
        self.current_index += 1
        
        # Create TelemetrySample from dict data
        sample = TelemetrySample(**sample_dict)
        sample.timestamp = time.time()
        sample.datetime = datetime.now()
        
        self.sample_count += 1
        return sample


class StubTelemetryCollector(TelemetryCollector):
    """
    Stub telemetry collector that generates synthetic data.
    Useful for testing without hardware.
    """
    
    def __init__(self, scenario: str = "normal", sample_rate: float = 2.0):
        # Don't call super().__init__ to avoid creating real controller
        self.scenario = scenario
        self.sample_interval = 1.0 / sample_rate
        self.queue = asyncio.Queue(maxsize=100)
        self.running = False
        self.sample_count = 0
        self.error_count = 0
        self.start_time = time.time()
    
    async def start(self) -> bool:
        """Stub start - always succeeds."""
        self.running = True
        self.start_time = time.time()
        logger.info(f"🤖 Stub telemetry collector started (scenario: {self.scenario})")
        return True
    
    async def stop(self):
        """Stub stop."""
        self.running = False
        logger.info("🤖 Stub telemetry collector stopped")
    
    def _generate_scenario_data(self, elapsed_time: float) -> Dict[str, Any]:
        """Generate synthetic data based on scenario."""
        
        if self.scenario == "normal":
            # Normal operation with some solar generation
            solar_power = max(0, 4000 + 2000 * (0.5 + 0.4 * math.sin(elapsed_time / 10)))
            battery_soc = 50 + 30 * math.sin(elapsed_time / 60)
            battery_power = 1000 * math.sin(elapsed_time / 20)
            grid_power = solar_power - 1200 - battery_power
            
        elif self.scenario == "peak_shaving":
            # Peak shaving scenario
            solar_power = 6000 if 10 < elapsed_time % 60 < 50 else 2000
            battery_soc = max(20, 80 - elapsed_time / 10)  # Discharging
            battery_power = -2000 if battery_soc > 25 else 0  # Discharge until low
            grid_power = solar_power - 3000 - battery_power
            
        elif self.scenario == "grid_outage":
            # Grid outage scenario
            solar_power = 3000
            battery_soc = max(10, 60 - elapsed_time / 5)  # Rapid discharge
            battery_power = -2500  # Emergency discharge
            grid_power = 0  # No grid
            
        else:
            # Default case
            solar_power = 2000
            battery_soc = 50
            battery_power = 0
            grid_power = 500
        
        # Calculate load from energy balance
        load_power = solar_power - battery_power - grid_power
        
        return {
            'solar_power': max(0, solar_power),
            'battery_power': battery_power,
            'grid_power': grid_power,
            'load_power': max(0, load_power),
            'battery_soc': max(0, min(100, battery_soc)),
            'grid_frequency': 50.0 + 0.1 * math.sin(elapsed_time),
            'inverter_temperature': 45 + 10 * math.sin(elapsed_time / 30),
            'system_state': f"Running {self.scenario.title()}",
            'running_state': 11,
            'ems_mode': 0,
            'data_valid': True,
            'connection_status': "stubbed"
        }
    
    async def collect_sample(self) -> TelemetrySample:
        """Generate synthetic sample."""
        elapsed_time = time.time() - self.start_time
        
        sample_data = self._generate_scenario_data(elapsed_time)
        sample = TelemetrySample(**sample_data)
        sample.timestamp = time.time()
        sample.datetime = datetime.now()
        
        self.sample_count += 1
        return sample


class TelemetryLogger:
    """
    Logs telemetry data to JSON for replay.
    Demonstrates data persistence capability.
    """
    
    def __init__(self, filename: str):
        self.filename = filename
        self.samples = []
    
    def log_sample(self, sample: TelemetrySample):
        """Log a sample to memory."""
        self.samples.append(sample.to_dict())
    
    def save_to_file(self):
        """Save logged samples to JSON file."""
        with open(self.filename, 'w') as f:
            json.dump(self.samples, f, indent=2)
        logger.info(f"💾 Saved {len(self.samples)} samples to {self.filename}")
    
    @classmethod
    def load_from_file(cls, filename: str) -> List[Dict[str, Any]]:
        """Load samples from JSON file for replay."""
        with open(filename, 'r') as f:
            data = json.load(f)
        logger.info(f"📂 Loaded {len(data)} samples from {filename}")
        return data


async def demo_real_system():
    """Demo 1: Real system with logging."""
    print("🏠 Demo 1: Real System Data Collection & Logging")
    print("=" * 60)
    
    try:
        # Create real telemetry system
        from telemetry import create_telemetry_system
        collector = await create_telemetry_system(sample_rate=2.0)
        
        # Create logger
        logger_demo = TelemetryLogger("telemetry_log.json")
        
        print("📊 Collecting 10 real samples...")
        
        # Collect and log samples
        for i in range(10):
            sample = await collector.get_sample()
            logger_demo.log_sample(sample)
            
            print(f"   Sample {i+1}: Solar={sample.solar_power:.0f}W, "
                  f"Battery={sample.battery_soc:.1f}%, Grid={sample.grid_power:.0f}W")
        
        # Save to file
        logger_demo.save_to_file()
        
        await collector.stop()
        print("✅ Real system demo complete\n")
        
    except Exception as e:
        print(f"❌ Real system demo failed: {e}\n")


async def demo_replay_system():
    """Demo 2: Replay from logged data."""
    print("🎬 Demo 2: Replay from Logged Data")
    print("=" * 60)
    
    try:
        # Load logged data
        sample_data = TelemetryLogger.load_from_file("telemetry_log.json")
        
        # Create mock collector for replay
        mock_collector = MockTelemetryCollector(sample_data, sample_rate=10.0)  # Faster replay
        await mock_collector.start()
        
        # Start collector task
        collector_task = asyncio.create_task(mock_collector.run_collector())
        
        print("📊 Replaying logged samples...")
        
        # Get replayed samples
        for i in range(5):
            sample = await mock_collector.get_sample()
            
            print(f"   Replay {i+1}: Solar={sample.solar_power:.0f}W, "
                  f"Battery={sample.battery_soc:.1f}%, Status={sample.connection_status}")
        
        # Stop replay
        await mock_collector.stop()
        collector_task.cancel()
        
        print("✅ Replay demo complete\n")
        
    except FileNotFoundError:
        print("❌ No log file found. Run demo 1 first.\n")
    except Exception as e:
        print(f"❌ Replay demo failed: {e}\n")


async def demo_stub_scenarios():
    """Demo 3: Stub scenarios for testing."""
    print("🤖 Demo 3: Stub Scenarios for Testing")
    print("=" * 60)
    
    scenarios = ["normal", "peak_shaving", "grid_outage"]
    
    for scenario in scenarios:
        print(f"\n🎯 Testing scenario: {scenario}")
        
        # Create stub collector
        stub_collector = StubTelemetryCollector(scenario, sample_rate=5.0)
        await stub_collector.start()
        
        # Start collector task
        collector_task = asyncio.create_task(stub_collector.run_collector())
        
        # Get samples from scenario
        for i in range(3):
            sample = await stub_collector.get_sample()
            
            print(f"   Step {i+1}: Solar={sample.solar_power:.0f}W, "
                  f"Battery={sample.battery_soc:.1f}%, Grid={sample.grid_power:.0f}W")
        
        # Stop scenario
        await stub_collector.stop()
        collector_task.cancel()
    
    print("\n✅ Stub scenarios demo complete\n")


async def demo_queue_analytics():
    """Demo 4: Queue-based analytics."""
    print("📈 Demo 4: Queue-Based Analytics")
    print("=" * 60)
    
    # Create stub for continuous data
    stub_collector = StubTelemetryCollector("normal", sample_rate=2.0)
    await stub_collector.start()
    
    # Start collector task
    collector_task = asyncio.create_task(stub_collector.run_collector())
    
    # Analytics consumer that processes batches
    samples_batch = await stub_collector.get_samples_batch(max_samples=10)
    
    # Calculate analytics
    solar_powers = [s.solar_power for s in samples_batch]
    battery_socs = [s.battery_soc for s in samples_batch]
    
    print(f"📊 Batch Analytics ({len(samples_batch)} samples):")
    print(f"   Solar Power: avg={sum(solar_powers)/len(solar_powers):.0f}W, "
          f"max={max(solar_powers):.0f}W, min={min(solar_powers):.0f}W")
    print(f"   Battery SOC: avg={sum(battery_socs)/len(battery_socs):.1f}%, "
          f"max={max(battery_socs):.1f}%, min={min(battery_socs):.1f}%")
    
    # Stop analytics
    await stub_collector.stop()
    collector_task.cancel()
    
    print("✅ Analytics demo complete\n")


async def main():
    """Run all telemetry architecture demos."""
    print("🎭 TELEMETRY ARCHITECTURE DEMONSTRATION")
    print("🔌 Queue Abstraction Enables: Replay, Stubbing, Testing, Analytics")
    print("=" * 80)
    
    # Demo 1: Real system with logging
    await demo_real_system()
    
    # Demo 2: Replay from logs
    await demo_replay_system()
    
    # Demo 3: Stub scenarios
    await demo_stub_scenarios()
    
    # Demo 4: Queue analytics
    await demo_queue_analytics()
    
    print("🎉 All demos complete!")
    print("\n📚 Key Benefits Demonstrated:")
    print("   ✅ Clean separation: collector vs. analytics/UI")
    print("   ✅ Replay capability: test with historical data")
    print("   ✅ Stub scenarios: test edge cases without hardware")
    print("   ✅ Queue throttling: handle different data rates")
    print("   ✅ Batch processing: efficient analytics")
    print("   ✅ Data validation: quality assurance at source")


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    # Run demos
    asyncio.run(main()) 