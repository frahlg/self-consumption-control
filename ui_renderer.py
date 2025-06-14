#!/usr/bin/env python3
"""
UI Renderer for Energy Management System
Pure UI rendering functions that convert analysis snapshots to Rich components.
"""

from typing import Union
from datetime import datetime

from rich.console import RenderableType
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns
from rich.text import Text
from rich.align import Align
from rich.layout import Layout
from rich.progress import Progress, BarColumn, TextColumn
from rich.rule import Rule

from analysis import AnalysisSnapshot, PowerStreamStats, EnergyBalance, EnergyRatios


def _format_power(watts: float) -> str:
    """Format power values with appropriate units and colors."""
    if abs(watts) >= 1_000_000:
        return f"{watts/1_000_000:.2f} MW"
    elif abs(watts) >= 1000:
        return f"{watts/1000:.2f} kW"
    else:
        return f"{watts:.0f} W"


def _format_percentage(ratio: float) -> str:
    """Format ratio as percentage."""
    return f"{ratio * 100:.1f}%"


def _get_power_color(watts: float, type_hint: str = "generic") -> str:
    """Get color for power values based on magnitude and type."""
    if type_hint == "solar":
        if watts > 5000: return "bright_yellow"
        elif watts > 1000: return "yellow"
        elif watts > 0: return "dim yellow"
        else: return "dim white"
    elif type_hint == "battery":
        if watts > 500: return "bright_green"  # Heavy charging
        elif watts > 0: return "green"  # Charging
        elif watts < -500: return "bright_red"  # Heavy discharging
        elif watts < 0: return "red"  # Discharging
        else: return "dim white"  # Idle
    elif type_hint == "grid":
        if watts > 500: return "bright_cyan"  # Heavy export
        elif watts > 0: return "cyan"  # Export
        elif watts < -500: return "bright_magenta"  # Heavy import
        elif watts < 0: return "magenta"  # Import
        else: return "dim white"  # Balanced
    else:
        if abs(watts) > 1000: return "bright_white"
        else: return "white"


def _render_power_stream_table(solar: PowerStreamStats, battery: PowerStreamStats,
                             grid: PowerStreamStats, load: PowerStreamStats) -> Table:
    """Render power streams as a Rich table."""
    table = Table(title="⚡ Power Stream Analysis", title_style="bold bright_blue")
    
    table.add_column("Stream", style="bold", width=12)
    table.add_column("Current", justify="right", width=12)
    table.add_column("Average", justify="right", width=12)
    table.add_column("Range", justify="right", width=15)
    table.add_column("Trend", justify="right", width=12)
    table.add_column("Stability", justify="right", width=10)
    
    # Solar row
    solar_current = Text(_format_power(solar.current), style=_get_power_color(solar.current, "solar"))
    solar_avg = Text(_format_power(solar.mean), style="dim yellow")
    solar_range = Text(f"{_format_power(solar.min_value)} to {_format_power(solar.max_value)}", style="dim white")
    solar_trend = Text(f"{solar.first_derivative:+.1f} W/s", 
                      style="green" if solar.first_derivative > 0 else "red" if solar.first_derivative < 0 else "dim white")
    solar_stability = Text(f"{solar.oscillation_index:.3f}", 
                          style="red" if solar.oscillation_index > 0.2 else "yellow" if solar.oscillation_index > 0.1 else "green")
    table.add_row("☀️ Solar", solar_current, solar_avg, solar_range, solar_trend, solar_stability)
    
    # Battery row
    battery_current = Text(_format_power(battery.current), style=_get_power_color(battery.current, "battery"))
    battery_avg = Text(_format_power(battery.mean), style="dim green")
    battery_range = Text(f"{_format_power(battery.min_value)} to {_format_power(battery.max_value)}", style="dim white")
    battery_trend = Text(f"{battery.first_derivative:+.1f} W/s",
                        style="green" if battery.first_derivative > 0 else "red" if battery.first_derivative < 0 else "dim white")
    battery_stability = Text(f"{battery.oscillation_index:.3f}",
                           style="red" if battery.oscillation_index > 0.2 else "yellow" if battery.oscillation_index > 0.1 else "green")
    table.add_row("🔋 Battery", battery_current, battery_avg, battery_range, battery_trend, battery_stability)
    
    # Grid row
    grid_current = Text(_format_power(grid.current), style=_get_power_color(grid.current, "grid"))
    grid_avg = Text(_format_power(grid.mean), style="dim cyan")
    grid_range = Text(f"{_format_power(grid.min_value)} to {_format_power(grid.max_value)}", style="dim white")
    grid_trend = Text(f"{grid.first_derivative:+.1f} W/s",
                     style="green" if grid.first_derivative > 0 else "red" if grid.first_derivative < 0 else "dim white")
    grid_stability = Text(f"{grid.oscillation_index:.3f}",
                         style="red" if grid.oscillation_index > 0.2 else "yellow" if grid.oscillation_index > 0.1 else "green")
    table.add_row("🏭 Grid", grid_current, grid_avg, grid_range, grid_trend, grid_stability)
    
    # Load row
    load_current = Text(_format_power(load.current), style=_get_power_color(load.current))
    load_avg = Text(_format_power(load.mean), style="dim white")
    load_range = Text(f"{_format_power(load.min_value)} to {_format_power(load.max_value)}", style="dim white")
    load_trend = Text(f"{load.first_derivative:+.1f} W/s",
                     style="green" if load.first_derivative > 0 else "red" if load.first_derivative < 0 else "dim white")
    load_stability = Text(f"{load.oscillation_index:.3f}",
                         style="red" if load.oscillation_index > 0.2 else "yellow" if load.oscillation_index > 0.1 else "green")
    table.add_row("🏠 Load", load_current, load_avg, load_range, load_trend, load_stability)
    
    return table


def _render_energy_balance_panel(balance: EnergyBalance) -> Panel:
    """Render energy balance as a Rich panel with thermodynamic equation."""
    
    # Create the thermodynamic equation display
    equation_text = Text()
    equation_text.append("P_solar + P_grid = P_load + P_battery\n", style="bold bright_white")
    
    # Show actual values with colors
    equation_text.append(f"{_format_power(balance.solar_power)}", style=_get_power_color(balance.solar_power, "solar"))
    equation_text.append(" + ", style="dim white")
    equation_text.append(f"{_format_power(balance.grid_power)}", style=_get_power_color(balance.grid_power, "grid"))
    equation_text.append(" = ", style="bold white")
    equation_text.append(f"{_format_power(balance.load_power)}", style="white")
    equation_text.append(" + ", style="dim white")
    equation_text.append(f"{_format_power(balance.battery_power)}", style=_get_power_color(balance.battery_power, "battery"))
    
    # Show balance check
    left_side = balance.solar_power + balance.grid_power
    right_side = balance.load_power + balance.battery_power
    equation_text.append(f"\n{_format_power(left_side)} = {_format_power(right_side)}", style="dim white")
    
    # Balance error
    equation_text.append(f"\nBalance Error: ", style="dim white")
    error_color = "green" if balance.balance_valid else "red"
    equation_text.append(f"{_format_power(balance.balance_error)}", style=error_color)
    equation_text.append(" ✅" if balance.balance_valid else " ❌", style=error_color)
    
    # Energy flow status
    equation_text.append("\n\nEnergy Flow Status:\n", style="bold dim white")
    
    if balance.grid_importing:
        equation_text.append("🏭➡️🏠 Grid Importing", style="magenta")
    elif balance.grid_exporting:
        equation_text.append("🏠➡️🏭 Grid Exporting", style="cyan")
    else:
        equation_text.append("🏭⚖️🏠 Grid Balanced", style="dim white")
    
    equation_text.append("  |  ", style="dim white")
    
    if balance.battery_charging:
        equation_text.append("🔋⬆️ Battery Charging", style="green")
    elif balance.battery_discharging:
        equation_text.append("🔋⬇️ Battery Discharging", style="red")
    else:
        equation_text.append("🔋⏸️ Battery Idle", style="dim white")
    
    panel_title = "⚖️ Energy Balance" + (" ✅" if balance.balance_valid else " ❌")
    panel_style = "green" if balance.balance_valid else "red"
    
    return Panel(equation_text, title=panel_title, border_style=panel_style)


def _render_efficiency_metrics_table(ratios: EnergyRatios) -> Table:
    """Render energy efficiency ratios as a Rich table."""
    table = Table(title="📊 Energy Efficiency Metrics", title_style="bold bright_green")
    
    table.add_column("Metric", style="bold", width=20)
    table.add_column("Value", justify="right", width=12)
    table.add_column("Status", width=15)
    table.add_column("Description", width=30)
    
    # Self-consumption ratio
    sc_color = "bright_green" if ratios.self_consumption_ratio > 0.8 else "green" if ratios.self_consumption_ratio > 0.6 else "yellow"
    sc_status = "Excellent" if ratios.self_consumption_ratio > 0.8 else "Good" if ratios.self_consumption_ratio > 0.6 else "Moderate"
    table.add_row(
        "🎯 Self-Consumption",
        Text(_format_percentage(ratios.self_consumption_ratio), style=sc_color),
        Text(sc_status, style=sc_color),
        "Solar energy used locally"
    )
    
    # Solar coverage ratio
    coverage_color = "bright_yellow" if ratios.solar_coverage_ratio > 1.0 else "yellow" if ratios.solar_coverage_ratio > 0.8 else "dim yellow"
    coverage_status = "Excess" if ratios.solar_coverage_ratio > 1.0 else "High" if ratios.solar_coverage_ratio > 0.8 else "Partial"
    table.add_row(
        "☀️ Solar Coverage",
        Text(_format_percentage(ratios.solar_coverage_ratio), style=coverage_color),
        Text(coverage_status, style=coverage_color),
        "Load covered by solar"
    )
    
    # Battery utilization
    batt_color = "bright_blue" if ratios.battery_utilization_ratio > 0.3 else "blue" if ratios.battery_utilization_ratio > 0.1 else "dim blue"
    batt_status = "High" if ratios.battery_utilization_ratio > 0.3 else "Active" if ratios.battery_utilization_ratio > 0.1 else "Low"
    table.add_row(
        "🔋 Battery Utilization",
        Text(_format_percentage(ratios.battery_utilization_ratio), style=batt_color),
        Text(batt_status, style=batt_color),
        "Battery activity vs solar"
    )
    
    # Grid dependency
    grid_dep_color = "red" if ratios.grid_dependency_ratio > 0.5 else "yellow" if ratios.grid_dependency_ratio > 0.2 else "green"
    grid_dep_status = "High" if ratios.grid_dependency_ratio > 0.5 else "Moderate" if ratios.grid_dependency_ratio > 0.2 else "Low"
    table.add_row(
        "🏭 Grid Dependency",
        Text(_format_percentage(ratios.grid_dependency_ratio), style=grid_dep_color),
        Text(grid_dep_status, style=grid_dep_color),
        "Load reliance on grid"
    )
    
    return table


def _render_system_status_banner(snapshot: AnalysisSnapshot) -> Panel:
    """Render system status as a headline banner."""
    
    # Determine primary operating mode
    ratios = snapshot.energy_ratios
    modes = []
    
    if ratios.self_consuming:
        modes.append("🔄 SELF-CONSUMING")
    if ratios.grid_feeding:
        modes.append("⬇️ GRID-FEEDING")
    if ratios.grid_dependent:
        modes.append("⬆️ GRID-DEPENDENT")
    if ratios.battery_active:
        modes.append("🔋 BATTERY-ACTIVE")
    
    primary_mode = " + ".join(modes) if modes else "⚪ STANDBY"
    
    # Create banner text
    banner_text = Text()
    banner_text.append(f"🏠 ENERGY MANAGEMENT SYSTEM\n", style="bold bright_white")
    banner_text.append(f"Mode: {primary_mode}\n", style="bold bright_cyan")
    banner_text.append(f"Timestamp: {snapshot.timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n", style="dim white")
    
    # System health indicators
    quality_color = "bright_green" if snapshot.data_quality_score > 0.9 else "green" if snapshot.data_quality_score > 0.7 else "yellow"
    stability_color = "green" if snapshot.system_stability_index < 0.1 else "yellow" if snapshot.system_stability_index < 0.2 else "red"
    
    banner_text.append(f"Data Quality: ", style="dim white")
    banner_text.append(f"{_format_percentage(snapshot.data_quality_score)}", style=quality_color)
    banner_text.append(f"  |  Stability: ", style="dim white")
    banner_text.append(f"{snapshot.system_stability_index:.3f}", style=stability_color)
    banner_text.append(f"  |  Samples: {snapshot.sample_count}", style="dim white")
    
    return Panel(banner_text, title="🏠 System Status", border_style="bright_blue", padding=(0, 1))


def _render_snapshot_metadata(snapshot: AnalysisSnapshot) -> Table:
    """Render snapshot metadata as a small table."""
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("Key", style="dim white")
    table.add_column("Value", style="white")
    
    table.add_row("Analysis Window", f"{snapshot.analysis_window_seconds}s")
    table.add_row("Sample Count", str(snapshot.sample_count))
    table.add_row("Data Quality", _format_percentage(snapshot.data_quality_score))
    table.add_row("System Stability", f"{snapshot.system_stability_index:.3f}")
    
    return table


def render(snapshot: AnalysisSnapshot) -> RenderableType:
    """
    Convert analysis snapshot to Rich renderable components.
    
    Args:
        snapshot: Complete analysis snapshot from pure analysis kernel
        
    Returns:
        RenderableType: Rich layout ready for Live display
        
    This function is pure - no side effects, no I/O, no globals.
    """
    
    # Create main layout
    layout = Layout()
    
    # Split into header and body
    layout.split_column(
        Layout(name="header", size=6),
        Layout(name="body")
    )
    
    # Header contains system status banner
    layout["header"].update(_render_system_status_banner(snapshot))
    
    # Body contains main content in columns
    layout["body"].split_row(
        Layout(name="left", ratio=2),
        Layout(name="right", ratio=1)
    )
    
    # Left side: power streams and energy balance
    layout["left"].split_column(
        Layout(name="power_table", ratio=2),
        Layout(name="balance_panel", ratio=1)
    )
    
    layout["left"]["power_table"].update(
        _render_power_stream_table(
            snapshot.solar_stats,
            snapshot.battery_stats, 
            snapshot.grid_stats,
            snapshot.load_stats
        )
    )
    
    layout["left"]["balance_panel"].update(
        _render_energy_balance_panel(snapshot.energy_balance)
    )
    
    # Right side: efficiency metrics and metadata
    layout["right"].split_column(
        Layout(name="efficiency", ratio=2),
        Layout(name="metadata", ratio=1)
    )
    
    layout["right"]["efficiency"].update(
        _render_efficiency_metrics_table(snapshot.energy_ratios)
    )
    
    layout["right"]["metadata"].update(
        Panel(_render_snapshot_metadata(snapshot), title="📋 Analysis Info", border_style="dim white")
    )
    
    return layout 