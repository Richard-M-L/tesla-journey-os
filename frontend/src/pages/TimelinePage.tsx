import { useState } from "react";
import { Link } from "react-router-dom";
import { useApi } from "@/hooks/useApi";
import { api } from "@/lib/api";
import { formatDistance, formatDuration, formatDate, formatDateShort, eventTypeLabel, severityColor } from "@/lib/utils";
import type { TripSummary } from "@/types";
import { ChevronRight, MapPin, MapPinOff, Clock, Gauge } from "lucide-react";

export function TimelinePage() {
  const [days, setDays] = useState<number | undefined>(30);
  const { data, loading } = useApi<{ trips: TripSummary[] }>(
    () => api.listTrips({ days, limit: 100 })
  );

  const trips = data?.trips ?? [];

  return (
    <div className="max-w-4xl space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold tracking-tight">时间线</h1>
        <select
          value={days ?? "all"}
          onChange={(e) => setDays(e.target.value === "all" ? undefined : Number(e.target.value))}
          className="bg-tesla-gray-800 border border-tesla-gray-700 rounded-lg px-3 py-1.5 text-sm text-tesla-gray-300"
        >
          <option value={7}>最近 7 天</option>
          <option value={30}>最近 30 天</option>
          <option value={90}>最近 90 天</option>
          <option value="all">全部</option>
        </select>
      </div>

      {loading ? (
        <div className="animate-pulse text-tesla-gray-400">加载中...</div>
      ) : trips.length === 0 ? (
        <div className="text-center py-16 text-tesla-gray-500">
          <Clock className="w-12 h-12 mx-auto mb-3 opacity-30" />
          <p className="text-lg">暂无行程数据</p>
          <p className="text-sm mt-1">导入遥测数据后，行程将自动出现在这里</p>
        </div>
      ) : (
        <div className="space-y-3">
          {trips.map((trip) => (
            <Link
              key={trip.id}
              to={`/trips/${trip.id}`}
              className="block p-4 rounded-xl bg-tesla-gray-800/50 border border-tesla-gray-800 hover:border-tesla-gray-700 transition-colors"
            >
              <div className="flex items-center justify-between">
                <div className="flex-1 min-w-0">
                  {/* Header row */}
                  <div className="flex items-center gap-3 mb-2">
                    <span className="text-sm font-semibold">
                      {formatDate(trip.start_time)}
                    </span>
                    {trip.has_gps ? (
                      <span className="flex items-center gap-1 text-xs text-tesla-gray-500">
                        <MapPin className="w-3 h-3" />
                        GPS
                      </span>
                    ) : (
                      <span className="flex items-center gap-1 text-xs text-amber-600">
                        <MapPinOff className="w-3 h-3" />
                        无 GPS
                      </span>
                    )}
                  </div>

                  {/* Stats row */}
                  <div className="flex items-center gap-4 text-sm text-tesla-gray-400">
                    <span className="flex items-center gap-1">
                      <RouteIcon />
                      {formatDistance(trip.distance_km)}
                    </span>
                    <span className="flex items-center gap-1">
                      <Clock className="w-3.5 h-3.5" />
                      {formatDuration(trip.duration_seconds)}
                    </span>
                    {trip.max_speed_kmh && (
                      <span className="flex items-center gap-1">
                        <Gauge className="w-3.5 h-3.5" />
                        {trip.max_speed_kmh} km/h
                      </span>
                    )}
                  </div>

                  {/* Events preview */}
                  {trip.event_count > 0 && (
                    <div className="flex gap-1.5 mt-2">
                      {Array.from({ length: Math.min(trip.event_count, 5) }).map((_, i) => (
                        <span
                          key={i}
                          className="w-1.5 h-1.5 rounded-full bg-amber-500"
                        />
                      ))}
                      {trip.event_count > 5 && (
                        <span className="text-xs text-tesla-gray-500">+{trip.event_count - 5}</span>
                      )}
                    </div>
                  )}
                </div>

                <ChevronRight className="w-5 h-5 text-tesla-gray-600 shrink-0" />
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

function RouteIcon() {
  return (
    <svg className="w-3.5 h-3.5" viewBox="0 0 16 16" fill="none">
      <path d="M2 8h12M2 8l3-3M2 8l3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
