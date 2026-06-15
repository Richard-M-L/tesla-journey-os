import { useState, useEffect, useCallback } from "react";
import { HardDrive, Film, Clock, AlertCircle, FolderOpen, BarChart3 } from "lucide-react";
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from "recharts";

interface DiskUsage { total_gb: number; used_gb: number; free_gb: number; used_pct: number; }
interface VideoStats { total_videos: number; total_size_gb: number; folders: Record<string, { video_count: number; total_size_gb: number }>; }
interface RecEstimate { free_gb: number; estimated_hours: number; estimated_minutes: number; gb_per_hour: number; }
interface Health { severity: string; disk: DiskUsage; video_stats: VideoStats; recording_estimate: RecEstimate; alerts: { severity: string; message: string }[]; }
interface FolderBreakdown { name: string; video_count: number; size_gb: number; pct: number; }

const COLORS = ["#3E6AE1", "#10B981", "#F59E0B", "#E82127", "#8B5CF6"];

export function StoragePage() {
  const [health, setHealth] = useState<Health | null>(null);
  const [folders, setFolders] = useState<FolderBreakdown[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    try {
      const [hRes, fRes] = await Promise.all([
        fetch("/api/storage/health"),
        fetch("/api/storage/folders"),
      ]);
      setHealth(await hRes.json());
      const fd = await fRes.json();
      setFolders(fd.folders || []);
    } catch (e) { console.error(e); } finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  if (loading) return <div className="animate-pulse text-tesla-gray-400">加载中...</div>;
  if (!health) return <div className="text-red-400">加载失败</div>;

  const { disk, video_stats, recording_estimate, alerts } = health;
  const usedColor = disk.used_pct > 90 ? "#E82127" : disk.used_pct > 75 ? "#F59E0B" : "#3E6AE1";
  const pieData = [{ name: "已用", value: disk.used_gb }, { name: "可用", value: disk.free_gb }];

  return (
    <div className="max-w-6xl space-y-6">
      <h1 className="text-2xl font-bold tracking-tight">存储分析</h1>

      {/* Alerts */}
      {alerts.filter(a => a.severity !== "info").map((a, i) => (
        <div key={i} className={`flex items-center gap-2 px-4 py-3 rounded-lg text-sm ${
          a.severity === "error" ? "bg-red-500/10 border border-red-500/20 text-red-400" :
          "bg-amber-500/10 border border-amber-500/20 text-amber-400"
        }`}>
          <AlertCircle className="w-4 h-4 shrink-0" />
          {a.message}
        </div>
      ))}

      {/* Top cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <StatCard icon={HardDrive} label="磁盘总容量" value={`${disk.total_gb.toFixed(0)} GB`} sub={`${disk.free_gb.toFixed(0)} GB 可用`} />
        <StatCard icon={Film} label="总视频数" value={`${video_stats.total_videos}`} sub={`${video_stats.total_size_gb.toFixed(1)} GB`}
          highlight={video_stats.total_videos > 0} />
        <StatCard icon={Clock} label="可录制时长" value={`${recording_estimate.estimated_hours.toFixed(0)} 小时`}
          sub={`${recording_estimate.gb_per_hour} GB/小时`} />
        <StatCard icon={AlertCircle} label="磁盘使用率" value={`${disk.used_pct.toFixed(0)}%`}
          sub={disk.used_pct > 80 ? "需要注意" : "正常"}
          highlight={disk.used_pct > 80} highlightBad={disk.used_pct > 90} />
      </div>

      {/* Disk usage chart */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="p-5 rounded-xl bg-tesla-gray-800/50 border border-tesla-gray-800">
          <h2 className="text-sm font-semibold text-tesla-gray-300 mb-4 flex items-center gap-2">
            <BarChart3 className="w-4 h-4" /> 磁盘使用
          </h2>
          <div className="flex items-center gap-4">
            <ResponsiveContainer width={140} height={140}>
              <PieChart>
                <Pie data={pieData} cx="50%" cy="50%" innerRadius={40} outerRadius={60} dataKey="value"
                  stroke="none">
                  <Cell fill={usedColor} />
                  <Cell fill="#333" />
                </Pie>
                <Tooltip contentStyle={{ background: "#222", border: "1px solid #444", borderRadius: "8px", fontSize: "12px" }} />
              </PieChart>
            </ResponsiveContainer>
            <div className="space-y-2 text-sm">
              <div className="flex items-center gap-2">
                <span className="w-3 h-3 rounded-sm" style={{ backgroundColor: usedColor }} />
                <span className="text-tesla-gray-400">已用</span>
                <span className="font-medium">{disk.used_gb.toFixed(1)} GB</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-3 h-3 rounded-sm" style={{ backgroundColor: "#333" }} />
                <span className="text-tesla-gray-400">可用</span>
                <span className="font-medium">{disk.free_gb.toFixed(1)} GB</span>
              </div>
            </div>
          </div>
        </div>

        {/* Folder breakdown */}
        <div className="p-5 rounded-xl bg-tesla-gray-800/50 border border-tesla-gray-800">
          <h2 className="text-sm font-semibold text-tesla-gray-300 mb-4 flex items-center gap-2">
            <FolderOpen className="w-4 h-4" /> 按目录
          </h2>
          <div className="space-y-3">
            {folders.map((f, i) => (
              <div key={f.name}>
                <div className="flex items-center justify-between text-sm mb-1">
                  <span className="text-tesla-gray-300">{f.name}</span>
                  <span className="text-tesla-gray-500">{f.video_count} 个 · {f.size_gb.toFixed(1)} GB</span>
                </div>
                <div className="h-2 rounded-full bg-tesla-gray-700 overflow-hidden">
                  <div className="h-full rounded-full transition-all"
                    style={{ width: `${Math.max(f.pct, 2)}%`, backgroundColor: COLORS[i % COLORS.length] }}
                  />
                </div>
              </div>
            ))}
            {folders.length === 0 && (
              <p className="text-sm text-tesla-gray-500">无视频数据</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function StatCard({ icon: Icon, label, value, sub, highlight, highlightBad }: {
  icon: React.ComponentType<{ className?: string }>; label: string; value: string; sub: string;
  highlight?: boolean; highlightBad?: boolean;
}) {
  return (
    <div className="p-4 rounded-xl bg-tesla-gray-800/50 border border-tesla-gray-800">
      <div className="flex items-center gap-2 mb-2">
        <Icon className={`w-4 h-4 ${highlightBad ? "text-red-400" : highlight ? "text-tesla-blue" : "text-tesla-gray-500"}`} />
        <span className="text-xs text-tesla-gray-500 uppercase tracking-wider">{label}</span>
      </div>
      <div className="text-xl font-bold">{value}</div>
      <div className="text-xs text-tesla-gray-500 mt-0.5">{sub}</div>
    </div>
  );
}
