#!/usr/bin/env python3
"""
🤖 Self-Consumption Automation Example
Real-world automation script for optimal energy management

This script demonstrates how to build intelligent automation using
the Sungrow controller for maximum self-consumption and cost savings.
"""

from sungrow_controller import SungrowController, EMSMode, BatteryCommand
import time
import datetime
import logging
from typing import Dict, Optional

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)


class SelfConsumptionAutomation:
    """Intelligent self-consumption automation system."""
    
    def __init__(self):
        self.controller = SungrowController()
        self.last_action_time = {}
        self.min_action_interval = 300  # 5 minutes between major changes
        
        # Thresholds (configurable)
        self.high_solar_threshold = 3000  # W
        self.low_battery_threshold = 20   # %
        self.high_battery_threshold = 90  # %
        self.high_grid_export_threshold = 2000  # W
        self.high_grid_import_threshold = 1000   # W
        
    def can_take_action(self, action_name: str) -> bool:
        """Check if enough time has passed since last action."""
        last_time = self.last_action_time.get(action_name, 0)
        return time.time() - last_time > self.min_action_interval
    
    def record_action(self, action_name: str):
        """Record when an action was taken."""
        self.last_action_time[action_name] = time.time()
    
    def get_time_of_use_period(self) -> str:
        """Determine current time-of-use period."""
        current_hour = datetime.datetime.now().hour
        
        if 22 <= current_hour or current_hour <= 6:
            return "off_peak"  # Night time - cheaper electricity
        elif 7 <= current_hour <= 9 or 17 <= current_hour <= 20:
            return "peak"      # Peak hours - expensive electricity
        else:
            return "standard"  # Day time - standard rates
    
    def analyze_solar_conditions(self, state: Dict) -> str:
        """Analyze current solar generation conditions."""
        solar_power = state['power']['solar_power']
        
        if solar_power > 4000:
            return "excellent"
        elif solar_power > 2000:
            return "good"
        elif solar_power > 500:
            return "moderate"
        else:
            return "poor"
    
    def calculate_excess_solar(self, state: Dict) -> float:
        """Calculate excess solar power available for battery charging."""
        balance = self.controller.calculate_energy_balance()
        return max(0, balance['solar_generation'] - balance['house_consumption'])
    
    def optimize_battery_charging(self, state: Dict) -> Optional[str]:
        """Optimize battery charging strategy."""
        solar_conditions = self.analyze_solar_conditions(state)
        excess_solar = self.calculate_excess_solar(state)
        battery_soc = state['battery']['level']
        time_period = self.get_time_of_use_period()
        
        action_taken = None
        
        # High solar generation - maximize charging
        if solar_conditions == "excellent" and battery_soc < 85:
            if excess_solar > 2000 and self.can_take_action("optimize_charging"):
                logger.info(f"🌞 Excellent solar ({excess_solar:.0f}W excess) - optimizing battery charging")
                if self.controller.optimize_self_consumption():
                    action_taken = "optimized_self_consumption"
                    self.record_action("optimize_charging")
        
        # Off-peak charging if battery is low
        elif time_period == "off_peak" and battery_soc < 30:
            if self.can_take_action("night_charging"):
                logger.info(f"🌙 Off-peak period with low battery ({battery_soc:.1f}%) - considering grid charging")
                # In real implementation, check electricity prices
                if self.controller.force_battery_charge_from_grid(1500):
                    action_taken = "night_charging"
                    self.record_action("night_charging")
        
        return action_taken
    
    def optimize_grid_interaction(self, state: Dict) -> Optional[str]:
        """Optimize grid import/export."""
        grid_power = state['power']['grid_power']
        battery_soc = state['battery']['level']
        time_period = self.get_time_of_use_period()
        
        action_taken = None
        
        # High grid import during peak hours
        if grid_power < -self.high_grid_import_threshold and time_period == "peak":
            if battery_soc > 40 and self.can_take_action("peak_discharge"):
                logger.info(f"⚡ High grid import ({-grid_power:.0f}W) during peak - maximizing battery discharge")
                if self.controller.set_soc_limits(15.0, 90.0):
                    action_taken = "peak_discharge"
                    self.record_action("peak_discharge")
        
        # High grid export - increase battery charging
        elif grid_power > self.high_grid_export_threshold:
            if battery_soc < 85 and self.can_take_action("reduce_export"):
                logger.info(f"📤 High grid export ({grid_power:.0f}W) - increasing battery charging")
                if self.controller.force_battery_charge_from_grid(min(3000, grid_power)):
                    action_taken = "reduce_export"
                    self.record_action("reduce_export")
        
        return action_taken
    
    def emergency_management(self, state: Dict) -> Optional[str]:
        """Handle emergency conditions."""
        battery_soc = state['battery']['level']
        inverter_temp = state['power']['inverter_temperature']
        
        action_taken = None
        
        # Critical battery level
        if battery_soc < 10 and self.can_take_action("emergency_preserve"):
            logger.warning(f"🚨 Critical battery level ({battery_soc:.1f}%) - activating emergency preservation")
            if self.controller.emergency_battery_preserve():
                action_taken = "emergency_preserve"
                self.record_action("emergency_preserve")
        
        # High inverter temperature
        elif inverter_temp > 70 and self.can_take_action("thermal_protection"):
            logger.warning(f"🌡️ High inverter temperature ({inverter_temp:.1f}°C) - reducing power limits")
            if self.controller.set_export_power_limit(5000, True):
                action_taken = "thermal_protection"
                self.record_action("thermal_protection")
        
        return action_taken
    
    def run_optimization_cycle(self) -> Dict[str, Optional[str]]:
        """Run a complete optimization cycle."""
        logger.info("🔄 Running optimization cycle...")
        
        if not self.controller.connect():
            logger.error("❌ Failed to connect to controller")
            return {"error": "connection_failed"}
        
        try:
            if not self.controller.update():
                logger.error("❌ Failed to update system data")
                return {"error": "data_update_failed"}
            
            state = self.controller.get_current_state()
            balance = self.controller.calculate_energy_balance()
            
            # Log current conditions
            logger.info(f"📊 Current: Solar={state['power']['solar_power']:.0f}W, "
                       f"Battery={state['battery']['level']:.1f}%, "
                       f"Grid={state['power']['grid_power']:.0f}W, "
                       f"Self-consumption={balance['self_consumption_ratio']:.1f}%")
            
            actions = {}
            
            # Run optimization strategies
            actions['battery_optimization'] = self.optimize_battery_charging(state)
            actions['grid_optimization'] = self.optimize_grid_interaction(state)
            actions['emergency_management'] = self.emergency_management(state)
            
            # Filter out None values
            actions = {k: v for k, v in actions.items() if v is not None}
            
            if actions:
                logger.info(f"✅ Actions taken: {', '.join(actions.values())}")
            else:
                logger.info("✅ System optimal, no actions needed")
            
            return actions
            
        finally:
            self.controller.disconnect()
    
    def run_continuous(self, interval_minutes: int = 5):
        """Run continuous optimization."""
        logger.info(f"🚀 Starting continuous self-consumption optimization (every {interval_minutes} minutes)")
        
        try:
            while True:
                start_time = time.time()
                
                try:
                    actions = self.run_optimization_cycle()
                    
                    if 'error' in actions:
                        logger.error(f"❌ Optimization cycle failed: {actions['error']}")
                    
                except Exception as e:
                    logger.error(f"❌ Unexpected error in optimization cycle: {e}")
                
                # Wait for next cycle
                elapsed = time.time() - start_time
                sleep_time = max(0, interval_minutes * 60 - elapsed)
                
                if sleep_time > 0:
                    logger.info(f"😴 Waiting {sleep_time:.0f}s until next optimization cycle...")
                    time.sleep(sleep_time)
                
        except KeyboardInterrupt:
            logger.info("🛑 Automation stopped by user")


def main():
    """Main function to demonstrate automation."""
    print("🤖 Self-Consumption Automation System")
    print("=" * 50)
    
    automation = SelfConsumptionAutomation()
    
    # Run a single optimization cycle first
    print("\n🔍 Running single optimization cycle...")
    actions = automation.run_optimization_cycle()
    
    if 'error' not in actions:
        print(f"✅ Optimization complete!")
        if actions:
            print(f"🎯 Actions taken: {', '.join(actions.values())}")
        else:
            print("🎯 System already optimal, no actions needed")
        
        # Ask user if they want continuous operation
        print(f"\n❓ Current solar conditions are excellent!")
        print(f"   Would you like to run continuous optimization?")
        print(f"   This will monitor and optimize every 5 minutes.")
        
        response = input("\n🤔 Start continuous automation? (y/N): ").strip().lower()
        
        if response in ['y', 'yes']:
            automation.run_continuous(interval_minutes=5)
        else:
            print("✅ Single optimization complete. Run again anytime!")
    else:
        print(f"❌ Optimization failed: {actions['error']}")


if __name__ == "__main__":
    main() 