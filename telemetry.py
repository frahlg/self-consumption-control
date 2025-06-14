#!/usr/bin/env python3
"""
Telemetry Data Structures and Async Collection System
Provides clean separation between data acquisition and processing.
"""

import asyncio
import time
import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, AsyncGenerator, Deque
from datetime import datetime
from collections import deque, defaultdict
from sungrow_controller import SungrowController

logger = logging.getLogger(__name__)


@dataclass
class TelemetrySample:
    """
    Validated telemetry sample with timestamp and all system data.
    This is the single data structure passed through the async queue.
    """
    timestamp: float = field(default_factory=time.time)
    datetime: datetime = field(default_factory=datetime.now)
    
    # Power data (W)
    solar_power: float = 0.0
    battery_power: float = 0.0        # + = charging, - = discharging
    grid_power: float = 0.0          # + = export, - = import
    load_power: float = 0.0          # Calculated house consumption
    total_power: float = 0.0
    
    # Battery data
    battery_soc: float = 0.0         # %
    battery_voltage: float = 0.0     # V
    battery_current: float = 0.0     # A
    battery_temperature: float = 0.0 # °C
    battery_soh: float = 0.0         # %
    battery_capacity: float = 0.0    # kWh
    
    # System data
    grid_frequency: float = 0.0      # Hz
    inverter_temperature: float = 0.0 # °C
    system_state: str = ""
    running_state: int = 0
    ems_mode: int = 0
    
    # Control settings
    min_soc: float = 0.0             # %
    max_soc: float = 0.0             # %
    export_power_limit: int = 0      # W
    export_power_limit_enabled: bool = False
    
    # Energy counters (kWh)
    daily_pv_generation: float = 0.0
    daily_imported_energy: float = 0.0
    daily_exported_energy: float = 0.0
    daily_battery_charge: float = 0.0
    daily_battery_discharge: float = 0.0
    
    # System identification
    inverter_serial: str = ""
    device_type_code: int = 0
    
    # Data quality indicators
    data_valid: bool = True
    connection_status: str = "connected"
    read_errors: int = 0
    
    def validate(self) -> bool:
        """Validate the telemetry sample for basic sanity checks."""
        try:
            # Basic range checks
            if not (0 <= self.battery_soc <= 100):
                logger.warning(f"Invalid battery SOC: {self.battery_soc}%")
                return False
                
            if not (45 <= self.grid_frequency <= 55):
                logger.warning(f"Invalid grid frequency: {self.grid_frequency} Hz")
                return False
                
            # Solar power should be negative (generation), only warn if extremely negative
            if self.solar_power < -50000:  # > 50kW seems unrealistic for most systems
                logger.warning(f"Extremely negative solar power: {self.solar_power} W")
                return False
                
            # Energy balance check using correct equation: P_load = P_grid - P_battery - P_solar
            calculated_load = self.grid_power - self.battery_power - self.solar_power
            if abs(calculated_load - self.load_power) > 100:  # 100W tolerance
                logger.debug(f"Energy balance deviation: calculated={calculated_load:.0f}W, "
                           f"stored={self.load_power:.0f}W")
                # Update with calculated value
                self.load_power = calculated_load
                
            return True
            
        except Exception as e:
            logger.error(f"Validation error: {e}")
            return False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization/logging."""
        return {
            'timestamp': self.timestamp,
            'datetime': self.datetime.isoformat(),
            'solar_power': self.solar_power,
            'battery_power': self.battery_power,
            'grid_power': self.grid_power,
            'load_power': self.load_power,
            'battery_soc': self.battery_soc,
            'grid_frequency': self.grid_frequency,
            'inverter_temperature': self.inverter_temperature,
            'system_state': self.system_state,
            'data_valid': self.data_valid,
            'connection_status': self.connection_status
        }


class TelemetryCollector:
    """
    Async telemetry collector that handles all data acquisition.
    Runs as a background task and pushes validated samples to a queue.
    Manages ring buffers for bounded memory usage and O(1) statistics.
    """
    
    def __init__(self, 
                 controller: SungrowController,
                 sample_rate: float = 2.0,  # Hz
                 queue_maxsize: int = 100,
                 short_window_seconds: int = 30,  # Short-term statistics window
                 long_window_seconds: int = 300): # Long-term statistics window (5 min)
        self.controller = controller
        self.sample_rate = sample_rate
        self.sample_interval = 1.0 / sample_rate
        self.queue = asyncio.Queue(maxsize=queue_maxsize)
        self.running = False
        self.sample_count = 0
        self.error_count = 0
        
        # Ring buffer parameters
        self.short_window_seconds = short_window_seconds
        self.long_window_seconds = long_window_seconds
        self.short_buffer_size = int(short_window_seconds * sample_rate)
        self.long_buffer_size = int(long_window_seconds * sample_rate)
        
        # Ring buffers for time-series data (bounded memory)
        # These store raw numeric values for O(1) statistical operations
        self.short_buffers: Dict[str, Deque[float]] = defaultdict(
            lambda: deque(maxlen=self.short_buffer_size)
        )
        self.long_buffers: Dict[str, Deque[float]] = defaultdict(
            lambda: deque(maxlen=self.long_buffer_size)
        )
        
        # Ring buffer for complete samples (for replay/debugging)
        self.sample_buffer: Deque[TelemetrySample] = deque(maxlen=self.short_buffer_size)
        
        # Buffer metadata
        self.buffer_keys = [
            'solar_power', 'battery_power', 'grid_power', 'load_power',
            'battery_soc', 'battery_voltage', 'battery_current', 'battery_temperature',
            'grid_frequency', 'inverter_temperature'
        ]
        
    async def start(self) -> bool:
        """Start the collector (connect to hardware)."""
        loop = asyncio.get_event_loop()
        
        # Run blocking connection call in thread pool
        connected = await loop.run_in_executor(None, self.controller.connect)
        
        if connected:
            self.running = True
            logger.info(f"🔌 Telemetry collector started at {1/self.sample_interval:.1f} Hz")
            return True
        else:
            logger.error("❌ Failed to connect telemetry collector")
            return False
    
    async def stop(self):
        """Stop the collector."""
        self.running = False
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.controller.disconnect)
        logger.info("🔌 Telemetry collector stopped")
    
    def _append_to_ring_buffers(self, sample: TelemetrySample):
        """
        Append sample data to ring buffers.
        This is the ONLY method that modifies ring buffers - collector exclusive.
        """
        if not sample.data_valid:
            return  # Don't pollute buffers with invalid data
        
        # Store complete sample
        self.sample_buffer.append(sample)
        
        # Extract and store numeric values in ring buffers
        sample_data = {
            'solar_power': sample.solar_power,
            'battery_power': sample.battery_power,
            'grid_power': sample.grid_power,
            'load_power': sample.load_power,
            'battery_soc': sample.battery_soc,
            'battery_voltage': sample.battery_voltage,
            'battery_current': sample.battery_current,
            'battery_temperature': sample.battery_temperature,
            'grid_frequency': sample.grid_frequency,
            'inverter_temperature': sample.inverter_temperature,
        }
        
        # Append to both short and long ring buffers (O(1) operation)
        for key in self.buffer_keys:
            if key in sample_data:
                value = sample_data[key]
                if isinstance(value, (int, float)):
                    self.short_buffers[key].append(value)
                    self.long_buffers[key].append(value)
    
    def _create_sample_from_controller_data(self) -> TelemetrySample:
        """Create a telemetry sample from current controller data."""
        try:
            # Get current state from controller
            state = self.controller.get_current_state()
            
            # Get power values for energy balance calculation
            solar_power = state['power'].get('solar_power', 0)
            battery_power = state['power'].get('battery_power', 0)
            grid_power = state['power'].get('grid_power', 0)
            
            # Calculate load power from energy balance: P_load = P_grid - P_battery - P_solar
            # This is more accurate than the load_power register
            calculated_load = grid_power - battery_power - solar_power
            
            # Create sample with all data
            sample = TelemetrySample(
                # Power data
                solar_power=solar_power,
                battery_power=battery_power,
                grid_power=grid_power,
                total_power=state['power'].get('total_power', 0),
                
                # Battery data  
                battery_soc=state['battery'].get('level', 0),
                battery_voltage=state['battery'].get('voltage', 0),
                battery_current=state['battery'].get('current', 0),
                battery_temperature=state['battery'].get('temperature', 0),
                battery_soh=state['battery'].get('state_of_health', 0),
                battery_capacity=state['battery'].get('capacity', 0),
                
                # System data
                grid_frequency=state['power'].get('grid_frequency', 0),
                inverter_temperature=state['power'].get('inverter_temperature', 0),
                system_state=state['system'].get('system_state', 'Unknown'),
                running_state=state['system'].get('running_state', 0),
                ems_mode=state['system'].get('ems_mode', 0),
                
                # Control settings
                min_soc=state['system'].get('min_soc', 0),
                max_soc=state['system'].get('max_soc', 0),
                export_power_limit=state['system'].get('export_power_limit', 0),
                export_power_limit_enabled=state['system'].get('export_power_limit_enabled', False),
                
                # Energy counters
                daily_pv_generation=state['energy'].get('daily_pv_generation', 0),
                daily_imported_energy=state['energy'].get('daily_imported_energy', 0),
                daily_exported_energy=state['energy'].get('daily_exported_energy', 0),
                daily_battery_charge=state['energy'].get('daily_battery_charge', 0),
                daily_battery_discharge=state['energy'].get('daily_battery_discharge', 0),
                
                # System identification
                inverter_serial=state['system'].get('inverter_serial', ''),
                device_type_code=0,  # Not currently in state dict
                
                # Use calculated load power from energy balance
                load_power=calculated_load,
                
                # Quality indicators
                data_valid=True,
                connection_status="connected",
                read_errors=self.error_count
            )
            
            return sample
            
        except Exception as e:
            logger.error(f"Error creating telemetry sample: {e}")
            # Return minimal error sample
            return TelemetrySample(
                data_valid=False,
                connection_status="error",
                read_errors=self.error_count + 1
            )
    
    async def collect_sample(self) -> Optional[TelemetrySample]:
        """Collect a single telemetry sample."""
        try:
            # Run blocking I/O in thread pool
            loop = asyncio.get_event_loop()
            
            # Update controller data
            update_success = await loop.run_in_executor(None, self.controller.update)
            
            if not update_success:
                self.error_count += 1
                logger.warning("Failed to update controller data")
                return TelemetrySample(
                    data_valid=False,
                    connection_status="read_error",
                    read_errors=self.error_count
                )
            
            # Create sample from updated data
            sample = self._create_sample_from_controller_data()
            
            # Validate sample
            if sample.validate():
                self.sample_count += 1
                return sample
            else:
                self.error_count += 1
                sample.data_valid = False
                return sample
                
        except Exception as e:
            self.error_count += 1
            logger.error(f"Error collecting telemetry sample: {e}")
            return TelemetrySample(
                data_valid=False,
                connection_status="exception",
                read_errors=self.error_count
            )
    
    async def run_collector(self):
        """Main collector loop - runs as background task."""
        logger.info("🚀 Starting telemetry collection loop")
        
        while self.running:
            start_time = time.time()
            
            try:
                # Collect sample
                sample = await self.collect_sample()
                
                if sample:
                    # Append to ring buffers (O(1) operation, bounded memory)
                    self._append_to_ring_buffers(sample)
                    
                    # Try to put sample in queue (non-blocking)
                    try:
                        self.queue.put_nowait(sample)
                    except asyncio.QueueFull:
                        logger.warning("Telemetry queue full, dropping oldest sample")
                        try:
                            self.queue.get_nowait()  # Remove oldest
                            self.queue.put_nowait(sample)  # Add new
                        except asyncio.QueueEmpty:
                            pass
                
                # Maintain sample rate
                elapsed = time.time() - start_time
                sleep_time = max(0, self.sample_interval - elapsed)
                
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                else:
                    logger.debug(f"Collection cycle overrun by {-sleep_time:.3f}s")
                    
            except asyncio.CancelledError:
                logger.info("Telemetry collector cancelled")
                break
            except Exception as e:
                logger.error(f"Unexpected error in collector loop: {e}")
                await asyncio.sleep(1.0)  # Brief pause before retry
        
        logger.info("🛑 Telemetry collection loop stopped")
    
    async def get_sample(self) -> TelemetrySample:
        """Get the next telemetry sample from the queue."""
        return await self.queue.get()
    
    def get_sample_nowait(self) -> Optional[TelemetrySample]:
        """Get a telemetry sample without waiting (returns None if empty)."""
        try:
            return self.queue.get_nowait()
        except asyncio.QueueEmpty:
            return None
    
    async def get_samples_batch(self, max_samples: int = 10) -> list[TelemetrySample]:
        """Get multiple samples as a batch."""
        samples = []
        
        # Get first sample (wait if needed)
        if max_samples > 0:
            first_sample = await self.get_sample()
            samples.append(first_sample)
            max_samples -= 1
        
        # Get additional samples if available (non-blocking)
        while max_samples > 0:
            sample = self.get_sample_nowait()
            if sample is None:
                break
            samples.append(sample)
            max_samples -= 1
        
        return samples
    
    # Read-only access to ring buffers for downstream consumers
    def get_short_buffer(self, key: str) -> Deque[float]:
        """
        Get read-only reference to short-term ring buffer.
        Consumers MUST treat this as read-only - do not modify!
        """
        return self.short_buffers[key]
    
    def get_long_buffer(self, key: str) -> Deque[float]:
        """
        Get read-only reference to long-term ring buffer.
        Consumers MUST treat this as read-only - do not modify!
        """
        return self.long_buffers[key]
    
    def get_sample_buffer(self) -> Deque[TelemetrySample]:
        """
        Get read-only reference to complete sample ring buffer.
        Consumers MUST treat this as read-only - do not modify!
        """
        return self.sample_buffer
    
    def get_buffer_info(self) -> Dict[str, Any]:
        """Get ring buffer metadata and statistics."""
        return {
            'short_window_seconds': self.short_window_seconds,
            'long_window_seconds': self.long_window_seconds,
            'short_buffer_size': self.short_buffer_size,
            'long_buffer_size': self.long_buffer_size,
            'sample_rate': self.sample_rate,
            'buffer_keys': self.buffer_keys,
            'short_buffer_lengths': {key: len(buf) for key, buf in self.short_buffers.items()},
            'long_buffer_lengths': {key: len(buf) for key, buf in self.long_buffers.items()},
            'sample_buffer_length': len(self.sample_buffer)
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """Get collector statistics."""
        return {
            'running': self.running,
            'sample_count': self.sample_count,
            'error_count': self.error_count,
            'error_rate': self.error_count / max(1, self.sample_count),
            'queue_size': self.queue.qsize(),
            'queue_maxsize': self.queue.maxsize,
            'sample_rate_hz': 1.0 / self.sample_interval
        }


async def create_telemetry_system(sample_rate: float = 2.0) -> TelemetryCollector:
    """
    Factory function to create and start a telemetry collection system.
    
    Args:
        sample_rate: Sampling rate in Hz
        
    Returns:
        Started TelemetryCollector instance
    """
    controller = SungrowController()
    collector = TelemetryCollector(controller, sample_rate=sample_rate)
    
    if await collector.start():
        # Start the background collection task
        asyncio.create_task(collector.run_collector())
        return collector
    else:
        raise RuntimeError("Failed to start telemetry system")


# Example usage for testing
async def telemetry_example():
    """Example of how to use the telemetry system."""
    
    # Create telemetry system
    collector = await create_telemetry_system(sample_rate=2.0)
    
    try:
        print("📊 Telemetry System Example")
        print("=" * 40)
        
        # Collect a few samples
        for i in range(5):
            sample = await collector.get_sample()
            
            print(f"\n📋 Sample {i+1}:")
            print(f"   🕒 Time: {sample.datetime.strftime('%H:%M:%S')}")
            print(f"   🌞 Solar: {sample.solar_power:.0f}W")
            print(f"   🔋 Battery: {sample.battery_soc:.1f}% ({sample.battery_power:.0f}W)")
            print(f"   ⚡ Grid: {sample.grid_power:.0f}W")
            print(f"   🏠 Load: {sample.load_power:.0f}W")
            print(f"   ✅ Valid: {sample.data_valid}")
        
        # Show collector stats
        stats = collector.get_stats()
        print(f"\n📈 Collector Stats:")
        print(f"   Samples: {stats['sample_count']}")
        print(f"   Errors: {stats['error_count']}")
        print(f"   Queue: {stats['queue_size']}/{stats['queue_maxsize']}")
        
    finally:
        await collector.stop()


if __name__ == "__main__":
    asyncio.run(telemetry_example()) 