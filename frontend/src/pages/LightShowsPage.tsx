import { useState, useEffect, useCallback } from "react";
import { Zap, Upload, Trash2, Download, RefreshCw, CheckCircle, AlertCircle } from "lucide-react";

interface ShowFile {
  filename: string;
  size_bytes: number;
  ext: string;
}

interface Show {
  name: string;
  files: ShowFile[];
  file_count: number;
  has_fseq: boolean;
  has_audio: boolean;
  valid: boolean;
  total_size_bytes: number;
}

export function LightShowsPage() {
  const [shows, setShows] = useState<Show[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    try {
      const res = await fetch("/api/media/lightshows");
      const data = await res.json();
      setShows(data.shows || []);
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
    const form = new FormData();
    form.append("file", file);
    try {
      const res = await fetch("/api/media/lightshows/upload", { method: "POST", body: form });
      const result = await res.json();
      if (result.success) {
        await fetchData();
        if (result.errors?.length) alert("部分文件出错: " + result.errors.join(", "));
      } else {
        alert(result.error || "Upload failed");
      }
    } catch (e) {
      alert("Upload error");
    }
  };

  const handleDelete = async (name: string) => {
    if (!confirm(`Delete show "${name}"?`)) return;
    await fetch(`/api/media/lightshows/${name}`, { method: "DELETE" });
    await fetchData();
  };

  const handleDownload = (name: string) => {
    window.open(`/api/media/lightshows/download/${name}`, "_blank");
  };

  return (
    <div className="max-w-4xl space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold tracking-tight">灯光秀</h1>
        <label className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-tesla-blue hover:bg-tesla-blue/80 cursor-pointer transition-colors">
          <Upload className="w-4 h-4" />
          上传
          <input type="file" accept=".zip,.fseq,.mp3,.wav" onChange={handleUpload} className="hidden" />
        </label>
      </div>

      {loading ? (
        <div className="p-8 text-center text-tesla-gray-400 animate-pulse">加载中...</div>
      ) : shows.length === 0 ? (
        <div className="text-center py-16 text-tesla-gray-500">
          <Zap className="w-12 h-12 mx-auto mb-3 opacity-30" />
          <p className="text-lg">暂无灯光秀</p>
          <p className="text-sm mt-1">上传 .fseq + .mp3/.wav 文件，或导入 ZIP 压缩包</p>
        </div>
      ) : (
        <div className="space-y-3">
          {shows.map((show) => (
            <div key={show.name} className="p-4 rounded-xl bg-tesla-gray-800/50 border border-tesla-gray-800">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  {show.valid ? (
                    <CheckCircle className="w-5 h-5 text-green-400" />
                  ) : (
                    <AlertCircle className="w-5 h-5 text-amber-500" />
                  )}
                  <div>
                    <h3 className="text-sm font-semibold">{show.name}</h3>
                    <div className="flex items-center gap-2 text-xs text-tesla-gray-500 mt-0.5">
                      <span>{show.file_count} 文件</span>
                      <span>·</span>
                      <span>{(show.total_size_bytes / 1024).toFixed(0)} kB</span>
                      {show.has_fseq && <span className="text-green-400">· .fseq</span>}
                      {show.has_audio && <span className="text-blue-400">· audio</span>}
                      {!show.valid && <span className="text-amber-500">· 缺少 .fseq</span>}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {show.files.map((f) => (
                    <span key={f.filename} className="text-xs px-2 py-1 rounded bg-tesla-gray-700 text-tesla-gray-400">
                      {f.ext}
                    </span>
                  ))}
                  <button
                    onClick={() => handleDelete(show.name)}
                    className="ml-2 text-tesla-gray-600 hover:text-red-400 transition-colors"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
