import { useState, useEffect, useCallback, useRef } from "react";
import { Zap, Upload, Trash2, CheckCircle, AlertCircle, Music, Play, Pause } from "lucide-react";

interface ShowFile { filename: string; size_bytes: number; ext: string; }
interface Show {
  name: string; files: ShowFile[]; file_count: number;
  has_fseq: boolean; has_audio: boolean; valid: boolean; total_size_bytes: number;
}

export function LightShowsPage() {
  const [shows, setShows] = useState<Show[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [playing, setPlaying] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement>(null);

  const fetchData = useCallback(async () => {
    try { const r = await fetch("/api/media/lightshows"); const d = await r.json(); setShows(d.shows || []); }
    catch (e) { console.error(e); } finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]; if (!file) return;
    setUploading(true);
    try {
      const form = new FormData(); form.append("file", file);
      const r = await fetch("/api/media/lightshows/upload", { method: "POST", body: form });
      const d = await r.json();
      if (d.success) { await fetchData(); if (d.errors?.length) alert("部分文件出错: " + d.errors.join(", ")); }
      else alert(d.error || "上传失败");
    } catch { alert("上传失败"); }
    finally { setUploading(false); }
  };

  const handleDelete = async (name: string) => {
    if (!confirm(`删除灯光秀 "${name}"？`)) return;
    await fetch(`/api/media/lightshows/${name}`, { method: "DELETE" });
    await fetchData();
  };

  const handlePreview = (name: string) => {
    if (playing === name) { audioRef.current?.pause(); setPlaying(null); return; }
    // Find the audio file for this show
    const show = shows.find(s => s.name === name);
    const audioFile = show?.files.find(f => f.ext === ".mp3" || f.ext === ".wav");
    if (!audioFile) return;
    // Stream via API
    const url = `/api/videos/stream?path=${encodeURIComponent(`/opt/tesla-journey-os/data/media/LightShow/${audioFile.filename}`)}`;
    if (audioRef.current) { audioRef.current.src = url; audioRef.current.play(); }
    setPlaying(name);
  };

  return (
    <div className="max-w-4xl space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold tracking-tight">灯光秀</h1>
        <label className={`inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium cursor-pointer transition-colors ${uploading ? "bg-tesla-gray-700" : "bg-tesla-blue hover:bg-tesla-blue/80"}`}>
          <Upload className="w-4 h-4" /> {uploading ? "上传中..." : "上传"}
          <input type="file" accept=".zip,.fseq,.mp3,.wav" onChange={handleUpload} className="hidden" disabled={uploading} />
        </label>
      </div>

      <audio ref={audioRef} onEnded={() => setPlaying(null)} className="hidden" />

      {loading ? <div className="animate-pulse text-tesla-gray-400">加载中...</div> :
       shows.length === 0 ? (
        <div className="text-center py-16 text-tesla-gray-500">
          <Zap className="w-12 h-12 mx-auto mb-3 opacity-30" />
          <p>暂无灯光秀，上传 .fseq + .mp3/.wav 文件或 ZIP 压缩包</p>
        </div>
      ) : (
        <div className="space-y-3">
          {shows.map(show => (
            <div key={show.name} className="p-4 rounded-xl bg-tesla-gray-800/50 border border-tesla-gray-800">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-3">
                  {show.valid ? <CheckCircle className="w-5 h-5 text-green-400" /> :
                   <AlertCircle className="w-5 h-5 text-amber-500" />}
                  <div>
                    <h3 className="text-sm font-semibold">{show.name}</h3>
                    <p className="text-xs text-tesla-gray-500">
                      {show.file_count} 文件 · {(show.total_size_bytes / 1024).toFixed(0)}KB
                      {!show.valid && <span className="text-amber-500 ml-1">· 缺少 .fseq</span>}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {show.has_audio && (
                    <button onClick={() => handlePreview(show.name)}
                      className={`p-2 rounded-lg text-xs transition-colors ${playing === show.name ? "bg-tesla-blue/20 text-tesla-blue" : "bg-tesla-gray-700 text-tesla-gray-400 hover:text-white"}`}>
                      {playing === show.name ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
                    </button>
                  )}
                  <button onClick={() => handleDelete(show.name)}
                    className="p-2 rounded-lg text-tesla-gray-600 hover:text-red-400 transition-colors">
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
              {/* Paired files */}
              <div className="grid grid-cols-2 gap-2">
                {show.files.map(f => (
                  <div key={f.filename} className="flex items-center gap-2 px-3 py-1.5 rounded bg-tesla-gray-800 text-xs">
                    <span className={`w-2 h-2 rounded-full ${f.ext===".fseq"?"bg-green-400":f.ext===".mp3"?"bg-blue-400":"bg-purple-400"}`} />
                    <span className="text-tesla-gray-300 truncate">{f.filename}</span>
                    <span className="text-tesla-gray-600 ml-auto">{(f.size_bytes/1024).toFixed(0)}KB</span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
