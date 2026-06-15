import { useApi } from "@/hooks/useApi";
import { api } from "@/lib/api";
import { formatDistance, formatDuration } from "@/lib/utils";
import type { DashboardStats } from "@/types";
import {
  Route,
  Gauge,
  Zap,
  AlertTriangle,
  TrendingUp,
  MapPinOff,
} from "lucide-react";

export function DashboardPage() {
  const { data, loading, error } = useApi<DashboardStats>(() => api.getDashboardStats());

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-pulse text-tesla-gray-400">加载中...</div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="flex items-center justify-center h-64 text-red-400">
        加载失败: {error}
      </div>
    );
  }

  const { overview, trip_summary, event_distribution, driving_score } = data;

  return (
    <div className="max-w-6xl space-y-6">
      <h1 className="text-2xl font-bold tracking-tight">仪表盘</h1>

      {/* Stat Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          icon={Route}
          label="总行程"
          value={`${overview.total_trips}`}
          sub={`${formatDistance(overview.total_distance_km)}`}
        />
        <StatCard
          icon={Gauge}
          label="驾驶评分"
          value={driving_score.score !== null ? `${driving_score.score}` : "--"}
          sub={driving_score.reason || `${overview.total_duration_hours.toFixed(1)} 小时`}
          highlight={driving_score.score !== null && driving_score.score >= 80}
        />
        <StatCard
          icon={AlertTriangle}
          label="总事件"
          value={`${overview.total_events}`}
          sub={event_distribution.total_events > 0
            ? `${Object.entries(event_distribution.by_type)
                .sort((a, b) => b[1] - a[1])[0]?.[0] || ""} 最多`
            : "无事件"}
        />
        <StatCard
          icon={Zap}
          label="能耗"
          value={trip_summary.total_energy_kwh > 0
            ? `${trip_summary.total_energy_kwh.toFixed(1)} kWh`
            : "--"}
          sub={trip_summary.avg_efficiency_wh_per_km > 0
            ? `${trip_summary.avg_efficiency_wh_per_km.toFixed(0)} Wh/km`
            : "无数据"}
        />
      </div>

      {/* GPS Status Banner */}
      {overview.trips_with_gps_pct < 50 && (
        <div className="flex items-center gap-2 px-4 py-3 rounded-lg bg-tesla-gray-800 border border-tesla-gray-700 text-sm text-tesla-gray-400">
          <MapPinOff className="w-4 h-4 text-amber-500 shrink-0" />
          <span>
            {overview.trips_without_gps_pct}% 的行程无 GPS 数据。
            所有功能正常运作，地图将降级显示。
          </span>
        </div>
      )}

      {/* Recent Trips Summary */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="p-5 rounded-xl bg-tesla-gray-800/50 border border-tesla-gray-800">
          <h2 className="text-sm font-semibold text-tesla-gray-300 mb-3 flex items-center gap-2">
            <TrendingUp className="w-4 h-4" />
            最近 30 天
          </h2>
          <div className="space-y-2 text-sm">
            <MetricRow label="行程次数" value={`${trip_summary.trip_count}`} />
            <MetricRow label="总里程" value={formatDistance(trip_summary.total_distance_km)} />
            <MetricRow label="总时长" value={formatDuration(trip_summary.total_duration_hours * 3600)} />
            <MetricRow label="平均每程" value={formatDistance(trip_summary.avg_distance_per_trip_km)} />
          </div>
        </div>

        <div className="p-5 rounded-xl bg-tesla-gray-800/50 border border-tesla-gray-800">
          <h2 className="text-sm font-semibold text-tesla-gray-300 mb-3 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4" />
            事件概览
          </h2>
          <div className="space-y-2 text-sm">
            {Object.entries(event_distribution.by_type).length > 0 ? (
              Object.entries(event_distribution.by_type)
                .sort((a, b) => b[1] - a[1])
                .slice(0, 5)
                .map(([type, count]) => (
                  <MetricRow key={type} label={eventLabel(type)} value={`${count}`} />
                ))
            ) : (
              <div className="text-tesla-gray-500">无事件记录</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function StatCard({
  icon: Icon,
  label,
  value,
  sub,
  highlight = false,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string;
  sub: string;
  highlight?: boolean;
}) {
  return (
    <div className="p-5 rounded-xl bg-tesla-gray-800/50 border border-tesla-gray-800">
      <div className="flex items-center gap-2 mb-3">
        <Icon className={`w-4 h-4 ${highlight ? "text-green-400" : "text-tesla-gray-400"}`} />
        <span className="text-xs text-tesla-gray-500 uppercase tracking-wider">{label}</span>
      </div>
      <div className="text-2xl font-bold">{value}</div>
      <div className="text-xs text-tesla-gray-500 mt-1">{sub}</div>
    </div>
  );
}

function MetricRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between">
      <span className="text-tesla-gray-400">{label}</span>
      <span className="font-medium">{value}</span>
    </div>
  );
}

function eventLabel(type: string): string {
  const labels: Record<string, string> = {
    emergency_brake: "紧急制动",
    harsh_brake: "急刹车",
    hard_acceleration: "急加速",
    sharp_turn: "急转弯",
    speeding: "超速",
    autopilot_disengage: "AP退出",
    battery_low: "低电量",
  };
  return labels[type] || type;
}
