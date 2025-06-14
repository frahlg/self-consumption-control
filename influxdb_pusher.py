#!/usr/bin/env python3
"""
High-Frequency InfluxDB Data Pusher Service
Collects data from Sungrow controller at 50Hz and pushes directly to InfluxDB
"""

import asyncio
import time
import logging
from datetime import datetime
from typing import Dict, Any, Optional
import yaml
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS, ASYNCHRONOUS, WriteOptions
from datetime import datetime, timezone
from sungrow_controller import SungrowController

logger = logging.getLogger(__name__)


class InfluxDBPusher:
    """
    High-frequency data pusher that collects telemetry at configurable rate
    and pushes directly to InfluxDB with minimal overhead.
    """
    
    def __init__(self, config_file: str = "influxdb_config.yaml"):
        self.config_file = config_file
        self.config = self._load_config()
        
        # InfluxDB settings
        self.influxdb_url = self.config['influxdb']['url']
        self.token = self.config['influxdb']['token']
        self.org = self.config['influxdb']['org']
        self.bucket = self.config['influxdb']['bucket']
        
        # Collection settings
        self.sample_rate = self.config['collection']['sample_rate']
        self.sample_interval = 1.0 / self.sample_rate
        self.progress_interval = self.config['logging']['show_progress_interval']
        
        # Setup logging
        log_level = getattr(logging, self.config['logging']['level'].upper())
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        # Initialize InfluxDB client with batching for high-frequency writes
        self.influx_client = InfluxDBClient(
            url=self.influxdb_url,
            token=self.token,
            org=self.org
        )
        
        # Use asynchronous batching for better throughput
        write_options = WriteOptions(
            batch_size=self.config['performance']['batch_size'],
            flush_interval=self.config['performance']['flush_interval'],
            jitter_interval=0,
            write_type=ASYNCHRONOUS
        )
        self.write_api = self.influx_client.write_api(write_options=write_options)
        
        # Initialize Sungrow controller
        self.controller = SungrowController()
        
        # Runtime state
        self.running = False
        self.sample_count = 0
        self.error_count = 0
        self.start_time = None
        
        # Performance metrics
        self.total_samples = 0
        self.total_writes = 0
        self.last_write_time = 0
        self.write_errors = 0
        
        logger.info(f"🚀 InfluxDB Pusher initialized at {self.sample_rate}Hz")
        logger.info(f"📡 Target: {self.influxdb_url} | Org: {self.org} | Bucket: {self.bucket}")
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        try:
            with open(self.config_file, 'r') as file:
                config = yaml.safe_load(file)
                logger.info(f"✅ Loaded configuration from {self.config_file}")
                return config
        except FileNotFoundError:
            logger.error(f"❌ Configuration file {self.config_file} not found")
            raise
        except Exception as e:
            logger.error(f"❌ Error loading configuration: {e}")
            raise
    
    async def start(self) -> bool:
        """Initialize connections and start the service."""
        try:
            # Connect to Sungrow controller
            logger.info("🔌 Connecting to Sungrow controller...")
            if not await asyncio.get_event_loop().run_in_executor(None, self.controller.connect):
                logger.error("❌ Failed to connect to Sungrow controller")
                return False
            
            # Test InfluxDB connection
            logger.info("🔌 Testing InfluxDB connection...")
            health = self.influx_client.health()
            if health.status != "pass":
                logger.error(f"❌ InfluxDB health check failed: {health.message}")
                return False
            
            logger.info("✅ All connections established successfully")
            self.running = True
            self.start_time = time.time()
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to start service: {e}")
            return False
    
    async def stop(self):
        """Stop the service and cleanup connections."""
        self.running = False
        
        # Disconnect from controller
        if self.controller:
            await asyncio.get_event_loop().run_in_executor(None, self.controller.disconnect)
        
        # Close InfluxDB connection
        if self.influx_client:
            self.influx_client.close()
        
        # Print final statistics
        if self.start_time:
            runtime = time.time() - self.start_time
            logger.info(f"📊 Final Statistics:")
            logger.info(f"   Runtime: {runtime:.1f}s")
            logger.info(f"   Total Samples: {self.total_samples}")
            logger.info(f"   Total Writes: {self.total_writes}")
            logger.info(f"   Write Errors: {self.write_errors}")
            logger.info(f"   Average Rate: {self.total_samples/runtime:.1f} Hz")
        
        logger.info("🛑 InfluxDB Pusher stopped")
    
    def collect_data(self) -> Optional[Dict[str, Any]]:
        """Collect data from Sungrow controller with minimal overhead."""
        try:
            # Update data from controller
            if not self.controller.update():
                return None
            
            # Get current state
            state = self.controller.get_current_state()
            
            if not state:
                return None
            
            # Extract key measurements with current timestamp
            timestamp = time.time()
            
            measurements = {
                'timestamp': timestamp,
                'datetime': datetime.fromtimestamp(timestamp),
                
                # Power measurements (W)
                'solar_power': state['power']['solar_power'],
                'battery_power': state['power']['battery_power'],
                'grid_power': state['power']['grid_power'],
                'load_power': state['power']['load_power'],
                'total_power': state['power']['total_power'],
                
                # Battery data
                'battery_soc': state['battery']['level'],
                'battery_voltage': state['battery']['voltage'],
                'battery_current': state['battery']['current'],
                'battery_temperature': state['battery']['temperature'],
                'battery_power_alt': state['battery']['power'],  # Alternative battery power reading
                'battery_soh': state['battery']['state_of_health'],
                'battery_capacity': state['battery']['capacity'],
                
                # System data
                'grid_frequency': state['power']['grid_frequency'],
                'inverter_temperature': state['power']['inverter_temperature'],
                'running_state': state['system']['running_state'],
                'ems_mode': state['system']['ems_mode'],
                'system_state': state['system']['system_state'],
                
                # Phase data (get from controller's power_data directly)
                'phase_a_voltage': self.controller.power_data.phase_a_voltage,
                'phase_b_voltage': self.controller.power_data.phase_b_voltage,
                'phase_c_voltage': self.controller.power_data.phase_c_voltage,
                'phase_a_current': self.controller.power_data.phase_a_current,
                'phase_b_current': self.controller.power_data.phase_b_current,
                'phase_c_current': self.controller.power_data.phase_c_current,
                
                # Energy counters
                'daily_pv_generation': state['energy']['daily_pv_generation'],
                'daily_imported_energy': state['energy']['daily_imported_energy'],
                'daily_exported_energy': state['energy']['daily_exported_energy'],
                'daily_battery_charge': state['energy']['daily_battery_charge'],
                'daily_battery_discharge': state['energy']['daily_battery_discharge'],
                
                # Control settings
                'min_soc': state['system']['min_soc'],
                'max_soc': state['system']['max_soc'],
                'export_power_limit': state['system']['export_power_limit'],
                'export_power_limit_enabled': state['system']['export_power_limit_enabled'],
                
                # System identification
                'inverter_serial': state['system']['inverter_serial'],
                
                # Battery state flags
                'is_charging': state['battery']['is_charging'],
                'is_discharging': state['battery']['is_discharging'],
            }
            
            return measurements
            
        except Exception as e:
            logger.error(f"❌ Data collection error: {e}")
            self.error_count += 1
            return None
    
    def write_to_influxdb(self, data: Dict[str, Any]) -> bool:
        """Write data point to InfluxDB with explicit nanosecond timestamp for high-frequency data."""
        try:
            # ns-precision wall clock for explicit timestamp
            now = datetime.now(tz=timezone.utc)
            
            point = (
                Point("energy_system")
                .tag("source", "sungrow_controller")
                .tag("location", "solar_system")
                .field("solar_power", float(data.get('solar_power', 0.0)))
                .field("battery_power", float(data.get('battery_power', 0.0)))
                .field("grid_power", float(data.get('grid_power', 0.0)))
                .field("load_power", float(data.get('load_power', 0.0)))
                .field("battery_soc", float(data.get('battery_soc', 0.0)))
                .field("battery_voltage", float(data.get('battery_voltage', 0.0)))
                .field("battery_current", float(data.get('battery_current', 0.0)))
                .field("battery_temperature", float(data.get('battery_temperature', 0.0)))
                .field("grid_frequency", float(data.get('grid_frequency', 0.0)))
                .field("inverter_temperature", float(data.get('inverter_temperature', 0.0)))
                .field("phase_a_voltage", float(data.get('phase_a_voltage', 0.0)))
                .field("phase_b_voltage", float(data.get('phase_b_voltage', 0.0)))
                .field("phase_c_voltage", float(data.get('phase_c_voltage', 0.0)))
                .field("phase_a_current", float(data.get('phase_a_current', 0.0)))
                .field("phase_b_current", float(data.get('phase_b_current', 0.0)))
                .field("phase_c_current", float(data.get('phase_c_current', 0.0)))
                .field("daily_pv_generation", float(data.get('daily_pv_generation', 0.0)))
                .field("daily_imported_energy", float(data.get('daily_imported_energy', 0.0)))
                .field("daily_exported_energy", float(data.get('daily_exported_energy', 0.0)))
                .field("daily_battery_charge", float(data.get('daily_battery_charge', 0.0)))
                .field("daily_battery_discharge", float(data.get('daily_battery_discharge', 0.0)))
                .field("running_state", int(data.get('running_state', 0)))
                .field("ems_mode", int(data.get('ems_mode', 0)))
                .field("export_power_limit", int(data.get('export_power_limit', 0)))
                .field("min_soc", float(data.get('min_soc', 0.0)))
                .field("max_soc", float(data.get('max_soc', 0.0)))
                .time(now, WritePrecision.NS)  # <<<<<<< explicit nanosecond timestamp
            )
            
            # batched asynchronous write with explicit precision
            self.write_api.write(
                bucket=self.bucket,
                org=self.org,
                record=point,
                write_precision=WritePrecision.NS  # redundant but explicit
            )
            self.total_writes += 1
            self.last_write_time = time.time()
            
            return True
            
        except Exception as e:
            logger.error(f"❌ InfluxDB write error: {e}")
            self.write_errors += 1
            return False
    
    async def run_collection_loop(self):
        """Main data collection and pushing loop at 50Hz."""
        logger.info(f"🔄 Starting data collection loop at {self.sample_rate}Hz")
        
        next_sample_time = time.time()
        
        while self.running:
            try:
                # Collect data
                data = await asyncio.get_event_loop().run_in_executor(None, self.collect_data)
                
                if data:
                    # Write to InfluxDB (non-blocking)
                    write_success = await asyncio.get_event_loop().run_in_executor(
                        None, self.write_to_influxdb, data
                    )
                    
                    if write_success:
                        self.total_samples += 1
                        
                        # Log progress at configured interval
                        if self.total_samples % self.progress_interval == 0:
                            current_time = time.time()
                            elapsed = current_time - self.start_time
                            actual_rate = self.total_samples / elapsed
                            logger.info(f"📊 Samples: {self.total_samples} | "
                                      f"Rate: {actual_rate:.1f}Hz | "
                                      f"Errors: {self.error_count + self.write_errors}")
                
                # Calculate next sample time and sleep
                next_sample_time += self.sample_interval
                current_time = time.time()
                sleep_time = next_sample_time - current_time
                
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                else:
                    # We're behind schedule - skip to next interval
                    next_sample_time = current_time + self.sample_interval
                    logger.warning(f"⚠️ Running behind schedule by {-sleep_time:.3f}s")
                
            except Exception as e:
                logger.error(f"❌ Loop error: {e}")
                self.error_count += 1
                await asyncio.sleep(0.1)  # Brief pause on error
    
    async def run(self):
        """Main service runner."""
        try:
            if not await self.start():
                return False
            
            logger.info("🚀 InfluxDB Pusher service started successfully")
            await self.run_collection_loop()
            
        except KeyboardInterrupt:
            logger.info("⌨️ Keyboard interrupt received")
        except Exception as e:
            logger.error(f"❌ Unexpected error: {e}")
        finally:
            await self.stop()


async def main():
    """Main entry point."""
    # Create and run the pusher service using configuration file
    pusher = InfluxDBPusher()
    await pusher.run()


if __name__ == "__main__":
    asyncio.run(main()) 