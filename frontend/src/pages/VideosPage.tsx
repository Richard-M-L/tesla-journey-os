import { useState, useEffect, useCallback, useRef } from "react";
import { Film, Play, Trash2, RefreshCw, MapPin, MapPinOff, X, Gauge, Cog, AlertTriangle } from "lucide-react";

interface Video {
  path: string; filename: string; folder: string; source: string;
  size_mb: number; modified: string; has_sidecar: boolean;
}

interface TelemetryFrame {
  frame_index: number; timestamp_ms: number; speed_kmh: number;
  gear: string; is_autopilot_on: boolean; autopilot_state: string;
  brake_applied: boolean; blinker_left: boolean; blinker_right: boolean;
  steering_angle: number | null; has_gps: boolean; latitude: number | null;
}

export function VideosPage() {
  const [videos, setVideos] = useState<Video[]>([]);
  const [loading, setLoading] = useState(true);
  const [playing, setPlaying] = useState<Video | null>(null);
  const [telemetry, setTelemetry] = useState<TelemetryFrame[]>([]);
  const [currentFrame, setCurrentFrame] = useState<TelemetryFrame | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);

  const fetchVideos = useCallback(async () => {
    try {
      const r = await fetch("/api/videos?limit=100");
      const d = await r.json();
      setVideos(d.videos || []);
    } catch (e) { console.error(e); } finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchVideos(); }, [fetchVideos]);

  const handlePlay = async (v: Video) => {
    setPlaying(v);
    // Fetch telemetry for HUD overlay
    try {
      const r = await fetch(`/api/videos/telemetry?path=${encodeURIComponent(v.path)}&sample_rate=10`);
      const d = await r.json();
      setTelemetry(d.frames || []);
    } catch (e) { setTelemetry([]); }
    setTimeout(() => videoRef.current?.play(), 100);
  };

  const handleTimeUpdate = () => {
    if (!videoRef.current || telemetry.length === 0) return;
    const currentMs = videoRef.current.currentTime * 1000;
    // Find closest telemetry frame
    let closest = telemetry[0];
    for (const f of telemetry) {
      if (Math.abs(f.timestamp_ms - currentMs) < Math.abs(closest.timestamp_ms - currentMs)) {
        closest = f;
      }
    }
    setCurrentFrame(closest);
  };

  const handleDelete = async (v: Video) => {
    if (!confirm(`Delete ${v.filename}?`)) return;
    await fetch(`/api/videos?path=${encodeURIComponent(v.path)}`, { method: "DELETE" });
    await fetchVideos();
  };

  return (
    <div className="max-w-6xl space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold tracking-tight">视频</h1>
        <button onClick={fetchVideos} className="text-tesla-gray-500 hover:text-white">
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>

      {/* Video Player */}
      {playing && (
        <div className="relative rounded-xl overflow-hidden bg-black border border-tesla-gray-700">
          {/* Close button */}
          <button onClick={() => { setPlaying(null); setTelemetry([]); setCurrentFrame(null); }}
            className="absolute top-3 right-3 z-20 p-1.5 rounded-lg bg-black/60 text-white hover:bg-black/80">
            <X className="w-5 h-5" />
          </button>

          {/* HUD Overlay */}
          {currentFrame && (
            <div className="absolute bottom-0 left-0 right-0 z-10 p-4 bg-gradient-to-t from-black/80 to-transparent">
              <div className="flex items-center gap-4 text-white">
                {/* Speed */}
                <div className="text-center">
                  <div className="text-3xl font-bold tabular-nums">{currentFrame.speed_kmh}</div>
                  <div className="text-[10px] text-white/60 uppercase">km/h</div>
                </div>

                {/* Gear */}
                <div className={`px-2 py-1 rounded text-xs font-bold uppercase ${
                  currentFrame.gear === "DRIVE" ? "bg-blue-500/30 text-blue-300" :
                  currentFrame.gear === "REVERSE" ? "bg-red-500/30 text-red-300" :
                  currentFrame.gear === "PARK" ? "bg-gray-500/30 text-gray-300" :
                  "bg-white/10 text-white/60"
                }`}>
                  {currentFrame.gear || "?"}
                </div>

                {/* AP State */}
                {currentFrame.is_autopilot_on && (
                  <div className="px-2 py-1 rounded text-xs font-bold bg-blue-500/50 text-blue-200">
                    AP
                  </div>
                )}

                {/* Brake indicator */}
                {currentFrame.brake_applied && (
                  <div className="px-2 py-1 rounded text-xs font-bold bg-red-500/50 text-red-200">
                    BRAKE
                  </div>
                )}

                {/* Blinkers */}
                <div className="flex gap-1">
                  <span className={`text-lg ${currentFrame.blinker_left ? "text-green-400 animate-pulse" : "text-white/20"}`}>&#9664;</span>
                  <span className={`text-lg ${currentFrame.blinker_right ? "text-green-400 animate-pulse" : "text-white/20"}`}>&#9654;</span>
                </div>

                {/* Steering visual */}
                {currentFrame.steering_angle !== null && (
                  <div className="flex items-center gap-1 text-xs text-white/50">
                    <Cog className="w-3 h-3" />
                    <span
                      className="inline-block transition-transform"
                      style={{ transform: `rotate(${currentFrame.steering_angle}deg)` }}
                    >&#9776;</span>
                    <span>{currentFrame.steering_angle.toFixed(0)}°</span>
                  </div>
                )}

                {/* GPS status */}
                <div className="flex items-center gap-1 text-xs">
                  {currentFrame.has_gps ? (
                    <span className="text-green-400 flex items-center gap-0.5"><MapPin className="w-3 h-3" /> GPS</span>
                  ) : (
                    <span className="text-tesla-gray-500 flex items-center gap-0.5"><MapPinOff className="w-3 h-3" /></span>
                  )}
                </div>

                {/* Timestamp */}
                <div className="text-xs text-white/40 ml-auto tabular-nums">
                  {(currentFrame.timestamp_ms / 1000).toFixed(1)}s
                </div>
              </div>

              {/* Speed bar */}
              <div className="mt-2 h-1 rounded-full bg-white/10 overflow-hidden">
                <div
                  className="h-full rounded-full transition-all duration-100"
                  style={{
                    width: `${Math.min(100, (currentFrame.speed_kmh / 200) * 100)}%`,
                    backgroundColor: currentFrame.speed_kmh > 120 ? "#E82127" :
                                     currentFrame.speed_kmh > 80 ? "#F59E0B" : "#3E6AE1",
                  }}
                />
              </div>
            </div>
          )}

          <video
            ref={videoRef}
            src={`/api/videos/stream?path=${encodeURIComponent(playing.path)}`}
            onTimeUpdate={handleTimeUpdate}
            controls
            className="w-full"
            style={{ maxHeight: "70vh" }}
          />
        </div>
      )}

      {/* Video List */}
      {loading ? (
        <div className="animate-pulse text-tesla-gray-400">加载中...</div>
      ) : videos.length === 0 ? (
        <div className="text-center py-16 text-tesla-gray-500">
          <Film className="w-12 h-12 mx-auto mb-3 opacity-30" />
          <p className="text-lg">暂无视频</p>
          <p className="text-sm mt-1">TeslaCam 视频导入后将出现在这里</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {videos.map((v) => (
            <div key={v.path} className="p-4 rounded-xl bg-tesla-gray-800/50 border border-tesla-gray-800 hover:border-tesla-gray-700 transition-colors">
              <div className="flex items-start justify-between mb-2">
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium truncate" title={v.filename}>{v.filename}</p>
                  <p className="text-xs text-tesla-gray-500 mt-0.5">
                    {v.size_mb.toFixed(0)} MB · {v.source}
                    {v.has_sidecar && <span className="text-green-400 ml-1">· SEI</span>}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2 mt-3">
                <button onClick={() => handlePlay(v)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-tesla-blue/20 text-tesla-blue hover:bg-tesla-blue/30 text-xs font-medium transition-colors">
                  <Play className="w-3.5 h-3.5" /> 播放
                </button>
                <button onClick={() => handleDelete(v)}
                  className="p-1.5 rounded-lg text-tesla-gray-600 hover:text-red-400 transition-colors ml-auto">
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
