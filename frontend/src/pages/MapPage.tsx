import { useState, useEffect } from "react";
import { useApi } from "@/hooks/useApi";
import { api } from "@/lib/api";
import type { TripSummary } from "@/types";
import { MapPin, MapPinOff, AlertCircle } from "lucide-react";

/**
 * Map page — Leaflet-based map view of all trips.
 *
 * This component gracefully degrades when:
 *  - GPS data is unavailable for some/all trips
 *  - The Leaflet library fails to load
 *  - The user has no network (map tiles may not load)
 *
 * Map is marked as "optional" in the architecture. All other features
 * continue to work without this page.
 */

export function MapPage() {
  const [mapReady, setMapReady] = useState(false);
  const [mapError, setMapError] = useState(false);
  const [MapComponent, setMapComponent] = useState<React.ComponentType<{ trips: TripSummary[] }> | null>(null);

  const { data, loading } = useApi<{ trips: TripSummary[] }>(
    () => api.listTrips({ days: 90, limit: 500 })
  );

  const trips = data?.trips ?? [];
  const tripsWithGps = trips.filter((t) => t.has_gps);
  const tripsWithoutGps = trips.filter((t) => !t.has_gps);

  // Attempt to load Leaflet dynamically — it may fail if not installed
  useEffect(() => {
    let cancelled = false;
    import("./MapComponent")
      .then((mod) => {
        if (!cancelled) {
          setMapComponent(() => mod.default);
          setMapReady(true);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setMapError(true);
        }
      });
    return () => { cancelled = true; };
  }, []);

  return (
    <div className="max-w-6xl space-y-6">
      <h1 className="text-2xl font-bold tracking-tight">地图</h1>

      {/* GPS Status */}
      {!loading && (
        <div className="flex items-center gap-4 text-sm">
          <span className="flex items-center gap-1.5 text-green-400">
            <MapPin className="w-4 h-4" />
            {tripsWithGps.length} 条行程有 GPS
          </span>
          {tripsWithoutGps.length > 0 && (
            <span className="flex items-center gap-1.5 text-amber-500">
              <MapPinOff className="w-4 h-4" />
              {tripsWithoutGps.length} 条行程无 GPS
            </span>
          )}
        </div>
      )}

      {/* Map Container */}
      <div className="rounded-xl border border-tesla-gray-800 overflow-hidden bg-tesla-gray-800/50" style={{ height: "70vh" }}>
        {loading ? (
          <div className="flex items-center justify-center h-full text-tesla-gray-400">
            加载中...
          </div>
        ) : mapError ? (
          <MapFallback message="地图组件加载失败" detail="Leaflet 可能未安装。运行 npm install leaflet react-leaflet 后刷新。" />
        ) : !mapReady ? (
          <div className="flex items-center justify-center h-full text-tesla-gray-400">
            <div className="animate-pulse">加载地图引擎...</div>
          </div>
        ) : tripsWithGps.length === 0 ? (
          <MapFallback
            message="无 GPS 数据可显示"
            detail={trips.length > 0
              ? `有 ${trips.length} 条行程，但全部无 GPS 坐标。行程和时间线仍可正常使用。`
              : "尚未导入带有 GPS 数据的行程。"}
          />
        ) : MapComponent ? (
          <MapComponent trips={tripsWithGps} />
        ) : null}
      </div>

      {/* Graceful degradation notice */}
      {tripsWithoutGps.length > 0 && (
        <div className="flex items-center gap-2 px-4 py-3 rounded-lg bg-tesla-gray-800 border border-tesla-gray-700 text-sm text-tesla-gray-400">
          <AlertCircle className="w-4 h-4 text-amber-500 shrink-0" />
          <span>
            {tripsWithoutGps.length} 条行程无 GPS 数据，不显示在地图上。
            所有其他功能仍可正常使用。
          </span>
        </div>
      )}
    </div>
  );
}

function MapFallback({ message, detail }: { message: string; detail: string }) {
  return (
    <div className="flex flex-col items-center justify-center h-full text-center px-8">
      <MapPinOff className="w-12 h-12 text-tesla-gray-600 mb-3" />
      <p className="text-lg text-tesla-gray-300">{message}</p>
      <p className="text-sm text-tesla-gray-500 mt-1 max-w-md">{detail}</p>
    </div>
  );
}
