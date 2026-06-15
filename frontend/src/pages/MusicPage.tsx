import { useState, useEffect, useCallback } from "react";
import { Disc, Upload, Trash2, RefreshCw } from "lucide-react";

interface MusicFile {
  filename: string;
  size_bytes: number;
  ext: string;
}

export function MusicPage() {
  const [files, setFiles] = useState<MusicFile[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const res = await fetch("/api/media/music");
      const data = await res.json();
      setFiles(data.files || []);
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
      const res = await fetch("/api/media/music/upload", { method: "POST", body: form });
      const result = await res.json();
      if (!result.success) alert(result.error || "Upload failed");
      await fetchData();
    } finally {
      setUploading(false);
    }
  };

  const handleDelete = async (filename: string) => {
    if (!confirm(`Delete ${filename}?`)) return;
    await fetch(`/api/media/music/${filename}`, { method: "DELETE" });
    await fetchData();
  };

  const totalMB = files.reduce((s, f) => s + f.size_bytes, 0) / (1024 * 1024);

  return (
    <div className="max-w-4xl space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">音乐</h1>
          <p className="text-sm text-tesla-gray-500 mt-1">
            {files.length} 首 · {totalMB.toFixed(0)} MB
          </p>
        </div>
        <label className={`inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium cursor-pointer transition-colors ${uploading ? "bg-tesla-gray-700" : "bg-tesla-blue hover:bg-tesla-blue/80"}`}>
          <Upload className="w-4 h-4" />
          {uploading ? "上传中..." : "上传"}
          <input type="file" accept=".mp3,.flac,.wav,.aac,.m4a" onChange={handleUpload} className="hidden" disabled={uploading} />
        </label>
      </div>

      {loading ? (
        <div className="p-8 text-center text-tesla-gray-400 animate-pulse">加载中...</div>
      ) : files.length === 0 ? (
        <div className="text-center py-16 text-tesla-gray-500">
          <Disc className="w-12 h-12 mx-auto mb-3 opacity-30" />
          <p className="text-lg">暂无音乐文件</p>
          <p className="text-sm mt-1">上传 MP3/FLAC/WAV/AAC/M4A 文件</p>
        </div>
      ) : (
        <div className="space-y-2">
          {files.map((f) => (
            <div key={f.filename} className="flex items-center justify-between px-4 py-3 rounded-xl bg-tesla-gray-800/50 border border-tesla-gray-800">
              <div className="flex items-center gap-3">
                <Disc className="w-4 h-4 text-tesla-blue" />
                <span className="text-sm font-medium">{f.filename}</span>
                <span className="text-xs text-tesla-gray-500">
                  {(f.size_bytes / (1024 * 1024)).toFixed(1)} MB
                </span>
              </div>
              <button
                onClick={() => handleDelete(f.filename)}
                className="text-tesla-gray-600 hover:text-red-400 transition-colors"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
