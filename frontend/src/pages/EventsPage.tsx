import { useState } from "react";
import { Link } from "react-router-dom";
import { useApi } from "@/hooks/useApi";
import { api } from "@/lib/api";
import { formatDate, formatTime, eventTypeLabel, severityColor } from "@/lib/utils";
import type { DrivingEvent } from "@/types";
import { AlertTriangle, Filter } from "lucide-react";

const EVENT_TYPES = [
  "emergency_brake",
  "harsh_brake",
  "hard_acceleration",
  "sharp_turn",
  "speeding",
  "autopilot_disengage",
  "battery_low",
];

const SEVERITIES = ["critical", "warning", "info"];

export function EventsPage() {
  const [typeFilter, setTypeFilter] = useState<string | undefined>();
  const [severityFilter, setSeverityFilter] = useState<string | undefined>();

  const { data, loading } = useApi<{ events: DrivingEvent[] }>(
    () => api.listEvents({
      event_type: typeFilter,
      severity: severityFilter,
      days: 30,
      limit: 200,
    }),
    [typeFilter, severityFilter]
  );

  const events = data?.events ?? [];

  return (
    <div className="max-w-4xl space-y-6">
      <h1 className="text-2xl font-bold tracking-tight">事件</h1>

      {/* Filters */}
      <div className="flex items-center gap-3 flex-wrap">
        <Filter className="w-4 h-4 text-tesla-gray-500" />
        <select
          value={typeFilter ?? ""}
          onChange={(e) => setTypeFilter(e.target.value || undefined)}
          className="bg-tesla-gray-800 border border-tesla-gray-700 rounded-lg px-3 py-1.5 text-sm text-tesla-gray-300"
        >
          <option value="">全部类型</option>
          {EVENT_TYPES.map((t) => (
            <option key={t} value={t}>{eventTypeLabel(t)}</option>
          ))}
        </select>
        <select
          value={severityFilter ?? ""}
          onChange={(e) => setSeverityFilter(e.target.value || undefined)}
          className="bg-tesla-gray-800 border border-tesla-gray-700 rounded-lg px-3 py-1.5 text-sm text-tesla-gray-300"
        >
          <option value="">全部级别</option>
          {SEVERITIES.map((s) => (
            <option key={s} value={s}>
              {s === "critical" ? "严重" : s === "warning" ? "警告" : "信息"}
            </option>
          ))}
        </select>
        {(typeFilter || severityFilter) && (
          <button
            onClick={() => { setTypeFilter(undefined); setSeverityFilter(undefined); }}
            className="text-xs text-tesla-blue hover:underline"
          >
            清除筛选
          </button>
        )}
      </div>

      {/* Event List */}
      {loading ? (
        <div className="animate-pulse text-tesla-gray-400">加载中...</div>
      ) : events.length === 0 ? (
        <div className="text-center py-16 text-tesla-gray-500">
          <AlertTriangle className="w-12 h-12 mx-auto mb-3 opacity-30" />
          <p className="text-lg">无事件记录</p>
          <p className="text-sm mt-1">驾驶行为良好，或尚未导入遥测数据</p>
        </div>
      ) : (
        <div className="space-y-2">
          {events.map((event) => (
            <div
              key={event.id}
              className={`flex items-center justify-between px-4 py-3 rounded-xl border ${severityColor(event.severity)}`}
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium">
                    {eventTypeLabel(event.event_type)}
                  </span>
                  <span className="text-xs px-1.5 py-0.5 rounded bg-black/20">
                    {event.severity === "critical" ? "严重" : event.severity === "warning" ? "警告" : "信息"}
                  </span>
                </div>
                <p className="text-xs opacity-70 mt-0.5">
                  {event.description || formatDate(event.timestamp)}
                </p>
              </div>
              <div className="text-right shrink-0 ml-4">
                <div className="text-xs opacity-70">{formatTime(event.timestamp)}</div>
                {event.trip_id && (
                  <Link
                    to={`/trips/${event.trip_id}`}
                    className="text-xs text-tesla-blue hover:underline mt-0.5 inline-block"
                  >
                    查看行程
                  </Link>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
