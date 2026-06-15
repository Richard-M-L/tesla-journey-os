import { useState, useEffect, useCallback } from "react";
import { Image, Upload, Trash2, AlertCircle, CheckCircle } from "lucide-react";

interface Wrap { filename: string; size_kb: number; width: number; height: number; valid: boolean; modified: string; }

export function WrapsPage() {
  const [wraps, setWraps] = useState<Wrap[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);

  const fetchWraps = useCallback(async () => {
    try { const r = await fetch("/api/media/wraps"); const d = await r.json(); setWraps(d.wraps || []); }
    catch (e) { console.error(e); } finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchWraps(); }, [fetchWraps]);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]; if (!file) return;
    setUploading(true);
    try {
      const form = new FormData(); form.append("file", file);
      const r = await fetch("/api/media/wraps/upload", { method: "POST", body: form });
      const d = await r.json();
      if (d.success) fetchWraps(); else alert(d.error);
    } finally { setUploading(false); }
  };

  const handleDelete = async (f: string) => {
    if (!confirm(`Delete ${f}?`)) return;
    await fetch(`/api/media/wraps/${encodeURIComponent(f)}`, { method: "DELETE" });
    fetchWraps();
  };

  return (
    <div className="max-w-4xl space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">车衣</h1>
          <p className="text-xs text-tesla-gray-500 mt-1">PNG · 512-1024px · ≤1MB · 最多10个 · 文件名不超过30字符</p>
        </div>
        <label className={`inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium cursor-pointer transition-colors ${wraps.length >= 10 ? "bg-tesla-gray-700 cursor-not-allowed" : "bg-tesla-blue hover:bg-tesla-blue/80"} ${uploading ? "opacity-50" : ""}`}>
          <Upload className="w-4 h-4" /> {uploading ? "上传中..." : "上传"}
          <input type="file" accept=".png" onChange={handleUpload} className="hidden" disabled={uploading || wraps.length >= 10} />
        </label>
      </div>

      {loading ? <div className="animate-pulse text-tesla-gray-400">加载中...</div> :
       wraps.length === 0 ? (
        <div className="text-center py-16 text-tesla-gray-500">
          <Image className="w-12 h-12 mx-auto mb-3 opacity-30" />
          <p>暂无车衣图片</p>
        </div>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
          {wraps.map((w) => (
            <div key={w.filename} className="p-3 rounded-xl bg-tesla-gray-800/50 border border-tesla-gray-800 group relative">
              <button onClick={() => handleDelete(w.filename)}
                className="absolute top-2 right-2 p-1 rounded bg-black/60 text-tesla-gray-400 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity">
                <Trash2 className="w-3.5 h-3.5" />
              </button>
              <div className="text-xs font-medium truncate mb-1">{w.filename}</div>
              <div className="text-[10px] text-tesla-gray-500 space-y-0.5">
                <div>{w.width}x{w.height} · {w.size_kb.toFixed(0)} KB</div>
                <div className="flex items-center gap-1">
                  {w.valid ? <CheckCircle className="w-3 h-3 text-green-400" /> : <AlertCircle className="w-3 h-3 text-amber-500" />}
                  {w.valid ? "有效" : "无效尺寸"}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
