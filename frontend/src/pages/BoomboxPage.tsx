import { useState, useEffect, useCallback } from "react";
import { Volume2, Upload, Trash2, CheckCircle, AlertCircle } from "lucide-react";

interface BoomboxSound { filename: string; size_bytes: number; format: string; valid: boolean; }

export function BoomboxPage() {
  const [sounds, setSounds] = useState<BoomboxSound[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchSounds = useCallback(async () => {
    try { const r = await fetch("/api/media/boombox"); const d = await r.json(); setSounds(d.sounds || []); }
    catch (e) { console.error(e); } finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchSounds(); }, [fetchSounds]);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]; if (!file) return;
    try {
      const form = new FormData(); form.append("file", file);
      const r = await fetch("/api/media/boombox/upload", { method: "POST", body: form });
      const d = await r.json();
      if (d.success) fetchSounds(); else alert(d.error || "Upload failed");
    } catch (e) { alert("Upload error"); }
  };

  const handleDelete = async (f: string) => {
    if (!confirm(`Delete ${f}?`)) return;
    await fetch(`/api/media/boombox/${encodeURIComponent(f)}`, { method: "DELETE" });
    fetchSounds();
  };

  return (
    <div className="max-w-4xl space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Boombox 音效</h1>
          <p className="text-xs text-tesla-gray-500 mt-1">
            MP3/WAV · 最多5个{ sounds.length >= 5 ? <span className="text-amber-400 ml-1">(已满)</span> : null}
          </p>
        </div>
        <label className={`inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium cursor-pointer transition-colors ${sounds.length >= 5 ? "bg-tesla-gray-700 cursor-not-allowed" : "bg-tesla-blue hover:bg-tesla-blue/80"}`}>
          <Upload className="w-4 h-4" /> 上传
          <input type="file" accept=".mp3,.wav" onChange={handleUpload} className="hidden" disabled={sounds.length >= 5} />
        </label>
      </div>

      {loading ? <div className="animate-pulse text-tesla-gray-400">加载中...</div> :
       sounds.length === 0 ? (
        <div className="text-center py-16 text-tesla-gray-500">
          <Volume2 className="w-12 h-12 mx-auto mb-3 opacity-30" />
          <p>暂无 Boombox 音效</p>
        </div>
      ) : (
        <div className="space-y-2">
          {sounds.map((s, i) => (
            <div key={s.filename} className="flex items-center justify-between px-4 py-3 rounded-xl bg-tesla-gray-800/50 border border-tesla-gray-800">
              <div className="flex items-center gap-3">
                <span className="text-xs text-tesla-gray-500 w-5">{i + 1}</span>
                {s.valid ? <CheckCircle className="w-4 h-4 text-green-400" /> : <AlertCircle className="w-4 h-4 text-amber-500" />}
                <div>
                  <span className="text-sm font-medium">{s.filename}</span>
                  <span className="text-xs text-tesla-gray-500 ml-2 uppercase">{s.format}</span>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-xs text-tesla-gray-500">{(s.size_bytes / 1024).toFixed(0)} KB</span>
                <button onClick={() => handleDelete(s.filename)} className="text-tesla-gray-600 hover:text-red-400 transition-colors">
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
