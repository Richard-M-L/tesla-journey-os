/** Utility functions for formatting and display. */

export function formatDistance(km: number): string {
  if (km < 1) return `${Math.round(km * 1000)} m`;
  return `${km.toFixed(1)} km`;
}

export function formatDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

export function formatSpeed(mps: number | null): string {
  if (mps === null || mps === undefined) return "--";
  const kmh = mps * 3.6;
  return `${Math.round(kmh)} km/h`;
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("zh-CN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatDateShort(iso: string): string {
  return new Date(iso).toLocaleDateString("zh-CN", {
    month: "short",
    day: "numeric",
  });
}

export function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function severityColor(severity: string): string {
  switch (severity) {
    case "critical":
      return "text-red-500 bg-red-500/10 border-red-500/30";
    case "warning":
      return "text-amber-500 bg-amber-500/10 border-amber-500/30";
    default:
      return "text-blue-400 bg-blue-400/10 border-blue-400/30";
  }
}

export function eventTypeLabel(type: string): string {
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

export function gpsUnavailable(): string {
  return "GPS 不可用";
}
