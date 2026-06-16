import { useState, useEffect, useCallback, useRef } from "react";
import { FileText, Upload, Trash2, CheckCircle, AlertCircle } from "lucide-react";

interface Plate {
  filename: string; size_kb: number; width: number; height: number;
  valid_dims: boolean; region: string; compliant: boolean; issues: string[];
}

export function PlatesPage() {
  const [plates, setPlates] = useState<Plate[]>([]);
  const [loading, setLoading] = useState(true);
  const [region, setRegion] = useState<"NA"|"EU">("NA");
  const [dragOver, setDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const fetchPlates = useCallback(async () => {
    try { const r = await fetch("/api/media/plates"); const d = await r.json(); setPlates(d.plates || []); }
    catch (e) { console.error(e); } finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchPlates(); }, [fetchPlates]);

  const handleUpload = async (file: File) => {
    setUploading(true);
    try {
      const form = new FormData(); form.append("file", file);
      const r = await fetch(`/api/media/plates/upload?region=${region}`, { method: "POST", body: form });
      const d = await r.json();
      if (!d.success) alert(d.error || "上传失败");
      await fetchPlates();
    } catch { alert("上传失败"); }
    finally { setUploading(false); }
  };

  const handleFiles = (files: FileList | File[]) => {
    Array.from(files).forEach(f => handleUpload(f));
  };

  const handleDelete = async (f: string) => {
    if (!confirm(`删除 ${f}？`)) return;
    await fetch(`/api/media/plates/${encodeURIComponent(f)}`, { method: "DELETE" });
    fetchPlates();
  };

  return (
    <div className="max-w-4xl space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">车牌</h1>
          <p className="text-xs text-tesla-gray-500 mt-1">自动裁剪至 420x200(NA) 或 420x100(EU) · ≤512KB · 文件名仅字母数字 ≤32 字符 · 最多10个</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex rounded-lg overflow-hidden border border-tesla-gray-700">
            <button onClick={() => setRegion("NA")}
              className={`px-3 py-1.5 text-xs font-medium ${region==="NA"?"bg-tesla-blue text-white":"bg-tesla-gray-800 text-tesla-gray-400"}`}>北美 420×200</button>
            <button onClick={() => setRegion("EU")}
              className={`px-3 py-1.5 text-xs font-medium ${region==="EU"?"bg-tesla-blue text-white":"bg-tesla-gray-800 text-tesla-gray-400"}`}>欧洲 420×100</button>
          </div>
          <label className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-tesla-blue hover:bg-tesla-blue/80 cursor-pointer">
            <Upload className="w-4 h-4" /> {uploading ? "上传中..." : "上传"}
            <input ref={inputRef} type="file" accept=".png,.jpg,.jpeg,.webp,.gif,.bmp" onChange={e => e.target.files && handleFiles(e.target.files)} className="hidden" />
          </label>
        </div>
      </div>

      {/* Drag-drop zone */}
      <div
        onDragOver={e => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={e => { e.preventDefault(); setDragOver(false); handleFiles(e.dataTransfer.files); }}
        className={`p-6 rounded-xl border-2 border-dashed text-center transition-colors cursor-pointer ${dragOver ? "border-tesla-blue bg-tesla-blue/10" : "border-tesla-gray-700 hover:border-tesla-gray-500"}`}
        onClick={() => inputRef.current?.click()}
      >
        <FileText className="w-10 h-10 mx-auto mb-2 text-tesla-gray-500" />
        <p className="text-sm text-tesla-gray-400">拖放任意图片 (PNG/JPEG/WEBP/GIF/BMP)</p>
        <p className="text-xs text-tesla-gray-600 mt-1">自动裁剪缩放至 {region==="NA"?"420×200":"420×100"}</p>
      </div>

      {loading ? <div className="animate-pulse text-tesla-gray-400">加载中...</div> :
       plates.length === 0 ? (
        <div className="text-center py-16 text-tesla-gray-500">
          <FileText className="w-12 h-12 mx-auto mb-3 opacity-30" />
          <p>暂无车牌图片</p>
        </div>
      ) : (
        <div className="space-y-2">
          {plates.map(p => (
            <div key={p.filename} className={`p-4 rounded-xl border ${p.compliant ? "bg-tesla-gray-800/50 border-tesla-gray-800" : "bg-amber-500/5 border-amber-500/20"}`}>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  {p.compliant ? <CheckCircle className="w-4 h-4 text-green-400" /> :
                   <AlertCircle className="w-4 h-4 text-amber-500" />}
                  <div>
                    <span className="text-sm font-medium">{p.filename}</span>
                    <span className="text-xs text-tesla-gray-500 ml-2">
                      {p.width}x{p.height} · {p.region} · {p.size_kb.toFixed(0)}KB
                    </span>
                  </div>
                </div>
                <button onClick={() => handleDelete(p.filename)}
                  className="text-tesla-gray-600 hover:text-red-400"><Trash2 className="w-4 h-4" /></button>
              </div>
              {p.issues.length > 0 && (
                <div className="mt-2 ml-7 space-y-0.5">
                  {p.issues.map((issue, i) => (
                    <div key={i} className="text-xs text-amber-400 flex items-center gap-1">
                      <AlertCircle className="w-3 h-3" /> {issue}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
