import { useState, useEffect, useCallback, useRef } from "react";
import { Volume2, Upload, Trash2, CheckCircle, AlertCircle, ShieldAlert } from "lucide-react";

interface BoomboxSound {
  filename: string; size_kb: number; format: string; valid: boolean; compliant: boolean;
}

const NHTSA_NOTICE = "外放音效仅在驻车时播放（2022年2月 NHTSA 召回 22V-068）。车辆必须配备外部行人警告扬声器——Model 3/Y/S/X 需 2019年9月后生产，Cybertruck 支持全部年份。";

export function BoomboxPage() {
  const [sounds, setSounds] = useState<BoomboxSound[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const fetchSounds = useCallback(async () => {
    try { const r = await fetch("/api/media/boombox"); const d = await r.json(); setSounds(d.sounds || []); }
    catch (e) { console.error(e); } finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchSounds(); }, [fetchSounds]);

  const handleUpload = async (file: File) => {
    setUploading(true);
    try {
      const form = new FormData(); form.append("file", file);
      const r = await fetch("/api/media/boombox/upload", { method: "POST", body: form });
      const d = await r.json();
      if (d.success) { await fetchSounds(); } else alert(d.error || "上传失败");
    } catch { alert("上传失败"); }
    finally { setUploading(false); }
  };

  const handleDelete = async (f: string) => {
    if (!confirm(`删除 ${f}？`)) return;
    await fetch(`/api/media/boombox/${encodeURIComponent(f)}`, { method: "DELETE" });
    fetchSounds();
  };

  return (
    <div className="max-w-4xl space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Boombox 音效</h1>
          <p className="text-xs text-tesla-gray-500 mt-1">MP3/WAV · ≤1MB · 最多 5 个 · 文件名 ≤64 字符</p>
        </div>
        <label className={`inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium cursor-pointer transition-colors ${sounds.length>=5 ? "bg-tesla-gray-700 cursor-not-allowed" : "bg-tesla-blue hover:bg-tesla-blue/80"}`}>
          <Upload className="w-4 h-4" /> {sounds.length>=5 ? "已满" : uploading ? "上传中..." : "上传"}
          <input ref={inputRef} type="file" accept=".mp3,.wav" onChange={e => { const f = e.target.files?.[0]; if (f) handleUpload(f); }} className="hidden" disabled={sounds.length>=5} />
        </label>
      </div>

      {/* NHTSA Safety Notice */}
      <div className="flex items-start gap-3 p-4 rounded-xl bg-amber-500/10 border border-amber-500/20">
        <ShieldAlert className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
        <div>
          <p className="text-sm text-amber-400 font-semibold mb-1">安全声明</p>
          <p className="text-xs text-amber-300/70">{NHTSA_NOTICE}</p>
        </div>
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
            <div key={s.filename} className={`px-4 py-3 rounded-xl border flex items-center justify-between ${s.compliant ? "bg-tesla-gray-800/50 border-tesla-gray-800" : "bg-red-500/5 border-red-500/20"}`}>
              <div className="flex items-center gap-3">
                <span className="text-xs text-tesla-gray-500 w-5">{i + 1}</span>
                {s.compliant ? <CheckCircle className="w-4 h-4 text-green-400" /> :
                 <AlertCircle className="w-4 h-4 text-red-400" />}
                <div>
                  <span className="text-sm font-medium">{s.filename}</span>
                  <span className="text-xs text-tesla-gray-500 ml-2">{s.size_kb.toFixed(0)}KB · {s.format}</span>
                </div>
              </div>
              <button onClick={() => handleDelete(s.filename)}
                className="text-tesla-gray-600 hover:text-red-400"><Trash2 className="w-4 h-4" /></button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
