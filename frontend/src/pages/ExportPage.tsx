import { useState, useEffect, useCallback } from "react";
import { HardDrive, Upload, RefreshCw, CheckCircle, FolderOpen, Music, Zap, Image, FileText, Volume2 } from "lucide-react";

interface Category { file_count: number; size_mb: number; files: string[]; }
interface Preview { categories: Record<string, Category>; total_files: number; total_size_mb: number; }
interface UsbDrive { path: string; label: string; free_gb: number; total_gb: number; }
interface ExportResult { success: boolean; dry_run: boolean; target: string; total_copied: number; total_size_mb: number; results: Record<string, {copied:number; size_mb:number; file_count:number}>; errors: string[] | null; }

const CAT_ICONS: Record<string, React.ComponentType<{className?:string}>> = {
  LockChimes: Music, LightShow: Zap, Music: FolderOpen, Boombox: Volume2, Wraps: Image, LicensePlates: FileText,
};

export function ExportPage() {
  const [preview, setPreview] = useState<Preview | null>(null);
  const [drives, setDrives] = useState<UsbDrive[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [result, setResult] = useState<ExportResult | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const [pr, dr] = await Promise.all([
        fetch("/api/media/export/preview"),
        fetch("/api/media/export/usb-drives"),
      ]);
      setPreview(await pr.json());
      const dd = await dr.json();
      setDrives(dd.drives || []);
      if (dd.drives?.length > 0) setSelected(dd.drives[0].path);
    } catch (e) { console.error(e); } finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleExport = async (dryRun: boolean) => {
    if (!selected) return;
    setExporting(true);
    try {
      const r = await fetch("/api/media/export", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target: selected, dry_run: dryRun }),
      });
      setResult(await r.json());
    } catch { alert("导出失败"); }
    finally { setExporting(false); }
  };

  return (
    <div className="max-w-4xl space-y-6">
      <h1 className="text-2xl font-bold tracking-tight">导出到 U 盘</h1>

      {/* Preview */}
      <div className="p-5 rounded-xl bg-tesla-gray-800/50 border border-tesla-gray-800">
        <h2 className="text-sm font-semibold text-tesla-gray-300 mb-3">待导出内容</h2>
        {loading ? <div className="animate-pulse text-tesla-gray-400">加载中...</div> :
         !preview || preview.total_files === 0 ? (
          <p className="text-sm text-tesla-gray-500">暂无媒体文件可导出</p>
        ) : (
          <div className="space-y-3">
            {Object.entries(preview.categories).map(([name, cat]) => {
              const Icon = CAT_ICONS[name] || FolderOpen;
              return (
                <div key={name} className="flex items-center justify-between p-3 rounded-lg bg-tesla-gray-800">
                  <div className="flex items-center gap-3">
                    <Icon className="w-4 h-4 text-tesla-blue" />
                    <div>
                      <span className="text-sm font-medium">{name}</span>
                      <span className="text-xs text-tesla-gray-500 ml-2">{cat.file_count} 文件 · {cat.size_mb.toFixed(1)} MB</span>
                    </div>
                  </div>
                </div>
              );
            })}
            <div className="flex items-center justify-between pt-3 border-t border-tesla-gray-700 text-sm">
              <span className="text-tesla-gray-400">总计</span>
              <span className="font-semibold">{preview.total_files} 文件 · {preview.total_size_mb.toFixed(1)} MB</span>
            </div>
          </div>
        )}
      </div>

      {/* USB Drive Selection */}
      <div className="p-5 rounded-xl bg-tesla-gray-800/50 border border-tesla-gray-800">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-tesla-gray-300 flex items-center gap-2">
            <HardDrive className="w-4 h-4" /> 目标 U 盘
          </h2>
          <button onClick={fetchData} className="text-tesla-gray-500 hover:text-white">
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
        {drives.length === 0 ? (
          <div className="text-center py-8 text-tesla-gray-500">
            <HardDrive className="w-10 h-10 mx-auto mb-2 opacity-30" />
            <p className="text-sm">未检测到 U 盘</p>
            <p className="text-xs mt-1">插入 U 盘后点击刷新</p>
          </div>
        ) : (
          <div className="space-y-2">
            {drives.map(d => (
              <button key={d.path} onClick={() => setSelected(d.path)}
                className={`w-full text-left p-4 rounded-lg border transition-colors ${selected === d.path ? "border-tesla-blue bg-tesla-blue/10" : "border-tesla-gray-800 hover:border-tesla-gray-700"}`}>
                <div className="flex items-center justify-between">
                  <div>
                    <span className="text-sm font-medium">{d.label}</span>
                    <span className="text-xs text-tesla-gray-500 ml-2">{d.path}</span>
                  </div>
                  <span className="text-xs text-tesla-gray-500">{d.free_gb.toFixed(1)} / {d.total_gb.toFixed(1)} GB 可用</span>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Action buttons */}
      {preview && preview.total_files > 0 && drives.length > 0 && (
        <div className="flex gap-3">
          <button onClick={() => handleExport(true)} disabled={exporting}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-tesla-gray-700 hover:bg-tesla-gray-600 disabled:opacity-50">
            预览
          </button>
          <button onClick={() => handleExport(false)} disabled={exporting}
            className="flex items-center gap-2 px-6 py-2 rounded-lg text-sm font-medium bg-tesla-blue hover:bg-tesla-blue/80 disabled:opacity-50">
            <Upload className="w-4 h-4" /> {exporting ? "导出中..." : "导出到 U 盘"}
          </button>
        </div>
      )}

      {/* Results */}
      {result && (
        <div className={`p-5 rounded-xl border ${result.success ? "bg-green-500/10 border-green-500/20" : "bg-amber-500/10 border-amber-500/20"}`}>
          <h2 className={`text-sm font-semibold mb-3 flex items-center gap-2 ${result.success ? "text-green-400" : "text-amber-400"}`}>
            <CheckCircle className="w-4 h-4" />
            {result.dry_run ? "预览结果" : result.success ? "导出成功" : "导出完成（有错误）"}
          </h2>
          <div className="space-y-2">
            <p className="text-sm text-tesla-gray-300">
              共复制 {result.total_copied} 文件 · {result.total_size_mb.toFixed(1)} MB → {result.target}
            </p>
            {Object.entries(result.results).map(([name, r]) => (
              <div key={name} className="text-xs text-tesla-gray-400 flex items-center justify-between">
                <span>{name}</span>
                <span>{r.copied}/{r.file_count} 文件 · {r.size_mb.toFixed(1)} MB</span>
              </div>
            ))}
            {result.errors && result.errors.map((e, i) => (
              <div key={i} className="text-xs text-red-400">{e}</div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
