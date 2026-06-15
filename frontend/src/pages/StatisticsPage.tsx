import { useState } from "react";
import { useApi } from "@/hooks/useApi";
import { api } from "@/lib/api";
import { eventTypeLabel } from "@/lib/utils";
import type { DailyTripData, BatteryTrend, DrivingScore, EventDistribution } from "@/types";
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import { TrendingUp, Battery, AlertTriangle } from "lucide-react";

const COLORS = ["#3E6AE1", "#E82127", "#F59E0B", "#10B981", "#8B5CF6", "#EC4899", "#06B6D4"];

export function StatisticsPage() {
  const [periodDays, setPeriodDays] = useState(30);

  const { data: dailyTrips } = useApi<{ daily_trips: DailyTripData[] }>(
    () => api.getDailyTrips(periodDays),
    [periodDays]
  );

  const { data: batteryTrend } = useApi<{ battery_trend: BatteryTrend[] }>(
    () => api.getBatteryTrend(periodDays),
    [periodDays]
  );

  const { data: score } = useApi<DrivingScore>(
    () => api.getDrivingScore(periodDays),
    [periodDays]
  );

  const { data: eventDist } = useApi<EventDistribution>(
    () => api.listEvents({ days: periodDays, limit: 0 }).then(() =>
      // We'll get event distribution from the dashboard stats instead
      ({ period_days: periodDays, total_events: 0, by_type: {}, by_severity: {} } as EventDistribution)
    ),
    [periodDays]
  );

  return (
    <div className="max-w-6xl space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold tracking-tight">统计</h1>
        <select
          value={periodDays}
          onChange={(e) => setPeriodDays(Number(e.target.value))}
          className="bg-tesla-gray-800 border border-tesla-gray-700 rounded-lg px-3 py-1.5 text-sm text-tesla-gray-300"
        >
          <option value={7}>最近 7 天</option>
          <option value={30}>最近 30 天</option>
          <option value={90}>最近 90 天</option>
          <option value={365}>最近一年</option>
        </select>
      </div>

      {/* Driving Score */}
      {score && (
        <div className="p-6 rounded-xl bg-tesla-gray-800/50 border border-tesla-gray-800">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-sm font-semibold text-tesla-gray-300 flex items-center gap-2">
                <TrendingUp className="w-4 h-4" />
                驾驶评分
              </h2>
              <p className="text-xs text-tesla-gray-500 mt-1">{periodDays} 天统计</p>
            </div>
            <div className="text-right">
              <div className={`text-4xl font-bold ${
                score.score === null ? "text-tesla-gray-500" :
                score.score >= 80 ? "text-green-400" :
                score.score >= 60 ? "text-amber-400" : "text-red-400"
              }`}>
                {score.score ?? "--"}
              </div>
              {score.reason && (
                <p className="text-xs text-tesla-gray-500 mt-1">{score.reason}</p>
              )}
              {score.events_per_100km !== undefined && (
                <p className="text-xs text-tesla-gray-500">
                  {score.total_harsh_events} 次激烈事件 · {score.events_per_100km}/100km
                </p>
              )}
            </div>
          </div>
          {/* Score bar */}
          {score.score !== null && (
            <div className="mt-4 h-2 rounded-full bg-tesla-gray-700 overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${
                  score.score >= 80 ? "bg-green-500" :
                  score.score >= 60 ? "bg-amber-500" : "bg-red-500"
                }`}
                style={{ width: `${score.score}%` }}
              />
            </div>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Daily Trip Count */}
        <div className="p-5 rounded-xl bg-tesla-gray-800/50 border border-tesla-gray-800">
          <h2 className="text-sm font-semibold text-tesla-gray-300 mb-4">每日行程</h2>
          {dailyTrips?.daily_trips && dailyTrips.daily_trips.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={dailyTrips.daily_trips}>
                <XAxis dataKey="date" stroke="#444" fontSize={11} />
                <YAxis stroke="#444" fontSize={11} allowDecimals={false} />
                <Tooltip
                  contentStyle={{ background: "#222", border: "1px solid #444", borderRadius: "8px", fontSize: "12px" }}
                />
                <Bar dataKey="trip_count" fill="#3E6AE1" radius={[4, 4, 0, 0]} name="行程数" />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="text-center py-8 text-tesla-gray-500 text-sm">无数据</div>
          )}
        </div>

        {/* Battery Trend */}
        <div className="p-5 rounded-xl bg-tesla-gray-800/50 border border-tesla-gray-800">
          <h2 className="text-sm font-semibold text-tesla-gray-300 mb-4 flex items-center gap-2">
            <Battery className="w-4 h-4" />
            电量趋势
          </h2>
          {batteryTrend?.battery_trend && batteryTrend.battery_trend.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={batteryTrend.battery_trend}>
                <XAxis dataKey="timestamp" stroke="#444" fontSize={11}
                  tickFormatter={(t) => new Date(t).toLocaleDateString("zh-CN", { month: "short", day: "numeric" })}
                />
                <YAxis stroke="#444" fontSize={11} domain={[0, 100]} unit="%" />
                <Tooltip
                  labelFormatter={(t) => new Date(t).toLocaleString("zh-CN")}
                  formatter={(v: number) => [`${v.toFixed(1)}%`, "电量"]}
                  contentStyle={{ background: "#222", border: "1px solid #444", borderRadius: "8px", fontSize: "12px" }}
                />
                <Line type="monotone" dataKey="battery_pct" stroke="#10B981" dot={false} strokeWidth={1.5} name="电量" />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="text-center py-8 text-tesla-gray-500 text-sm">无电池数据</div>
          )}
        </div>
      </div>
    </div>
  );
}
