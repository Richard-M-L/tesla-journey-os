import { useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useApi } from "@/hooks/useApi";
import { api } from "@/lib/api";
import { formatDistance, formatDuration, formatTime, formatSpeed, formatDate, eventTypeLabel, severityColor } from "@/lib/utils";
import type { TripDetail, TelemetryFrame } from "@/types";
import {
  ArrowLeft,
  MapPin,
  MapPinOff,
  Clock,
  Gauge,
  Zap,
  AlertTriangle,
  Activity,
} from "lucide-react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

export function TripDetailPage() {
  const { id } = useParams<{ id: string }>();
  const tripId = Number(id);

  const { data: trip, loading, error } = useApi<TripDetail>(
    () => api.getTrip(tripId),
    [tripId]
  );

  const { data: telemetryData } = useApi<{ telemetry: TelemetryFrame[] }>(
    () => api.getTripTelemetry(tripId, 30),
    [tripId]
  );

  if (loading) return <div className="animate-pulse text-tesla-gray-400">加载中...</div>;
  if (error || !trip) return <div className="text-red-400">加载失败: {error}</div>;

  const frames = telemetryData?.telemetry ?? [];
  const chartData = frames.map((f) => ({
    t: new Date(f.timestamp).getTime(),
    speed: f.speed_kmh,
    power: f.power_kw,
  }));

  return (
    <div className="max-w-5xl space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Link to="/timeline" className="text-tesla-gray-400 hover:text-white">
          <ArrowLeft className="w-5 h-5" />
        </Link>
        <div className="flex-1">
          <h1 className="text-xl font-bold">行程详情</h1>
          <p className="text-sm text-tesla-gray-400">
            {formatDate(trip.start_time)}
            {trip.has_gps ? "" : " · GPS 不可用"}
          </p>
        </div>
        {!trip.has_gps && (
          <span className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs bg-amber-500/10 text-amber-500 border border-amber-500/20">
            <MapPinOff className="w-3.5 h-3.5" />
            无 GPS
          </span>
        )}
      </div>

      {/* Stat Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <MiniStat icon={RouteIcon2} label="距离" value={formatDistance(trip.distance_km)} />
        <MiniStat icon={Clock} label="时长" value={formatDuration(trip.duration_seconds)} />
        <MiniStat icon={Gauge} label="最高速度" value={trip.max_speed_kmh ? `${trip.max_speed_kmh} km/h` : "--"} />
        <MiniStat icon={Zap} label="能耗" value={trip.energy_consumed_kwh ? `${trip.energy_consumed_kwh.toFixed(1)} kWh` : "--"} />
      </div>

      {/* Speed Chart */}
      {chartData.length > 5 && (
        <div className="p-5 rounded-xl bg-tesla-gray-800/50 border border-tesla-gray-800">
          <h2 className="text-sm font-semibold text-tesla-gray-300 mb-4 flex items-center gap-2">
            <Activity className="w-4 h-4" />
            速度曲线
          </h2>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={chartData}>
              <XAxis
                dataKey="t"
                type="number"
                scale="time"
                domain={["dataMin", "dataMax"]}
                tickFormatter={(t) => formatTime(new Date(t).toISOString())}
                stroke="#444"
                fontSize={11}
              />
              <YAxis stroke="#444" fontSize={11} unit=" km/h" />
              <Tooltip
                labelFormatter={(t) => formatTime(new Date(t).toISOString())}
                formatter={(v: number) => [`${v.toFixed(1)} km/h`, "速度"]}
                contentStyle={{
                  background: "#222",
                  border: "1px solid #444",
                  borderRadius: "8px",
                  fontSize: "12px",
                }}
              />
              <Line
                type="monotone"
                dataKey="speed"
                stroke="#3E6AE1"
                dot={false}
                strokeWidth={1.5}
              />
            </LineChart>
          </ResponsiveContainer>

          {/* GPS unavailability notice for chart */}
          {!trip.has_gps && (
            <div className="mt-2 text-xs text-tesla-gray-500">
              速度曲线基于遥测数据（无需 GPS）
            </div>
          )}
        </div>
      )}

      {/* Events */}
      {trip.events.length > 0 && (
        <div className="p-5 rounded-xl bg-tesla-gray-800/50 border border-tesla-gray-800">
          <h2 className="text-sm font-semibold text-tesla-gray-300 mb-3 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4" />
            行程事件 ({trip.events.length})
          </h2>
          <div className="space-y-2">
            {trip.events.map((event) => (
              <div
                key={event.id}
                className={`flex items-center justify-between px-3 py-2 rounded-lg border ${severityColor(event.severity)}`}
              >
                <div>
                  <span className="text-sm font-medium">
                    {eventTypeLabel(event.event_type)}
                  </span>
                  <span className="text-xs opacity-70 ml-2">
                    {event.description}
                  </span>
                </div>
                <span className="text-xs opacity-70">
                  {formatTime(event.timestamp)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* No GPS notice */}
      {!trip.has_gps && trip.events.length === 0 && chartData.length <= 5 && (
        <div className="text-center py-12 text-tesla-gray-500">
          <MapPinOff className="w-10 h-10 mx-auto mb-2 opacity-30" />
          <p>此行程无 GPS 数据且遥测数据有限</p>
          <p className="text-sm mt-1">可用的遥测指标已在上方显示</p>
        </div>
      )}
    </div>
  );
}

function MiniStat({ icon: Icon, label, value }: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string;
}) {
  return (
    <div className="p-4 rounded-xl bg-tesla-gray-800/50 border border-tesla-gray-800">
      <div className="flex items-center gap-2 mb-1">
        <Icon className="w-3.5 h-3.5 text-tesla-gray-500" />
        <span className="text-xs text-tesla-gray-500">{label}</span>
      </div>
      <div className="text-lg font-semibold">{value}</div>
    </div>
  );
}

function RouteIcon2({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 16 16" fill="none">
      <path d="M2 8h12M2 8l3-3M2 8l3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
