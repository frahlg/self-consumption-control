#!/usr/bin/env python3
"""
Pure Energy Analysis Kernel
Immutable, side-effect-free analysis of energy system telemetry data.
"""

import math
import statistics
from dataclasses import dataclass
from typing import Deque, Optional, Dict, Any
from datetime import datetime


@dataclass(frozen=True)
class PowerStreamStats:
    """Statistics for a single power stream (immutable)."""
    current: float
    mean: float
    std_dev: float
    first_derivative: float  # Rate of change (W/s)
    oscillation_index: float  # RMS(power - mean) / |mean|
    min_value: float
    max_value: float
    sample_count: int


@dataclass(frozen=True)
class EnergyBalance:
    """Instantaneous energy balance analysis (immutable)."""
    solar_power: float
    battery_power: float  # Positive = charging, negative = discharging
    grid_power: float     # Positive = importing, negative = exporting
    load_power: float     # Always positive
    
    # Balance check: P_grid = P_solar - P_load - P_battery
    balance_error: float  # Should be close to zero for valid data
    balance_valid: bool   # |balance_error| < tolerance
    
    # Energy flow directions
    grid_importing: bool  # True if importing from grid
    grid_exporting: bool  # True if exporting to grid
    battery_charging: bool  # True if battery charging
    battery_discharging: bool  # True if battery discharging


@dataclass(frozen=True)
class EnergyRatios:
    """Energy efficiency and coverage ratios (immutable)."""
    self_consumption_ratio: float  # (P_solar - P_grid_export) / P_solar
    solar_coverage_ratio: float    # P_solar / P_load
    battery_utilization_ratio: float  # |P_battery| / P_solar
    grid_dependency_ratio: float   # P_grid_import / P_load
    
    # System operating mode
    self_consuming: bool    # Using own solar production
    grid_feeding: bool     # Exporting excess solar
    grid_dependent: bool   # Importing from grid
    battery_active: bool   # Battery charging or discharging


@dataclass(frozen=True)
class AnalysisSnapshot:
    """Complete immutable analysis snapshot of energy system state."""
    timestamp: datetime
    analysis_window_seconds: float
    sample_count: int
    
    # Power stream statistics
    solar_stats: PowerStreamStats
    battery_stats: PowerStreamStats
    grid_stats: PowerStreamStats
    load_stats: PowerStreamStats
    
    # System analysis
    energy_balance: EnergyBalance
    energy_ratios: EnergyRatios
    
    # Overall system health
    data_quality_score: float  # 0.0 to 1.0 based on balance validity and sample count
    system_stability_index: float  # Average oscillation index across all streams


def _calculate_power_stream_stats(buffer: Deque[float], sample_rate: float) -> PowerStreamStats:
    """
    Calculate comprehensive statistics for a single power stream.
    Pure function with no side effects.
    """
    if len(buffer) == 0:
        return PowerStreamStats(
            current=0.0, mean=0.0, std_dev=0.0, first_derivative=0.0,
            oscillation_index=0.0, min_value=0.0, max_value=0.0, sample_count=0
        )
    
    data = list(buffer)  # Convert to list for calculations
    sample_count = len(data)
    
    # Basic statistics
    current = data[-1]
    mean = statistics.mean(data)
    std_dev = statistics.stdev(data) if sample_count > 1 else 0.0
    min_value = min(data)
    max_value = max(data)
    
    # First derivative (rate of change)
    first_derivative = 0.0
    if sample_count >= 10:  # Need sufficient samples for stable derivative
        # Use last 10 points for derivative calculation
        recent_data = data[-10:]
        x = list(range(len(recent_data)))
        y = recent_data
        n = len(x)
        
        # Linear regression slope
        sum_x = sum(x)
        sum_y = sum(y)
        sum_xy = sum(x[i] * y[i] for i in range(n))
        sum_x2 = sum(x[i] * x[i] for i in range(n))
        
        if n * sum_x2 - sum_x * sum_x != 0:
            slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x * sum_x)
            first_derivative = slope * sample_rate  # Convert to W/s
    
    # Oscillation index: RMS(power - mean) / |mean|
    oscillation_index = 0.0
    if abs(mean) > 1.0:  # Avoid division by very small numbers
        rms_deviation = math.sqrt(sum((x - mean) ** 2 for x in data) / sample_count)
        oscillation_index = rms_deviation / abs(mean)
    
    return PowerStreamStats(
        current=current,
        mean=mean,
        std_dev=std_dev,
        first_derivative=first_derivative,
        oscillation_index=oscillation_index,
        min_value=min_value,
        max_value=max_value,
        sample_count=sample_count
    )


def _calculate_energy_balance(solar: float, battery: float, grid: float, load: float,
                            tolerance: float = 50.0) -> EnergyBalance:
    """
    Calculate instantaneous energy balance.
    Pure function implementing: P_solar + P_grid = P_load + P_battery
    With solar NEGATIVE (generation) and load POSITIVE (consumption)
    """
    # Energy balance from house perspective: P_solar + P_grid = P_load + P_battery  
    # Where: P_solar < 0 (generation), P_grid > 0 = import, P_grid < 0 = export
    # P_load > 0 (consumption), P_battery > 0 = charging, P_battery < 0 = discharging
    balance_error = solar + grid - load - battery
    balance_valid = abs(balance_error) < tolerance
    
    # Energy flow directions
    grid_importing = grid > 10.0  # Small threshold to avoid noise
    grid_exporting = grid < -10.0
    battery_charging = battery > 10.0
    battery_discharging = battery < -10.0
    
    return EnergyBalance(
        solar_power=solar,
        battery_power=battery,
        grid_power=grid,
        load_power=load,
        balance_error=balance_error,
        balance_valid=balance_valid,
        grid_importing=grid_importing,
        grid_exporting=grid_exporting,
        battery_charging=battery_charging,
        battery_discharging=battery_discharging
    )


def _calculate_energy_ratios(solar: float, battery: float, grid: float, load: float) -> EnergyRatios:
    """
    Calculate energy efficiency and coverage ratios.
    Pure function with safe division handling.
    Solar is NEGATIVE (generation), load is POSITIVE (consumption).
    """
    # Convert solar to positive for ratio calculations (generation amount)
    solar_generation = abs(solar)  # Convert negative to positive generation
    
    # Self-consumption ratio: (P_solar_generation - P_grid_export) / P_solar_generation
    self_consumption_ratio = 0.0
    if solar_generation > 10.0:  # Avoid division by small solar values
        grid_export = max(0, -grid)  # Only count export (negative grid -> positive export)
        self_consumption_ratio = (solar_generation - grid_export) / solar_generation
        self_consumption_ratio = max(0.0, min(1.0, self_consumption_ratio))  # Clamp to [0,1]
    
    # Solar coverage ratio: P_solar_generation / P_load
    solar_coverage_ratio = 0.0
    if load > 10.0:
        solar_coverage_ratio = solar_generation / load
    
    # Battery utilization ratio: |P_battery| / P_solar_generation
    battery_utilization_ratio = 0.0
    if solar_generation > 10.0:
        battery_utilization_ratio = abs(battery) / solar_generation
    
    # Grid dependency ratio: P_grid_import / P_load
    grid_dependency_ratio = 0.0
    if load > 10.0:
        grid_import = max(0, grid)  # Only count import (positive grid)
        grid_dependency_ratio = grid_import / load
    
    # System operating modes
    self_consuming = self_consumption_ratio > 0.1
    grid_feeding = grid < -50.0  # Significant export
    grid_dependent = grid > 50.0  # Significant import
    battery_active = abs(battery) > 50.0  # Significant battery activity
    
    return EnergyRatios(
        self_consumption_ratio=self_consumption_ratio,
        solar_coverage_ratio=solar_coverage_ratio,
        battery_utilization_ratio=battery_utilization_ratio,
        grid_dependency_ratio=grid_dependency_ratio,
        self_consuming=self_consuming,
        grid_feeding=grid_feeding,
        grid_dependent=grid_dependent,
        battery_active=battery_active
    )


def analyze(solar_buffer: Deque[float], battery_buffer: Deque[float], 
           grid_buffer: Deque[float], load_buffer: Deque[float],
           now_ts: datetime, sample_rate: float = 2.0,
           window_seconds: float = 30.0) -> AnalysisSnapshot:
    """
    Pure analysis kernel for energy system telemetry.
    
    Args:
        solar_buffer: Ring buffer of solar power samples (W)
        battery_buffer: Ring buffer of battery power samples (W, +charge/-discharge)
        grid_buffer: Ring buffer of grid power samples (W, +import/-export)
        load_buffer: Ring buffer of load power samples (W, always positive)
        now_ts: Current timestamp
        sample_rate: Sampling rate (Hz)
        window_seconds: Analysis window duration (s)
    
    Returns:
        AnalysisSnapshot: Immutable analysis results
        
    This function is pure - no globals, no logging, no I/O.
    """
    # Calculate statistics for each power stream
    solar_stats = _calculate_power_stream_stats(solar_buffer, sample_rate)
    battery_stats = _calculate_power_stream_stats(battery_buffer, sample_rate)
    grid_stats = _calculate_power_stream_stats(grid_buffer, sample_rate)
    load_stats = _calculate_power_stream_stats(load_buffer, sample_rate)
    
    # Get current instantaneous values
    solar_current = solar_stats.current
    battery_current = battery_stats.current
    grid_current = grid_stats.current
    load_current = load_stats.current
    
    # Calculate energy balance
    energy_balance = _calculate_energy_balance(
        solar_current, battery_current, grid_current, load_current
    )
    
    # Calculate energy ratios
    energy_ratios = _calculate_energy_ratios(
        solar_current, battery_current, grid_current, load_current
    )
    
    # Data quality score (0.0 to 1.0)
    min_samples = min(solar_stats.sample_count, battery_stats.sample_count,
                     grid_stats.sample_count, load_stats.sample_count)
    expected_samples = window_seconds * sample_rate
    sample_quality = min(1.0, min_samples / expected_samples) if expected_samples > 0 else 0.0
    balance_quality = 1.0 if energy_balance.balance_valid else 0.5
    data_quality_score = (sample_quality + balance_quality) / 2.0
    
    # System stability index (average oscillation across all streams)
    oscillations = [
        solar_stats.oscillation_index,
        battery_stats.oscillation_index,
        grid_stats.oscillation_index,
        load_stats.oscillation_index
    ]
    system_stability_index = statistics.mean(oscillations)
    
    return AnalysisSnapshot(
        timestamp=now_ts,
        analysis_window_seconds=window_seconds,
        sample_count=min_samples,
        solar_stats=solar_stats,
        battery_stats=battery_stats,
        grid_stats=grid_stats,
        load_stats=load_stats,
        energy_balance=energy_balance,
        energy_ratios=energy_ratios,
        data_quality_score=data_quality_score,
        system_stability_index=system_stability_index
    )


def analyze_from_collector(collector, now_ts: datetime) -> AnalysisSnapshot:
    """
    Convenience function to analyze data from a TelemetryCollector.
    
    Args:
        collector: TelemetryCollector instance with ring buffers
        now_ts: Current timestamp
        
    Returns:
        AnalysisSnapshot: Comprehensive analysis results
    """
    buffer_info = collector.get_buffer_info()
    
    return analyze(
        solar_buffer=collector.get_short_buffer('solar_power'),
        battery_buffer=collector.get_short_buffer('battery_power'),
        grid_buffer=collector.get_short_buffer('grid_power'),
        load_buffer=collector.get_short_buffer('load_power'),
        now_ts=now_ts,
        sample_rate=buffer_info['sample_rate'],
        window_seconds=buffer_info['short_window_seconds']
    ) 