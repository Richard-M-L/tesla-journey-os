import { useState, useEffect, useCallback } from "react";
import { Wifi, Radio, Sliders, RefreshCw, Lock, Unlock, Signal, Plus, Trash2, AlertCircle, CheckCircle, ChevronUp, ChevronDown, Eye, EyeOff } from "lucide-react";

interface WifiNetwork {
  ssid: string; signal: number; security: string; secured: boolean;
}
interface SavedNet { name: string; ssid: string; priority: number; active: boolean; in_range: boolean; signal: number | null; }
interface WifiState { connected: boolean; ssid: string | null; signal: number | null; }

type Tab = "wifi" | "ap" | "advanced";

export function SettingsPage() {
  const [tab, setTab] = useState<Tab>("wifi");

  // WiFi state
  const [wifiState, setWifiState] = useState<WifiState>({ connected: false, ssid: null, signal: null });
  const [networks, setNetworks] = useState<WifiNetwork[]>([]);
  const [saved, setSaved] = useState<SavedNet[]>([]);
  const [scanning, setScanning] = useState(false);
  const [connecting, setConnecting] = useState<string | null>(null);
  const [connectSSID, setConnectSSID] = useState("");
  const [connectPass, setConnectPass] = useState("");
  const [error, setError] = useState("");

  // AP state
  const [apStatus, setApStatus] = useState<{ active: boolean; force_mode: string; ssid: string } | null>(null);
  const [apSSID, setApSSID] = useState("Tesla Journey OS");
  const [apPass, setApPass] = useState("");
  const [apSaving, setApSaving] = useState(false);

  const fetchWifiStatus = useCallback(async () => {
    try {
      const r = await fetch("/api/wifi/status");
      setWifiState(await r.json());
    } catch (e) { console.error(e); }
  }, []);

  const scan = useCallback(async () => {
    setScanning(true);
    try {
      const r = await fetch("/api/wifi/scan");
      const d = await r.json();
      setNetworks(d.networks || []);
    } catch (e) { console.error(e); } finally {
      setScanning(false);
    }
  }, []);

  const fetchSaved = useCallback(async () => {
    try {
      const r = await fetch("/api/wifi/saved");
      const d = await r.json();
      setSaved(d.saved || []);
    } catch (e) { console.error(e); }
  }, []);

  const fetchApStatus = useCallback(async () => {
    try {
      const r = await fetch("/api/ap/status");
      const d = await r.json();
      setApStatus(d);
      if (d.ssid) setApSSID(d.ssid);
    } catch (e) { console.error(e); }
  }, []);

  const fetchApConfig = useCallback(async () => {
    try {
      const r = await fetch("/api/ap/config");
      const d = await r.json();
      setApSSID(d.ssid || "Tesla Journey OS");
      setApPass(d.passphrase || "");
    } catch (e) { console.error(e); }
  }, []);

  useEffect(() => {
    fetchWifiStatus(); scan(); fetchSaved();
    fetchApStatus(); fetchApConfig();
  }, []);

  const handleConnect = async (ssid: string) => {
    setConnecting(ssid);
    setError("");
    try {
      const pass = ssid === connectSSID ? connectPass : prompt(`Password for ${ssid}:`) || "";
      const r = await fetch(`/api/wifi/connect?ssid=${encodeURIComponent(ssid)}&password=${encodeURIComponent(pass)}`, { method: "POST" });
      const d = await r.json();
      if (d.success) {
        setConnectSSID("");
        setConnectPass("");
        await fetchWifiStatus();
        await fetchSaved();
      } else {
        // Show password form inline
        setConnectSSID(ssid);
        setError(d.error || "Connection failed");
      }
    } catch (e) {
      setError("Connection error");
    } finally {
      setConnecting(null);
    }
  };

  const handleConnectWithPass = async () => {
    if (!connectSSID) return;
    setConnecting(connectSSID);
    setError("");
    try {
      const r = await fetch(`/api/wifi/connect?ssid=${encodeURIComponent(connectSSID)}&password=${encodeURIComponent(connectPass)}`, { method: "POST" });
      const d = await r.json();
      if (d.success) {
        setConnectSSID(""); setConnectPass(""); setError("");
        await fetchWifiStatus(); await fetchSaved();
      } else {
        setError(d.error || "Connection failed");
      }
    } catch (e) { setError("Connection error"); } finally { setConnecting(null); }
  };

  const handleForget = async (name: string) => {
    if (!confirm(`Forget "${name}"?`)) return;
    await fetch(`/api/wifi/forget/${encodeURIComponent(name)}`, { method: "DELETE" });
    await fetchSaved();
  };

  const handleApSave = async () => {
    setApSaving(true);
    try {
      const r = await fetch(`/api/ap/config?ssid=${encodeURIComponent(apSSID)}&passphrase=${encodeURIComponent(apPass)}`, { method: "POST" });
      const d = await r.json();
      if (!d.success) alert(d.error);
      else await fetchApStatus();
    } finally { setApSaving(false); }
  };

  const handleForceMode = async (mode: string) => {
    await fetch(`/api/ap/force-mode?mode=${mode}`, { method: "POST" });
    await fetchApStatus();
  };

  return (
    <div className="max-w-4xl space-y-6">
      <h1 className="text-2xl font-bold tracking-tight">设置</h1>

      {/* Tabs */}
      <div className="flex gap-1 p-1 rounded-xl bg-tesla-gray-800/50 border border-tesla-gray-800 w-fit">
        {(["wifi", "ap", "advanced"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              tab === t ? "bg-tesla-gray-700 text-white" : "text-tesla-gray-400 hover:text-white"
            }`}
          >
            {t === "wifi" ? <Wifi className="w-4 h-4" /> :
             t === "ap" ? <Radio className="w-4 h-4" /> : <Sliders className="w-4 h-4" />}
            {t === "wifi" ? "WiFi" : t === "ap" ? "热点" : "高级"}
          </button>
        ))}
      </div>

      {/* === WiFi Tab === */}
      {tab === "wifi" && (
        <div className="space-y-6">
          {/* Status */}
          <div className="p-5 rounded-xl bg-tesla-gray-800/50 border border-tesla-gray-800">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-tesla-gray-300 flex items-center gap-2">
                <Wifi className="w-4 h-4" />
                当前连接
              </h2>
              <button onClick={() => { scan(); fetchWifiStatus(); }} className="text-tesla-gray-500 hover:text-white">
                <RefreshCw className="w-4 h-4" />
              </button>
            </div>
            <div className="mt-3 flex items-center gap-4">
              <span className={`w-3 h-3 rounded-full ${wifiState.connected ? "bg-green-500" : "bg-gray-600"}`} />
              <span className="text-lg font-semibold">{wifiState.connected ? wifiState.ssid : "未连接"}</span>
              {wifiState.signal !== null && (
                <SignalIndicator pct={Math.min(100, Math.max(0, (wifiState.signal + 100) * 2))} />
              )}
            </div>
          </div>

          {/* Password form (shown inline when connection fails) */}
          {connectSSID && (
            <div className="p-4 rounded-xl bg-tesla-gray-800/50 border border-amber-500/30">
              <h3 className="text-sm font-semibold mb-3">输入密码: {connectSSID}</h3>
              {error && <p className="text-xs text-red-400 mb-2">{error}</p>}
              <div className="flex gap-2">
                <input
                  type="password" value={connectPass} onChange={(e) => setConnectPass(e.target.value)}
                  placeholder="WiFi 密码" className="flex-1 px-3 py-2 rounded-lg bg-tesla-gray-800 border border-tesla-gray-700 text-sm text-white placeholder-tesla-gray-500"
                  onKeyDown={(e) => e.key === "Enter" && handleConnectWithPass()}
                />
                <button onClick={handleConnectWithPass} disabled={connecting === connectSSID}
                  className="px-4 py-2 rounded-lg bg-tesla-blue text-sm font-medium hover:bg-tesla-blue/80 disabled:opacity-50">
                  {connecting === connectSSID ? "连接中..." : "连接"}
                </button>
                <button onClick={() => { setConnectSSID(""); setConnectPass(""); setError(""); }}
                  className="px-3 py-2 rounded-lg bg-tesla-gray-700 text-sm">取消</button>
              </div>
            </div>
          )}

          {/* Available Networks */}
          <div className="rounded-xl bg-tesla-gray-800/50 border border-tesla-gray-800 overflow-hidden">
            <div className="px-5 py-3 border-b border-tesla-gray-800 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-tesla-gray-300">可用网络</h2>
              <button onClick={scan} disabled={scanning}
                className={`text-xs flex items-center gap-1 ${scanning ? "text-tesla-gray-600" : "text-tesla-blue hover:underline"}`}>
                <RefreshCw className={`w-3 h-3 ${scanning ? "animate-spin" : ""}`} />
                {scanning ? "扫描中..." : "刷新"}
              </button>
            </div>
            <div className="divide-y divide-tesla-gray-800/50">
              {networks.slice(0, 15).map((n) => (
                <div key={n.ssid} className="flex items-center justify-between px-5 py-3">
                  <div className="flex items-center gap-3">
                    {n.secured ? <Lock className="w-3.5 h-3.5 text-tesla-gray-500" /> :
                                 <Unlock className="w-3.5 h-3.5 text-amber-500" />}
                    <div>
                      <span className="text-sm font-medium">{n.ssid}</span>
                      {wifiState.ssid === n.ssid && (
                        <span className="text-xs text-green-400 ml-2">已连接</span>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <SignalIndicator pct={Math.min(100, Math.max(0, (n.signal + 100) * 2))} />
                    <button
                      onClick={() => handleConnect(n.ssid)}
                      disabled={connecting === n.ssid || wifiState.ssid === n.ssid}
                      className="text-xs px-3 py-1.5 rounded-lg bg-tesla-blue/20 text-tesla-blue hover:bg-tesla-blue/30 disabled:opacity-30 transition-colors"
                    >
                      {wifiState.ssid === n.ssid ? "已连接" : connecting === n.ssid ? "..." : "连接"}
                    </button>
                  </div>
                </div>
              ))}
              {networks.length === 0 && (
                <div className="p-8 text-center text-tesla-gray-500 text-sm">扫描中或无可用网络</div>
              )}
            </div>
          </div>

          {/* Add Network Form */}
          <div className="p-4 rounded-xl bg-tesla-gray-800/50 border border-tesla-gray-800">
            <h3 className="text-sm font-semibold text-tesla-gray-300 mb-3">添加网络</h3>
            <div className="flex gap-2 flex-wrap">
              <input list="scan-list" placeholder="SSID" value={connectSSID}
                onChange={e => setConnectSSID(e.target.value)}
                className="flex-1 min-w-[120px] px-3 py-2 rounded bg-tesla-gray-800 border border-tesla-gray-700 text-sm text-white" />
              <datalist id="scan-list">{networks.map(n => <option key={n.ssid} value={n.ssid} />)}</datalist>
              <input type="password" placeholder="密码" value={connectPass}
                onChange={e => setConnectPass(e.target.value)}
                onKeyDown={e => e.key === "Enter" && handleConnectWithPass()}
                className="flex-1 min-w-[120px] px-3 py-2 rounded bg-tesla-gray-800 border border-tesla-gray-700 text-sm text-white" />
              <button onClick={handleConnectWithPass} disabled={!connectSSID || connecting !== null}
                className="px-4 py-2 rounded-lg bg-tesla-blue text-sm font-medium hover:bg-tesla-blue/80 disabled:opacity-50">
                {connecting ? "连接中..." : "连接"}
              </button>
            </div>
            {error && <p className="text-xs text-red-400 mt-2">{error}</p>}
          </div>

          {/* Saved Networks */}
          {saved.length > 0 && (
            <div className="rounded-xl bg-tesla-gray-800/50 border border-tesla-gray-800 overflow-hidden">
              <div className="px-5 py-3 border-b border-tesla-gray-800">
                <h2 className="text-sm font-semibold text-tesla-gray-300">已保存的网络</h2>
              </div>
              <div className="divide-y divide-tesla-gray-800/50">
                {saved.map((n, i) => (
                  <div key={n.name} className="flex items-center justify-between px-4 py-3">
                    <div className="flex items-center gap-2 flex-1 min-w-0">
                      {/* Reorder buttons */}
                      <div className="flex flex-col gap-0.5 mr-1">
                        <button onClick={async () => {
                          const reorder = [...saved];
                          if (i > 0) { [reorder[i-1], reorder[i]] = [reorder[i], reorder[i-1]]; }
                          await fetch("/api/wifi/reorder", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({names:reorder.map(x=>x.name)})});
                          fetchSaved();
                        }} disabled={i===0} className="text-tesla-gray-600 hover:text-white disabled:opacity-30"><ChevronUp className="w-3 h-3"/></button>
                        <button onClick={async () => {
                          const reorder = [...saved];
                          if (i < saved.length-1) { [reorder[i], reorder[i+1]] = [reorder[i+1], reorder[i]]; }
                          await fetch("/api/wifi/reorder", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({names:reorder.map(x=>x.name)})});
                          fetchSaved();
                        }} disabled={i===saved.length-1} className="text-tesla-gray-600 hover:text-white disabled:opacity-30"><ChevronDown className="w-3 h-3"/></button>
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          {n.active && <span className="w-2 h-2 rounded-full bg-green-500" />}
                          <span className="text-sm font-medium truncate">{n.ssid || n.name}</span>
                        </div>
                        <div className="flex items-center gap-2 text-xs text-tesla-gray-500 mt-0.5">
                          {n.in_range ? (
                            <span className="flex items-center gap-1 text-green-400">
                              <Signal className="w-3 h-3" /> {n.signal}%
                            </span>
                          ) : n.active ? null : <span className="text-tesla-gray-600">不在范围内</span>}
                        </div>
                      </div>
                    </div>
                    <button onClick={() => handleForget(n.name)}
                      className="text-tesla-gray-600 hover:text-red-400 transition-colors p-1 ml-2">
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* === AP Tab === */}
      {tab === "ap" && (
        <div className="space-y-6">
          {/* Status */}
          <div className="p-5 rounded-xl bg-tesla-gray-800/50 border border-tesla-gray-800">
            <h2 className="text-sm font-semibold text-tesla-gray-300 flex items-center gap-2 mb-3">
              <Radio className="w-4 h-4" />热点状态
            </h2>
            <div className="flex items-center gap-4">
              <span className={`w-3 h-3 rounded-full ${apStatus?.active ? "bg-green-500 animate-pulse" : "bg-gray-600"}`} />
              <span className="text-lg font-semibold">
                {apStatus?.active ? "已激活" : "未激活"}
              </span>
              {apStatus?.ssid && <span className="text-tesla-gray-400 text-sm">SSID: {apStatus.ssid}</span>}
            </div>
            <div className="flex gap-2 mt-4">
              {(["auto", "force_on", "force_off"] as const).map((mode) => (
                <button key={mode} onClick={() => handleForceMode(mode)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                    apStatus?.force_mode === mode
                      ? "bg-tesla-blue text-white"
                      : "bg-tesla-gray-700 text-tesla-gray-400 hover:text-white"
                  }`}>
                  {mode === "auto" ? "自动" : mode === "force_on" ? "强制开" : "强制关"}
                </button>
              ))}
            </div>
          </div>

          {/* AP Config */}
          <div className="p-5 rounded-xl bg-tesla-gray-800/50 border border-tesla-gray-800">
            <h2 className="text-sm font-semibold text-tesla-gray-300 mb-4">热点配置</h2>
            <div className="space-y-4">
              <div>
                <label className="block text-xs text-tesla-gray-500 mb-1">SSID (名称)</label>
                <input type="text" value={apSSID} onChange={(e) => setApSSID(e.target.value)}
                  maxLength={32} className="w-full px-3 py-2 rounded-lg bg-tesla-gray-800 border border-tesla-gray-700 text-sm text-white" />
              </div>
              <div>
                <label className="block text-xs text-tesla-gray-500 mb-1">密码 (留空 = 开放网络)</label>
                <input type="text" value={apPass} onChange={(e) => setApPass(e.target.value)}
                  maxLength={63} placeholder="8-63 字符" className="w-full px-3 py-2 rounded-lg bg-tesla-gray-800 border border-tesla-gray-700 text-sm text-white" />
              </div>
              <button onClick={handleApSave} disabled={apSaving}
                className="px-4 py-2 rounded-lg bg-tesla-blue text-sm font-medium hover:bg-tesla-blue/80 disabled:opacity-50">
                {apSaving ? "保存中..." : "保存配置"}
              </button>
            </div>
          </div>

          {/* Info */}
          <div className="p-4 rounded-xl bg-tesla-gray-800/30 border border-tesla-gray-800 text-sm text-tesla-gray-400">
            <p className="flex items-center gap-2"><AlertCircle className="w-4 h-4 text-amber-500" />
              连接到此热点后，打开浏览器访问任何网址都会自动跳转到 TJOS 仪表盘（Captive Portal）。
            </p>
          </div>
        </div>
      )}

      {/* === Advanced Tab === */}
      {tab === "advanced" && <AdvancedTab />}
    </div>
  );
}

function AdvancedTab() {
  const [values, setValues] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    fetch("/api/settings/config").then(r => r.json()).then(d => {
      const flat: Record<string, string> = {};
      if (d.ingestion) flat["ingestion.sample_rate"] = String(d.ingestion.sample_rate);
      if (d.trip) {
        flat["trip.gap_minutes"] = String(d.trip.gap_minutes);
        flat["trip.min_duration_seconds"] = String(d.trip.min_duration_seconds);
        flat["trip.min_distance_km"] = String(d.trip.min_distance_km);
      }
      if (d.events) {
        for (const [k, v] of Object.entries(d.events as Record<string, {enabled: boolean; threshold_ms2: number}>)) {
          flat[`events.${k}.enabled`] = String(v.enabled);
          flat[`events.${k}.threshold_ms2`] = String(v.threshold_ms2);
        }
      }
      setValues(flat);
    }).catch(() => {});
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      const r = await fetch("/api/settings/config", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(values),
      });
      const d = await r.json();
      if (d.success) { setSaved(true); setTimeout(() => setSaved(false), 2000); }
      else alert(d.error || "Save failed");
    } catch (e) { alert("Save error"); }
    finally { setSaving(false); }
  };

  const setVal = (k: string, v: string) => setValues(prev => ({...prev, [k]: v}));

  return (
    <div className="space-y-4">
      <div className="p-5 rounded-xl bg-amber-500/10 border border-amber-500/20">
        <p className="text-sm text-amber-400 flex items-center gap-2">
          <AlertCircle className="w-4 h-4" />
          高级设置影响后台数据处理行为。大多数用户应保持默认值。
        </p>
      </div>
      <AdvInput label="采样率" desc="每秒处理的视频帧数（30 = 每秒1帧）" configKey="ingestion.sample_rate" value={values["ingestion.sample_rate"] || "30"} onChange={setVal} />
      <AdvInput label="行程间隔" desc="超过此时间（分钟）的间隙会拆分行程" configKey="trip.gap_minutes" unit="分钟" value={values["trip.gap_minutes"] || "5"} onChange={setVal} />
      <AdvInput label="最短行程时长" desc="短于此时间的行程将被忽略" configKey="trip.min_duration_seconds" unit="秒" value={values["trip.min_duration_seconds"] || "60"} onChange={setVal} />
      <AdvInput label="紧急制动阈值" desc="纵向加速度低于此值触发紧急制动事件" configKey="events.emergency_brake.threshold_ms2" unit="m/s²" value={values["events.emergency_brake.threshold_ms2"] || "-7.0"} onChange={setVal} />
      <AdvInput label="急刹车阈值" desc="纵向加速度低于此值触发急刹车事件" configKey="events.harsh_brake.threshold_ms2" unit="m/s²" value={values["events.harsh_brake.threshold_ms2"] || "-4.0"} onChange={setVal} />
      <AdvInput label="急加速阈值" desc="纵向加速度超过此值触发急加速事件" configKey="events.hard_acceleration.threshold_ms2" unit="m/s²" value={values["events.hard_acceleration.threshold_ms2"] || "3.5"} onChange={setVal} />
      <button onClick={handleSave} disabled={saving}
        className={`px-6 py-2.5 rounded-lg text-sm font-medium transition-colors ${saved ? "bg-green-600" : "bg-tesla-blue hover:bg-tesla-blue/80"} disabled:opacity-50`}>
        {saving ? "保存中..." : saved ? "已保存 ✓" : "保存设置"}
      </button>
    </div>
  );
}

function AdvInput({ label, desc, configKey, unit, value, onChange }: {
  label: string; desc: string; configKey: string; unit?: string; value: string; onChange: (k: string, v: string) => void;
}) {
  return (
    <div className="p-4 rounded-xl bg-tesla-gray-800/50 border border-tesla-gray-800">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-sm font-medium">{label}</div>
          <div className="text-xs text-tesla-gray-500 mt-0.5">{desc}</div>
        </div>
        <div className="flex items-center gap-2">
          <input type="text" inputMode="decimal" value={value}
            onChange={(e) => onChange(configKey, e.target.value)}
            className="w-20 px-2 py-1 rounded bg-tesla-gray-800 border border-tesla-gray-700 text-sm text-right text-white focus:border-tesla-blue focus:outline-none"
          />
          {unit && <span className="text-xs text-tesla-gray-500 w-10">{unit}</span>}
        </div>
      </div>
    </div>
  );
}

function SignalIndicator({ pct }: { pct: number }) {
  const bars = pct < 20 ? 1 : pct < 45 ? 2 : pct < 70 ? 3 : 4;
  return (
    <div className="flex items-end gap-0.5" style={{ height: 16 }}>
      {[1, 2, 3, 4].map((i) => (
        <div key={i} className="w-1 rounded-sm transition-colors"
          style={{
            height: `${4 + i * 4}px`,
            backgroundColor: i <= bars ? "rgb(62, 106, 225)" : "rgb(68, 68, 68)",
          }}
        />
      ))}
    </div>
  );
}

