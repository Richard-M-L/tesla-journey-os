import { useState, useEffect, useCallback } from "react";
import { FileText, Upload, Trash2, CheckCircle, AlertCircle } from "lucide-react";

interface Plate { filename: string; size_kb: number; width: number; height: number; valid_dims: boolean; region: string; valid: boolean; }

export function PlatesPage() {
  const [plates, setPlates] = useState<Plate[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchPlates = useCallback(async () => {
    try { const r = await fetch("/api/media/plates"); const d = await r.json(); setPlates(d.plates || []); }
    catch (e) { console.error(e); } finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchPlates(); }, [fetchPlates]);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]; if (!file) return;
    try {
      const form = new FormData(); form.append("file", file);
      const r = await fetch("/api/media/plates/upload", { method: "POST", body: form });
      const d = await r.json();
      if (d.success) fetchPlates(); else alert(d.error);
    } catch (e) { alert("Upload error"); }
  };

  const handleDelete = async (f: string) => {
    if (!confirm(`Delete ${f}?`)) return;
    await fetch(`/api/media/plates/${encodeURIComponent(f)}`, { method: "DELETE" });
    fetchPlates();
  };

  return (
    <div className="max-w-4xl space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">车牌</h1>
          <p className="text-xs text-tesla-gray-500 mt-1">PNG · 420x200 (NA) / 420x100 (EU) · ≤512KB</p>
        </div>
        <label className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-tesla-blue hover:bg-tesla-blue/80 cursor-pointer transition-colors">
          <Upload className="w-4 h-4" /> 上传
          <input type="file" accept=".png" onChange={handleUpload} className="hidden" />
        </label>
      </div>

      {loading ? <div className="animate-pulse text-tesla-gray-400">加载中...</div> :
       plates.length === 0 ? (
        <div className="text-center py-16 text-tesla-gray-500">
          <FileText className="w-12 h-12 mx-auto mb-3 opacity-30" />
          <p>暂无车牌图片</p>
        </div>
      ) : (
        <div className="space-y-2">
          {plates.map((p) => (
            <div key={p.filename} className="flex items-center justify-between px-4 py-3 rounded-xl bg-tesla-gray-800/50 border border-tesla-gray-800">
              <div className="flex items-center gap-3">
                {p.valid_dims ? <CheckCircle className="w-4 h-4 text-green-400" /> : <AlertCircle className="w-4 h-4 text-amber-500" />}
                <div>
                  <span className="text-sm font-medium">{p.filename}</span>
                  <span className="text-xs text-tesla-gray-500 ml-2">{p.width}x{p.height} · {p.region} · {p.size_kb.toFixed(0)} KB</span>
                </div>
              </div>
              <button onClick={() => handleDelete(p.filename)} className="text-tesla-gray-600 hover:text-red-400 transition-colors">
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
