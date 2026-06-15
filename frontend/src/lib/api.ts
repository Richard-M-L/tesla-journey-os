/** API client for Tesla Journey OS backend. */

import type {
  DashboardStats,
  TripSummary,
  TripDetail,
  DrivingEvent,
  TelemetryFrame,
  DailyTripData,
  BatteryTrend,
  DrivingScore,
  SpeedProfilePoint,
  GeoResult,
} from "@/types";

const BASE = "/api";

async function get<T>(path: string, params?: Record<string, string | number>): Promise<T> {
  const url = new URL(`${BASE}${path}`, window.location.origin);
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null) url.searchParams.set(k, String(v));
    });
  }
  const res = await fetch(url);
  if (!res.ok) throw new Error(`API error: ${res.status} ${res.statusText}`);
  return res.json();
}

export const api = {
  // Stats
  getDashboardStats: () => get<DashboardStats>("/stats/dashboard"),

  // Trips
  listTrips: (opts?: { days?: number; limit?: number; offset?: number }) =>
    get<{ trips: TripSummary[] }>("/trips", opts as Record<string, string | number>),

  getTrip: (id: number) => get<TripDetail>(`/trips/${id}`),

  getTripTelemetry: (id: number, sampleRate?: number) =>
    get<{ trip_id: number; sample_rate: number; frame_count: number; telemetry: TelemetryFrame[] }>(
      `/trips/${id}/telemetry`,
      { sample_rate: sampleRate ?? 30 }
    ),

  getTripSpeedProfile: (id: number) =>
    get<{ trip_id: number; profile: SpeedProfilePoint[] }>(`/trips/${id}/speed-profile`),

  // Events
  listEvents: (opts?: {
    event_type?: string;
    severity?: string;
    trip_id?: number;
    days?: number;
    limit?: number;
    offset?: number;
  }) => get<{ events: DrivingEvent[] }>("/events", opts as Record<string, string | number>),

  // Analytics
  getDailyTrips: (days?: number) =>
    get<{ daily_trips: DailyTripData[] }>("/analytics/trips/daily", { days: days ?? 30 }),

  getBatteryTrend: (days?: number) =>
    get<{ battery_trend: BatteryTrend[] }>("/analytics/battery", { days: days ?? 30 }),

  getDrivingScore: (days?: number) => get<DrivingScore>("/analytics/score", { days: days ?? 30 }),

  // Geo
  reverseGeocode: (lat: number, lon: number, provider?: string) =>
    get<GeoResult>("/geo/reverse", { lat, lon, provider: provider ?? "cache" }),
};
