/** Core types shared across the frontend — mirrors backend API responses. */

export interface TripSummary {
  id: number;
  start_time: string;
  end_time: string | null;
  distance_km: number;
  duration_seconds: number;
  max_speed_kmh: number | null;
  avg_speed_kmh: number | null;
  energy_consumed_kwh: number | null;
  start_lat: number | null;
  start_lon: number | null;
  end_lat: number | null;
  end_lon: number | null;
  has_gps: boolean;
  event_count: number;
  waypoint_count: number;
}

export interface Waypoint {
  id: number;
  timestamp: string;
  latitude: number | null;
  longitude: number | null;
  heading: number | null;
  speed_mps: number | null;
  autopilot_state: string | null;
  gap_after: boolean;
}

export interface DrivingEvent {
  id: number;
  trip_id: number | null;
  timestamp: string;
  event_type: EventType;
  severity: Severity;
  description: string | null;
  latitude: number | null;
  longitude: number | null;
  has_gps: boolean;
  video_path: string | null;
  frame_offset: number | null;
}

export type EventType =
  | "emergency_brake"
  | "harsh_brake"
  | "hard_acceleration"
  | "sharp_turn"
  | "speeding"
  | "autopilot_disengage"
  | "battery_low";

export type Severity = "info" | "warning" | "critical";

export interface TripDetail extends TripSummary {
  waypoints: Waypoint[];
  events: DrivingEvent[];
}

export interface TelemetryFrame {
  timestamp: string;
  speed_mps: number;
  speed_kmh: number;
  gear: string;
  odometer_km: number | null;
  battery_level_pct: number | null;
  battery_range_km: number | null;
  power_kw: number | null;
  latitude: number | null;
  longitude: number | null;
  heading: number | null;
  is_autopilot_on: boolean;
  autopilot_state: string | null;
  video_path: string | null;
  frame_offset: number | null;
  has_gps: boolean;
}

export interface StatsOverview {
  total_trips: number;
  total_events: number;
  total_telemetry_snapshots: number;
  total_indexed_files: number;
  total_distance_km: number;
  total_duration_hours: number;
  trips_with_gps_pct: number;
  trips_without_gps_pct: number;
}

export interface TripSummary30d {
  period_days: number;
  trip_count: number;
  total_distance_km: number;
  total_duration_hours: number;
  total_energy_kwh: number;
  avg_distance_per_trip_km: number;
  avg_efficiency_wh_per_km: number;
}

export interface EventDistribution {
  period_days: number;
  total_events: number;
  by_type: Record<string, number>;
  by_severity: Record<string, number>;
}

export interface DrivingScore {
  score: number | null;
  total_harsh_events?: number;
  events_per_100km?: number;
  distance_km?: number;
  period_days?: number;
  reason?: string;
}

export interface DashboardStats {
  overview: StatsOverview;
  trip_summary: TripSummary30d;
  event_distribution: EventDistribution;
  driving_score: DrivingScore;
}

export interface DailyTripData {
  date: string;
  trip_count: number;
  distance_km: number;
  duration_hours: number;
}

export interface BatteryTrend {
  timestamp: string;
  battery_pct: number;
  range_km: number | null;
}

export interface SpeedProfilePoint {
  timestamp: string;
  speed_kmh: number;
  power_kw: number | null;
  is_autopilot_on: boolean;
}

export interface GeoResult {
  latitude: number;
  longitude: number;
  address: string | null;
  city: string | null;
  province: string | null;
  country: string | null;
}
