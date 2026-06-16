import { useState, useEffect, useCallback, useRef } from "react";
import { RefreshCw, Download, GitCommit, CheckCircle, AlertCircle, Clock, ArrowRight } from "lucide-react";

interface CommitInfo { hash: string; message: string; date: string; }
interface UpdateCheck {
  update_available: boolean;
  current_version: string;
  current_commit: string;
  current_commit_msg: string;
  current_commit_date: string;
  latest_version: string;
  latest_commit: string;
  new_commits: CommitInfo[];
  changelog: string;
  checked_at: number;
  commit_count: number;
  error: string | null;
}

interface UpdateStatus {
  running: boolean;
  success: boolean;
  step: string;
  error: string | null;
}

export function UpdatePage() {
  const [version, setVersion] = useState<string>("");
  const [commit, setCommit] = useState<CommitInfo | null>(null);
  const [check, setCheck] = useState<UpdateCheck | null>(null);
  const [checking, setChecking] = useState(false);
  const [applying, setApplying] = useState(false);
  const [status, setStatus] = useState<UpdateStatus | null>(null);
  const [error, setError] = useState("");
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchVersion = useCallback(async () => {
    try {
      const r = await fetch("/api/system/version");
      setVersion((await r.json()).version);
      const cr = await fetch("/api/system/version");
      setCommit((await cr.json()).commit);
    } catch { /* ignore */ }
  }, []);

  const handleCheck = useCallback(async (force = false) => {
    setChecking(true);
    setError("");
    try {
      const r = await fetch(`/api/system/updates/check?force=${force}`);
      const d = await r.json();
      setCheck(d);
      if (d.error) setError(d.error);
    } catch {
      setError("检查更新失败，请检查网络连接");
    } finally {
      setChecking(false);
    }
  }, []);

  const handleApply = useCallback(async () => {
    if (!confirm("确定要更新吗？更新过程中服务会重启。")) return;
    setApplying(true);
    setError("");
    setStatus(null);

    try {
      const r = await fetch("/api/system/updates/apply", { method: "POST" });
      const d = await r.json();

      if (!d.started) {
        setError(d.message || "更新启动失败");
        setApplying(false);
        return;
      }

      // Start polling for status
      pollRef.current = setInterval(async () => {
        try {
          const sr = await fetch("/api/system/updates/status");
          const sd: UpdateStatus = await sr.json();
          setStatus(sd);

          if (!sd.running) {
            // Done (success or failure)
            if (pollRef.current) clearInterval(pollRef.current);
            setApplying(false);

            if (sd.success) {
              // Wait for service to come back, then refresh
              let attempts = 0;
              const healthCheck = setInterval(async () => {
                try {
                  const hr = await fetch("/health");
                  if (hr.ok) {
                    clearInterval(healthCheck);
                    await fetchVersion();
                    await handleCheck(true);
                    setStatus({ running: false, success: true, step: "更新完成！页面即将刷新...", error: null });
                    setTimeout(() => window.location.reload(), 2000);
                  }
                } catch { /* still restarting */ }
                attempts++;
                if (attempts > 30) {
                  clearInterval(healthCheck);
                  setStatus({ running: false, success: true, step: "更新完成，请手动刷新页面", error: null });
                }
              }, 2000);
            }
          }
        } catch { /* polling error, ignore */ }
      }, 1500);

    } catch {
      setError("请求失败，服务可能正在重启。请稍后刷新页面。");
      setApplying(false);
    }
  }, []);

  useEffect(() => {
    fetchVersion();
    handleCheck();
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, []);

  return (
    <div className="max-w-4xl space-y-6">
      <h1 className="text-2xl font-bold tracking-tight">系统更新</h1>

      {/* Current Version */}
      <div className="p-5 rounded-xl bg-tesla-gray-800/50 border border-tesla-gray-800">
        <h2 className="text-sm font-semibold text-tesla-gray-300 mb-3 flex items-center gap-2">
          <GitCommit className="w-4 h-4" /> 当前版本
        </h2>
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <span className="text-tesla-gray-500">版本号</span>
            <div className="text-lg font-bold mt-0.5">v{version || "..."}</div>
          </div>
          <div>
            <span className="text-tesla-gray-500">提交</span>
            <div className="font-mono text-sm mt-0.5">{commit?.hash || "..."}</div>
          </div>
          <div className="col-span-2">
            <span className="text-tesla-gray-500">最近提交</span>
            <div className="text-sm mt-0.5 text-tesla-gray-300">
              {commit?.message || "..."}
              {commit?.date && <span className="text-tesla-gray-500 ml-2">{commit.date}</span>}
            </div>
          </div>
        </div>
      </div>

      {/* Check for Updates */}
      <div className="p-5 rounded-xl bg-tesla-gray-800/50 border border-tesla-gray-800">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold text-tesla-gray-300 flex items-center gap-2">
            <RefreshCw className="w-4 h-4" /> 检查更新
          </h2>
          <button onClick={() => handleCheck(true)} disabled={checking}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-tesla-blue hover:bg-tesla-blue/80 disabled:opacity-50 transition-colors">
            <RefreshCw className={`w-4 h-4 ${checking ? "animate-spin" : ""}`} />
            {checking ? "检查中..." : "刷新检查"}
          </button>
        </div>

        {error && (
          <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-red-500/10 border border-red-500/20 text-sm text-red-400 mb-3">
            <AlertCircle className="w-4 h-4" /> {error}
          </div>
        )}

        {check ? (
          check.update_available ? (
            <div className="space-y-4">
              <div className="flex items-center gap-2 text-green-400">
                <Download className="w-5 h-5" />
                <span className="font-semibold">发现 {check.commit_count} 个新提交</span>
              </div>

              <div className="p-4 rounded-lg bg-tesla-gray-800 border border-tesla-gray-700 max-h-64 overflow-y-auto">
                <h3 className="text-xs uppercase tracking-wider text-tesla-gray-500 mb-2">更新内容</h3>
                <div className="space-y-2">
                  {check.new_commits.map((c) => (
                    <div key={c.hash} className="text-sm">
                      <div className="flex items-center gap-2">
                        <ArrowRight className="w-3 h-3 text-tesla-blue shrink-0" />
                        <span className="text-tesla-gray-200">{c.message}</span>
                      </div>
                      <div className="flex items-center gap-3 ml-5 mt-0.5 text-xs text-tesla-gray-500">
                        <span className="font-mono">{c.hash}</span>
                        {c.date && <span className="flex items-center gap-1"><Clock className="w-3 h-3" />{c.date}</span>}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <button onClick={handleApply} disabled={applying}
                className="flex items-center gap-2 px-6 py-3 rounded-lg text-sm font-bold bg-green-600 hover:bg-green-500 disabled:opacity-50 transition-colors w-full justify-center">
                <Download className="w-4 h-4" />
                {applying ? "更新中..." : "立即更新"}
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-2 text-tesla-gray-400">
              <CheckCircle className="w-5 h-5 text-green-500" />
              <span>已是最新版本</span>
              {check.checked_at > 0 && (
                <span className="text-xs text-tesla-gray-600 ml-1">
                  （检查于 {new Date(check.checked_at * 1000).toLocaleTimeString("zh-CN")}）
                </span>
              )}
            </div>
          )
        ) : (
          <div className="text-sm text-tesla-gray-500">点击刷新检查获取最新版本信息</div>
        )}
      </div>

      {/* Update Progress */}
      {applying && status && (
        <div className="p-5 rounded-xl bg-blue-500/10 border border-blue-500/20">
          <h2 className="text-sm font-semibold text-blue-400 mb-3 flex items-center gap-2">
            <RefreshCw className="w-4 h-4 animate-spin" />
            {status.running ? "正在更新..." : status.success ? "更新成功" : "更新完成"}
          </h2>
          <div className="flex items-center gap-3">
            {status.running && <div className="w-4 h-4 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />}
            {!status.running && status.success && <CheckCircle className="w-4 h-4 text-green-400" />}
            {!status.running && !status.success && <AlertCircle className="w-4 h-4 text-red-400" />}
            <span className="text-sm text-tesla-gray-300">{status.step}</span>
          </div>
          {status.error && (
            <div className="mt-2 text-sm text-red-400">{status.error}</div>
          )}
        </div>
      )}
    </div>
  );
}
