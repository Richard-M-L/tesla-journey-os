import { useState, useEffect, useCallback } from "react";
import { Usb, HardDrive, Power, RefreshCw, AlertCircle, CheckCircle, XCircle } from "lucide-react";

interface LunInfo {
  index: number;
  name: string;
  readonly: boolean;
  image_exists: boolean;
  image_size_mb: number;
}

interface UsbStatus {
  supported: boolean;
  mode: string;
  active: boolean;
  udc_available: boolean;
  udc_device: string | null;
  luns: LunInfo[];
}

export function UsbSettingsPage() {
  const [status, setStatus] = useState<UsbStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch("/api/usb/status");
      setStatus(await res.json());
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchStatus(); }, [fetchStatus]);

  const setMode = async (mode: "present" | "edit") => {
    setActionLoading(true);
    try {
      const res = await fetch(`/api/usb/mode/${mode}`, { method: "POST" });
      const data = await res.json();
      if (data.success) await fetchStatus();
      else alert(data.error || "Failed to switch mode");
    } catch (e) {
      alert("Mode switch error");
    } finally {
      setActionLoading(false);
    }
  };

  const runSetup = async () => {
    setActionLoading(true);
    try {
      const res = await fetch("/api/usb/setup", { method: "POST" });
      const data = await res.json();
      if (data.success) await fetchStatus();
      else alert(data.error || "Setup failed");
    } catch (e) {
      alert("Setup error");
    } finally {
      setActionLoading(false);
    }
  };

  return (
    <div className="max-w-4xl space-y-6">
      <h1 className="text-2xl font-bold tracking-tight">USB 设置</h1>

      {loading ? (
        <div className="animate-pulse text-tesla-gray-400">加载中...</div>
      ) : !status?.supported ? (
        <div className="p-8 rounded-xl bg-tesla-gray-800/50 border border-tesla-gray-800 text-center">
          <AlertCircle className="w-12 h-12 mx-auto mb-3 text-amber-500" />
          <p className="text-lg text-tesla-gray-300">USB Gadget 不可用</p>
          <p className="text-sm text-tesla-gray-500 mt-1 max-w-md mx-auto">
            此功能需要 Linux 系统 + ConfigFS + UDC 硬件支持。
            <br />
            在树莓派上运行 TJOS 以启用 USB 设备模拟。
          </p>
        </div>
      ) : (
        <>
          {/* Status Card */}
          <div className="p-5 rounded-xl bg-tesla-gray-800/50 border border-tesla-gray-800">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-tesla-gray-300 flex items-center gap-2">
                <Usb className="w-4 h-4" />
                状态
              </h2>
              <div className="flex items-center gap-2">
                <span className={`w-2 h-2 rounded-full ${status.active ? "bg-green-500 animate-pulse" : "bg-gray-600"}`} />
                <span className="text-sm font-medium">
                  {status.mode === "present" ? "Present (车可访问)" :
                   status.mode === "edit" ? "Edit (Pi 可修改)" :
                   "Unknown"}
                </span>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3 text-sm">
              <div className="flex items-center gap-2 text-tesla-gray-400">
                UDC: {status.udc_available ? (
                  <span className="text-green-400 flex items-center gap-1">
                    <CheckCircle className="w-3 h-3" /> {status.udc_device}
                  </span>
                ) : (
                  <span className="text-red-400 flex items-center gap-1">
                    <XCircle className="w-3 h-3" /> 不可用
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* LUNs */}
          <div className="p-5 rounded-xl bg-tesla-gray-800/50 border border-tesla-gray-800">
            <h2 className="text-sm font-semibold text-tesla-gray-300 mb-3 flex items-center gap-2">
              <HardDrive className="w-4 h-4" />
              磁盘镜像
            </h2>
            <div className="space-y-2">
              {status.luns.map((lun) => (
                <div key={lun.index} className="flex items-center justify-between px-4 py-3 rounded-lg bg-tesla-gray-800/50 border border-tesla-gray-800">
                  <div className="flex items-center gap-3">
                    <HardDrive className={`w-4 h-4 ${lun.image_exists ? "text-tesla-blue" : "text-tesla-gray-600"}`} />
                    <div>
                      <span className="text-sm font-medium">LUN {lun.index}: {lun.name}</span>
                      <span className="text-xs text-tesla-gray-500 ml-2">
                        {lun.readonly ? "Read-Only" : "Read-Write"}
                      </span>
                    </div>
                  </div>
                  <div className="text-sm">
                    {lun.image_exists ? (
                      <span className="text-green-400">{lun.image_size_mb.toFixed(0)} MB</span>
                    ) : (
                      <span className="text-tesla-gray-600">未创建</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Actions */}
          <div className="flex items-center gap-3">
            <button
              onClick={() => setMode("present")}
              disabled={actionLoading || status.mode === "present"}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-green-600 hover:bg-green-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              <Power className="w-4 h-4" />
              Present (连接车)
            </button>
            <button
              onClick={() => setMode("edit")}
              disabled={actionLoading || status.mode === "edit"}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              <RefreshCw className="w-4 h-4" />
              Edit (修改文件)
            </button>
            <button
              onClick={runSetup}
              disabled={actionLoading}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-tesla-gray-700 hover:bg-tesla-gray-600 disabled:opacity-50 transition-colors"
            >
              Setup
            </button>
          </div>
        </>
      )}
    </div>
  );
}
