// InfluxDB Flux Queries for High-Frequency Data Verification
// Use these queries in InfluxDB UI or Grafana to verify 50Hz data collection

// =============================================================================
// 1. Samples-per-second (should show ~50 for perfect stream)
// =============================================================================

from(bucket: "data")
  |> range(start: -10m)                                         // or v.timeRangeStart
  |> filter(fn: (r) => r["_measurement"] == "energy_system" and
                       r["source"]       == "sungrow_controller" and
                       r["_field"]       == "solar_power")
  |> aggregateWindow(every: 1s, fn: count, createEmpty: false)
  |> yield(name: "samples_per_second")

// Expected result: ~50 points per second for perfect 50Hz stream
// Values < 50 indicate missing data points
// Use this for Grafana alert: threshold at 48 triggers "missing packets"

// =============================================================================
// 2. Average Δt (delta time) inside 5-second windows
// =============================================================================

from(bucket: "data")
  |> range(start: -10m)
  |> filter(fn: (r) => r["_measurement"] == "energy_system" and
                       r["source"]       == "sungrow_controller" and
                       r["_field"]       == "solar_power")
  |> elapsed(unit: 1ms)                          // adds _elapsed (ms)
  |> aggregateWindow(every: 5s,
       fn: mean,
       column: "_elapsed",
       createEmpty: false)
  |> rename(columns: {_elapsed: "_value"})
  |> yield(name: "avg_delta_ms")

// Expected result: ~20 ms (1000ms/50Hz = 20ms)
// Spikes indicate lag; plateaus >20ms mean the loop is falling behind
// Use this for Grafana alert: threshold at 25ms triggers "loop lagging"

// =============================================================================
// 3. Data Quality Dashboard Query (combined metrics)
// =============================================================================

// Samples per second with quality indicators
samples = from(bucket: "data")
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r["_measurement"] == "energy_system" and
                       r["source"] == "sungrow_controller" and
                       r["_field"] == "solar_power")
  |> aggregateWindow(every: 1s, fn: count, createEmpty: false)
  |> map(fn: (r) => ({
      _time: r._time,
      _value: r._value,
      _field: "samples_per_second",
      quality: if r._value >= 48 then "good" else "poor"
    }))

// Timing precision
timing = from(bucket: "data")
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r["_measurement"] == "energy_system" and
                       r["source"] == "sungrow_controller" and
                       r["_field"] == "solar_power")
  |> elapsed(unit: 1ms)
  |> aggregateWindow(every: 5s, fn: mean, column: "_elapsed", createEmpty: false)
  |> map(fn: (r) => ({
      _time: r._time,
      _value: r._elapsed,
      _field: "avg_delta_ms",
      quality: if r._elapsed <= 25.0 then "good" else "poor"
    }))

// Combine both metrics
union(tables: [samples, timing])
  |> yield(name: "data_quality")

// =============================================================================
// 4. Real-time Solar Power with Quality Overlay
// =============================================================================

from(bucket: "data")
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r["_measurement"] == "energy_system" and
                       r["source"] == "sungrow_controller" and
                       r["_field"] == "solar_power")
  |> yield(name: "solar_power_50hz")

// =============================================================================
// 5. System Health Summary (for alerts)
// =============================================================================

// Calculate health metrics over last 5 minutes
health_window = from(bucket: "data")
  |> range(start: -5m)
  |> filter(fn: (r) => r["_measurement"] == "energy_system" and
                       r["source"] == "sungrow_controller" and
                       r["_field"] == "solar_power")

// Sample rate check
sample_rate = health_window
  |> aggregateWindow(every: 1s, fn: count, createEmpty: false)
  |> mean()
  |> map(fn: (r) => ({
      _time: now(),
      _field: "avg_sample_rate",
      _value: r._value,
      status: if r._value >= 48.0 then "healthy" else "degraded"
    }))

// Timing precision check  
timing_precision = health_window
  |> elapsed(unit: 1ms)
  |> mean(column: "_elapsed")
  |> map(fn: (r) => ({
      _time: now(),
      _field: "avg_timing_ms", 
      _value: r._elapsed,
      status: if r._elapsed <= 25.0 then "healthy" else "degraded"
    }))

union(tables: [sample_rate, timing_precision])
  |> yield(name: "system_health")

// =============================================================================
// Usage Instructions:
//
// 1. Copy individual queries into InfluxDB Data Explorer
// 2. Use "samples_per_second" query for Grafana panel with threshold alerts
// 3. Use "avg_delta_ms" query for timing precision monitoring  
// 4. Use "data_quality" for combined dashboard view
// 5. Set up InfluxDB Tasks to run "system_health" every minute for alerting
//
// Grafana Alert Thresholds:
// - samples_per_second < 48: "Missing data packets"
// - avg_delta_ms > 25: "Collection loop lagging"
// ============================================================================= 