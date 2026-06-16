import { useState, useEffect, useCallback, useRef } from "react";
import { Image, Upload, Trash2, CheckCircle, AlertCircle, X } from "lucide-react";

interface Wrap {
  filename: string; size_kb: number; width: number; height: number;
  valid: boolean; compliant: boolean; modified: string;
}

export function WrapsPage() {
  const [wraps, setWraps] = useState<Wrap[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [uploadFiles, setUploadFiles] = useState<File[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const [results, setResults] = useState<{filename:string; success:boolean; error?:string}[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  const fetchWraps = useCallback(async () => {
    try { const r = await fetch("/api/media/wraps"); const d = await r.json(); setWraps(d.wraps || []); }
    catch (e) { console.error(e); } finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchWraps(); }, [fetchWraps]);

  const handleFiles = (files: FileList | File[]) => {
    const arr = Array.from(files).filter(f => f.name.toLowerCase().endsWith(".png"));
    if (arr.length === 0) { alert("仅支持 PNG 文件"); return; }
    const total = wraps.length + arr.length;
    if (total > 10) { alert(`最多 10 个车衣（当前 ${wraps.length}，尝试添加 ${arr.length}）`); return; }
    setUploadFiles(arr);
  };

  const handleUploadAll = async () => {
    if (uploadFiles.length === 0) return;
    setUploading(true);
    const res: {filename:string; success:boolean; error?:string}[] = [];
    for (const file of uploadFiles) {
      try {
        const form = new FormData(); form.append("file", file);
        const r = await fetch("/api/media/wraps/upload", { method: "POST", body: form });
        const d = await r.json();
        res.push({filename: file.name, success: d.success, error: d.error});
      } catch { res.push({filename: file.name, success: false, error: "上传失败"}); }
    }
    setResults(res);
    setUploadFiles([]);
    setUploading(false);
    await fetchWraps();
  };

  const handleDelete = async (f: string) => {
    if (!confirm(`删除 ${f}？`)) return;
    await fetch(`/api/media/wraps/${encodeURIComponent(f)}`, { method: "DELETE" });
    fetchWraps();
  };

  return (
    <div className="max-w-4xl space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">车衣</h1>
          <p className="text-xs text-tesla-gray-500 mt-1">PNG · 512-1024px · ≤1MB · 最多 10 个 · 文件名 ≤30 字符</p>
        </div>
      </div>

      {/* Drag-drop zone */}
      <div
        onDragOver={e => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={e => { e.preventDefault(); setDragOver(false); handleFiles(e.dataTransfer.files); }}
        className={`p-8 rounded-xl border-2 border-dashed text-center transition-colors cursor-pointer ${dragOver ? "border-tesla-blue bg-tesla-blue/10" : "border-tesla-gray-700 hover:border-tesla-gray-500"}`}
        onClick={() => inputRef.current?.click()}
      >
        <input ref={inputRef} type="file" accept=".png" multiple
          onChange={e => e.target.files && handleFiles(e.target.files)} className="hidden" />
        <Image className="w-10 h-10 mx-auto mb-2 text-tesla-gray-500" />
        <p className="text-sm text-tesla-gray-400">拖放 PNG 文件到此处</p>
        <p className="text-xs text-tesla-gray-600 mt-1">或点击选择文件（可多选）</p>
      </div>

      {/* Queued files */}
      {uploadFiles.length > 0 && (
        <div className="p-4 rounded-xl bg-tesla-gray-800/50 border border-tesla-gray-800">
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm font-semibold">待上传 ({uploadFiles.length})</span>
            <div className="flex gap-2">
              <button onClick={() => setUploadFiles([])} className="px-3 py-1 text-xs rounded bg-tesla-gray-700 hover:bg-tesla-gray-600">清空</button>
              <button onClick={handleUploadAll} disabled={uploading}
                className="px-4 py-1 text-xs rounded bg-tesla-blue hover:bg-tesla-blue/80 disabled:opacity-50">
                {uploading ? "上传中..." : "全部上传"}
              </button>
            </div>
          </div>
          <div className="space-y-1">
            {uploadFiles.map((f,i) => <div key={i} className="text-xs text-tesla-gray-400">{f.name} ({(f.size/1024).toFixed(0)}KB)</div>)}
          </div>
        </div>
      )}

      {/* Results */}
      {results.length > 0 && (
        <div className="p-3 rounded-xl bg-tesla-gray-800/30 border border-tesla-gray-800 space-y-1">
          {results.map((r,i) => (
            <div key={i} className="flex items-center gap-2 text-xs">
              {r.success ? <CheckCircle className="w-3 h-3 text-green-400" /> : <AlertCircle className="w-3 h-3 text-red-400" />}
              <span>{r.filename}</span>
              {r.error && <span className="text-red-400">{r.error}</span>}
            </div>
          ))}
        </div>
      )}

      {/* File grid */}
      {loading ? <div className="animate-pulse text-tesla-gray-400">加载中...</div> :
       wraps.length === 0 ? (
        <div className="text-center py-16 text-tesla-gray-500">
          <Image className="w-12 h-12 mx-auto mb-3 opacity-30" />
          <p>暂无车衣图片</p>
        </div>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
          {wraps.map(w => (
            <div key={w.filename} className="p-3 rounded-xl bg-tesla-gray-800/50 border border-tesla-gray-800 group relative">
              <button onClick={() => handleDelete(w.filename)}
                className="absolute top-2 right-2 p-1 rounded bg-black/60 text-tesla-gray-400 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity">
                <Trash2 className="w-3.5 h-3.5" />
              </button>
              <div className="text-xs font-medium truncate mb-1" title={w.filename}>{w.filename}</div>
              <div className="text-[10px] text-tesla-gray-500 space-y-0.5">
                <div>{w.width}x{w.height} · {w.size_kb.toFixed(0)}KB</div>
                <div className="flex items-center gap-1">
                  {w.compliant ? <><CheckCircle className="w-3 h-3 text-green-400" />合规</> :
                   <><AlertCircle className="w-3 h-3 text-amber-500" />不合规</>}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
