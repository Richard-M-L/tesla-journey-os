import { useState, useEffect, useCallback } from "react";
import { Music, Upload, Trash2, Plus, RefreshCw } from "lucide-react";

interface Chime {
  filename: string;
  size_bytes: number;
  modified: string;
  duration_s: number;
  sample_rate: number;
  valid: boolean;
}

interface Group {
  name: string;
  files: string[];
  file_count: number;
}

interface Schedule {
  schedule_type: string;
  chime_group: string;
  day_of_week: number;
  month: number;
  day: number;
  start_date: string;
  end_date: string;
}

export function LockChimesPage() {
  const [chimes, setChimes] = useState<Chime[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const res = await fetch("/api/media/chimes");
      const data = await res.json();
      setChimes(data.chimes || []);
      setGroups(data.groups || []);
      setSchedules(data.schedules || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch("/api/media/chimes/upload", { method: "POST", body: form });
      const result = await res.json();
      if (result.success) await fetchData();
      else alert(result.error || "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const handleDelete = async (filename: string) => {
    if (!confirm(`Delete ${filename}?`)) return;
    await fetch(`/api/media/chimes/${filename}`, { method: "DELETE" });
    await fetchData();
  };

  return (
    <div className="max-w-4xl space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold tracking-tight">锁车音效</h1>
        <label className={`inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium cursor-pointer transition-colors ${uploading ? "bg-tesla-gray-700" : "bg-tesla-blue hover:bg-tesla-blue/80"}`}>
          <Upload className="w-4 h-4" />
          {uploading ? "上传中..." : "上传 WAV"}
          <input type="file" accept=".wav" onChange={handleUpload} className="hidden" disabled={uploading} />
        </label>
      </div>

      {/* Chime files */}
      <div className="rounded-xl bg-tesla-gray-800/50 border border-tesla-gray-800 overflow-hidden">
        <div className="px-5 py-3 border-b border-tesla-gray-800 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-tesla-gray-300 flex items-center gap-2">
            <Music className="w-4 h-4" />
            音效文件 ({chimes.length})
          </h2>
          <button onClick={fetchData} className="text-tesla-gray-500 hover:text-white">
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
        {loading ? (
          <div className="p-8 text-center text-tesla-gray-400 animate-pulse">加载中...</div>
        ) : chimes.length === 0 ? (
          <div className="p-8 text-center text-tesla-gray-500">
            <Music className="w-10 h-10 mx-auto mb-2 opacity-30" />
            <p>暂无锁车音效</p>
            <p className="text-sm mt-1">上传 WAV 文件开始</p>
          </div>
        ) : (
          <div className="divide-y divide-tesla-gray-800/50">
            {chimes.map((c) => (
              <div key={c.filename} className="flex items-center justify-between px-5 py-3">
                <div>
                  <span className="text-sm font-medium">{c.filename}</span>
                  <span className="text-xs text-tesla-gray-500 ml-3">
                    {c.duration_s.toFixed(1)}s · {Math.round(c.size_bytes / 1024)}kB
                    {c.sample_rate > 0 && ` · ${(c.sample_rate / 1000).toFixed(1)}kHz`}
                  </span>
                  {!c.valid && (
                    <span className="text-xs text-amber-500 ml-2">⚠ Invalid format</span>
                  )}
                </div>
                <button
                  onClick={() => handleDelete(c.filename)}
                  className="text-tesla-gray-600 hover:text-red-400 transition-colors"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Groups */}
      <div className="rounded-xl bg-tesla-gray-800/50 border border-tesla-gray-800 p-5">
        <h2 className="text-sm font-semibold text-tesla-gray-300 mb-3">音效组</h2>
        {groups.length === 0 ? (
          <p className="text-sm text-tesla-gray-500">暂无分组。创建分组后可随机轮换音效。</p>
        ) : (
          <div className="space-y-2">
            {groups.map((g) => (
              <div key={g.name} className="flex items-center justify-between px-3 py-2 rounded-lg bg-tesla-gray-800/50">
                <div>
                  <span className="text-sm font-medium">{g.name}</span>
                  <span className="text-xs text-tesla-gray-500 ml-2">{g.file_count} 文件</span>
                </div>
                <div className="text-xs text-tesla-gray-500">
                  {g.files.slice(0, 3).join(", ")}
                  {g.files.length > 3 && ` +${g.files.length - 3}`}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
