import { useState, useEffect, useCallback } from "react";
import { Music, Upload, Trash2, Plus, RefreshCw, Play, Pause, Volume2, Clock, FolderOpen } from "lucide-react";

interface Chime {
  filename: string; size_kb: number; duration_s: number;
  sample_rate: number; channels: number; valid: boolean; message: string; modified: string;
}
interface Group { id: string; name: string; description: string; files: string[]; file_count: number; }
interface Schedule {
  id: number; name: string; chime_filename: string; schedule_type: string; enabled: boolean;
  time: string; days: string[]; month: number; day: number; holiday: string; interval: string;
  last_run: string;
}

const LOUDNESS_PRESETS = [
  { id: "broadcast", label: "广播标准 (-23 LUFS)" },
  { id: "streaming", label: "流媒体 (-16 LUFS, 推荐)" },
  { id: "loud", label: "响亮 (-14 LUFS)" },
  { id: "maximum", label: "最大 (-12 LUFS)" },
];
const SCHEDULE_TYPES = ["weekly","date","holiday","recurring"] as const;
const DAYS = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"];
const DAY_LABELS: Record<string,string> = {"Mon":"周一","Tue":"周二","Wed":"周三","Thu":"周四","Fri":"周五","Sat":"周六","Sun":"周日"};
const HOLIDAYS = ["元旦","春节","除夕","元宵节","清明节","劳动节","端午节","中秋","国庆","冬至","Easter","Christmas","Halloween","Thanksgiving"];
const INTERVALS = [
  { id: "on_boot", label: "每次启动" }, { id: "15min", label: "每 15 分钟" },
  { id: "30min", label: "每 30 分钟" }, { id: "1hour", label: "每小时" },
  { id: "2hour", label: "每 2 小时" }, { id: "4hour", label: "每 4 小时" },
  { id: "6hour", label: "每 6 小时" }, { id: "12hour", label: "每 12 小时" },
];

export function LockChimesPage() {
  const [chimes, setChimes] = useState<Chime[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [preset, setPreset] = useState("streaming");
  const [normalize, setNormalize] = useState(true);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [activeTab, setActiveTab] = useState<"library"|"groups"|"schedules">("library");
  // Schedule form
  const [showSchedForm, setShowSchedForm] = useState(false);
  const [schedForm, setSchedForm] = useState({ name:"", chime_filename:"RANDOM", schedule_type:"weekly" as typeof SCHEDULE_TYPES[number], time:"08:00", days:["Mon"], month:1, day:1, holiday:"", interval:"on_boot" });

  const fetchAll = useCallback(async () => {
    try {
      const r = await fetch("/api/media/chimes");
      const d = await r.json();
      setChimes(d.chimes || []);
      setGroups(d.groups || []);
      setSchedules(d.schedules || []);
    } catch (e) { console.error(e); } finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]; if (!file) return;
    setUploading(true); setUploadProgress(0);
    const form = new FormData(); form.append("file", file);
    try {
      const r = await fetch(`/api/media/chimes/upload?preset=${preset}&normalize=${normalize}`, { method: "POST", body: form });
      const d = await r.json();
      if (d.success) { await fetchAll(); setUploadProgress(100); }
      else alert(d.error || "上传失败");
    } catch { alert("上传失败"); }
    finally { setUploading(false); }
  };

  const handleDelete = async (f: string) => {
    if (!confirm(`删除 ${f}？`)) return;
    await fetch(`/api/media/chimes/${encodeURIComponent(f)}`, { method: "DELETE" });
    await fetchAll();
  };

  const handleCreateGroup = async () => {
    const name = prompt("分组名称：");
    if (!name) return;
    const r = await fetch(`/api/media/chimes/groups/create?name=${encodeURIComponent(name)}`, { method: "POST" });
    const d = await r.json();
    if (d.success) await fetchAll(); else alert(d.error);
  };

  const handleAddSched = async () => {
    const params = new URLSearchParams({
      name: schedForm.name, chime_filename: schedForm.chime_filename,
      schedule_type: schedForm.schedule_type, time: schedForm.time,
      days: schedForm.days.join(","), month: String(schedForm.month),
      day: String(schedForm.day), holiday: schedForm.holiday,
      interval: schedForm.interval,
    });
    const r = await fetch(`/api/media/chimes/schedules/add?${params}`, { method: "POST" });
    const d = await r.json();
    if (d.success) { setShowSchedForm(false); await fetchAll(); }
    else alert(d.error);
  };

  const handleDeleteSched = async (id: number) => {
    if (!confirm("删除此排程？")) return;
    await fetch(`/api/media/chimes/schedules/${id}`, { method: "DELETE" });
    await fetchAll();
  };

  return (
    <div className="max-w-4xl space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold tracking-tight">锁车音效</h1>
        <label className={`inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium cursor-pointer transition-colors ${uploading ? "bg-tesla-gray-700" : "bg-tesla-blue hover:bg-tesla-blue/80"}`}>
          <Upload className="w-4 h-4" /> {uploading ? `上传中 ${uploadProgress}%` : "上传 WAV/MP3"}
          <input type="file" accept=".wav,.mp3" onChange={handleUpload} className="hidden" disabled={uploading} />
        </label>
      </div>

      {/* Upload settings */}
      <div className="flex items-center gap-4 p-3 rounded-xl bg-tesla-gray-800/30 border border-tesla-gray-800 text-sm">
        <Volume2 className="w-4 h-4 text-tesla-gray-500" />
        <select value={preset} onChange={e => setPreset(e.target.value)}
          className="bg-tesla-gray-800 border border-tesla-gray-700 rounded px-2 py-1 text-sm">
          {LOUDNESS_PRESETS.map(p => <option key={p.id} value={p.id}>{p.label}</option>)}
        </select>
        <label className="flex items-center gap-2 text-tesla-gray-400">
          <input type="checkbox" checked={normalize} onChange={e => setNormalize(e.target.checked)} />
          归一化
        </label>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 p-1 rounded-xl bg-tesla-gray-800/50 border border-tesla-gray-800 w-fit">
        {(["library","groups","schedules"] as const).map(t => (
          <button key={t} onClick={() => setActiveTab(t)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${activeTab===t ? "bg-tesla-gray-700 text-white" : "text-tesla-gray-400 hover:text-white"}`}>
            {t==="library"?"音效库":t==="groups"?"分组":"排程"}
          </button>
        ))}
      </div>

      {/* LIBRARY TAB */}
      {activeTab === "library" && (
        <div className="rounded-xl bg-tesla-gray-800/50 border border-tesla-gray-800 overflow-hidden">
          {loading ? <div className="p-8 text-center text-tesla-gray-400 animate-pulse">加载中...</div> :
           chimes.length === 0 ? (
            <div className="p-8 text-center text-tesla-gray-500">
              <Music className="w-10 h-10 mx-auto mb-2 opacity-30" />
              <p>暂无锁车音效，上传 WAV 或 MP3 文件开始</p>
            </div>
          ) : (
            <div className="divide-y divide-tesla-gray-800/50">
              {chimes.map(c => (
                <div key={c.filename} className="flex items-center justify-between px-5 py-3">
                  <div>
                    <span className="text-sm font-medium">{c.filename}</span>
                    <span className="text-xs text-tesla-gray-500 ml-3">
                      {c.duration_s.toFixed(1)}s · {c.size_kb.toFixed(0)}kB
                      {c.sample_rate>0 && ` · ${(c.sample_rate/1000).toFixed(1)}kHz`}
                      {c.channels===1?" 单声道":" 立体声"}
                    </span>
                    {!c.valid && <span className="text-xs text-amber-500 ml-2">⚠ {c.message}</span>}
                  </div>
                  <button onClick={() => handleDelete(c.filename)}
                    className="text-tesla-gray-600 hover:text-red-400 transition-colors">
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* GROUPS TAB */}
      {activeTab === "groups" && (
        <div className="space-y-3">
          <button onClick={handleCreateGroup}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-tesla-blue hover:bg-tesla-blue/80">
            <Plus className="w-4 h-4" /> 创建分组
          </button>
          {groups.length === 0 ? (
            <p className="text-sm text-tesla-gray-500">暂无分组。创建分组后可随机轮换音效。</p>
          ) : (
            groups.map(g => (
              <div key={g.id} className="p-4 rounded-xl bg-tesla-gray-800/50 border border-tesla-gray-800">
                <div className="flex items-center justify-between mb-2">
                  <div>
                    <span className="text-sm font-semibold">{g.name}</span>
                    <span className="text-xs text-tesla-gray-500 ml-2">{g.file_count} 个音效</span>
                    {g.description && <p className="text-xs text-tesla-gray-500 mt-0.5">{g.description}</p>}
                  </div>
                  <button onClick={async () => {
                    await fetch(`/api/media/chimes/groups/${g.id}`, { method: "DELETE" }); fetchAll();
                  }} className="text-tesla-gray-600 hover:text-red-400"><Trash2 className="w-4 h-4" /></button>
                </div>
                <div className="flex flex-wrap gap-1">
                  {g.files.map(f => <span key={f} className="px-2 py-0.5 text-xs rounded bg-tesla-gray-700 text-tesla-gray-400">{f}</span>)}
                  {g.files.length===0 && <span className="text-xs text-tesla-gray-500">空分组</span>}
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {/* SCHEDULES TAB */}
      {activeTab === "schedules" && (
        <div className="space-y-3">
          <button onClick={() => setShowSchedForm(!showSchedForm)}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-tesla-blue hover:bg-tesla-blue/80">
            <Clock className="w-4 h-4" /> {showSchedForm ? "取消" : "创建排程"}
          </button>

          {showSchedForm && (
            <div className="p-4 rounded-xl bg-tesla-gray-800/50 border border-tesla-gray-800 space-y-3">
              <input placeholder="排程名称" value={schedForm.name}
                onChange={e => setSchedForm({...schedForm, name: e.target.value})}
                className="w-full px-3 py-2 rounded bg-tesla-gray-800 border border-tesla-gray-700 text-sm text-white" />
              <div className="flex gap-2">
                <select value={schedForm.schedule_type}
                  onChange={e => setSchedForm({...schedForm, schedule_type: e.target.value as typeof SCHEDULE_TYPES[number]})}
                  className="px-3 py-2 rounded bg-tesla-gray-800 border border-tesla-gray-700 text-sm">
                  <option value="weekly">每周</option><option value="date">指定日期</option>
                  <option value="holiday">节假日</option><option value="recurring">定期轮换</option>
                </select>
                <select value={schedForm.chime_filename}
                  onChange={e => setSchedForm({...schedForm, chime_filename: e.target.value})}
                  className="px-3 py-2 rounded bg-tesla-gray-800 border border-tesla-gray-700 text-sm">
                  <option value="RANDOM">随机</option>
                  {chimes.map(c => <option key={c.filename} value={c.filename}>{c.filename}</option>)}
                </select>
              </div>
              {schedForm.schedule_type === "weekly" && (
                <div className="flex gap-1 flex-wrap">
                  {DAYS.map(d => (
                    <button key={d} onClick={() => setSchedForm({...schedForm, days: schedForm.days.includes(d) ? schedForm.days.filter(x=>x!==d) : [...schedForm.days, d]})}
                      className={`px-3 py-1 text-xs rounded ${schedForm.days.includes(d) ? "bg-tesla-blue text-white" : "bg-tesla-gray-700 text-tesla-gray-400"}`}>
                      {DAY_LABELS[d]}</button>
                  ))}
                </div>
              )}
              {schedForm.schedule_type === "date" && (
                <div className="flex gap-2">
                  <input type="number" min={1} max={12} value={schedForm.month}
                    onChange={e => setSchedForm({...schedForm, month: +e.target.value})}
                    className="w-16 px-2 py-1 rounded bg-tesla-gray-800 border border-tesla-gray-700 text-sm" placeholder="月" />
                  <input type="number" min={1} max={31} value={schedForm.day}
                    onChange={e => setSchedForm({...schedForm, day: +e.target.value})}
                    className="w-16 px-2 py-1 rounded bg-tesla-gray-800 border border-tesla-gray-700 text-sm" placeholder="日" />
                </div>
              )}
              {schedForm.schedule_type === "holiday" && (
                <select value={schedForm.holiday}
                  onChange={e => setSchedForm({...schedForm, holiday: e.target.value})}
                  className="px-3 py-2 rounded bg-tesla-gray-800 border border-tesla-gray-700 text-sm">
                  <option value="">选择节日...</option>
                  {HOLIDAYS.map(h => <option key={h} value={h}>{h}</option>)}
                </select>
              )}
              {schedForm.schedule_type === "recurring" && (
                <select value={schedForm.interval}
                  onChange={e => setSchedForm({...schedForm, interval: e.target.value})}
                  className="px-3 py-2 rounded bg-tesla-gray-800 border border-tesla-gray-700 text-sm">
                  {INTERVALS.map(i => <option key={i.id} value={i.id}>{i.label}</option>)}
                </select>
              )}
              {schedForm.schedule_type !== "recurring" && (
                <input type="time" value={schedForm.time}
                  onChange={e => setSchedForm({...schedForm, time: e.target.value})}
                  className="px-3 py-2 rounded bg-tesla-gray-800 border border-tesla-gray-700 text-sm" />
              )}
              <button onClick={handleAddSched}
                className="px-4 py-2 rounded-lg bg-green-600 text-sm font-medium hover:bg-green-500">保存排程</button>
            </div>
          )}

          {schedules.length === 0 ? (
            <p className="text-sm text-tesla-gray-500">暂无排程</p>
          ) : (
            schedules.map(s => (
              <div key={s.id} className="flex items-center justify-between p-4 rounded-xl bg-tesla-gray-800/50 border border-tesla-gray-800">
                <div>
                  <span className="text-sm font-medium">{s.name}</span>
                  <span className="text-xs text-tesla-gray-500 ml-2">
                    {s.schedule_type === "recurring" ? INTERVALS.find(i=>i.id===s.interval)?.label :
                     s.schedule_type === "weekly" ? `每周 ${s.days.map(d=>DAY_LABELS[d]||d).join(",")} ${s.time}` :
                     s.schedule_type === "date" ? `${s.month}/${s.day} ${s.time}` :
                     s.schedule_type === "holiday" ? `${s.holiday} ${s.time}` : s.time}
                  </span>
                </div>
                <button onClick={() => handleDeleteSched(s.id)}
                  className="text-tesla-gray-600 hover:text-red-400"><Trash2 className="w-4 h-4" /></button>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
