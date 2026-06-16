import { useState, useEffect, useCallback } from "react";
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

interface ApplyResult {
  success: boolean;
  steps: string[];
  error: string | null;
  restarted: boolean;
}

export function UpdatePage() {
  const [version, setVersion] = useState<string>("");
  const [commit, setCommit] = useState<CommitInfo | null>(null);
  const [check, setCheck] = useState<UpdateCheck | null>(null);
  const [checking, setChecking] = useState(false);
  const [applying, setApplying] = useState(false);
  const [applyResult, setApplyResult] = useState<ApplyResult | null>(null);
  const [error, setError] = useState("");

  const fetchVersion = useCallback(async () => {
    try {
      const r = await fetch("/api/system/version");
      const d = await r.json();
      setVersion(d.version);
      setCommit(d.commit);
    } catch (e) { console.error(e); }
  }, []);

  const handleCheck = useCallback(async (force = false) => {
    setChecking(true);
    setError("");
    setApplyResult(null);
    try {
      const r = await fetch(`/api/system/updates/check?force=${force}`);
      const d = await r.json();
      setCheck(d);
      if (d.error) setError(d.error);
    } catch (e) {
      setError("Failed to check for updates");
    } finally {
      setChecking(false);
    }
  }, []);

  const handleApply = useCallback(async () => {
    if (!confirm("Apply updates? The backend will restart after pulling the latest code.")) return;
    setApplying(true);
    setError("");
    try {
      const r = await fetch("/api/system/updates/apply", { method: "POST" });
      const d = await r.json();
      setApplyResult(d);
      if (d.success) {
        // Wait for service to restart, then refresh
        setTimeout(() => {
          fetchVersion();
          handleCheck(true);
        }, 5000);
      }
    } catch (e) {
      setError("Update failed — the service may be restarting. Refresh the page in a moment.");
    } finally {
      setApplying(false);
    }
  }, []);

  useEffect(() => {
    fetchVersion();
    handleCheck();
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

              {/* Changelog */}
              <div className="p-4 rounded-lg bg-tesla-gray-800 border border-tesla-gray-700 max-h-64 overflow-y-auto">
                <h3 className="text-xs uppercase tracking-wider text-tesla-gray-500 mb-2">更新内容</h3>
                <div className="space-y-2">
                  {check.new_commits.map((c) => (
                    <div key={c.hash} className="text-sm">
                      <div className="flex items-center gap-2">
                        <ArrowRight className="w-3 h-3 text-tesla-blue" />
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

              {/* Apply button */}
              <button onClick={handleApply} disabled={applying}
                className="flex items-center gap-2 px-6 py-3 rounded-lg text-sm font-bold bg-green-600 hover:bg-green-500 disabled:opacity-50 transition-colors w-full justify-center">
                <Download className="w-4 h-4" />
                {applying ? "更新中... 服务将重启" : "立即更新"}
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-2 text-tesla-gray-400">
              <CheckCircle className="w-5 h-5 text-green-500" />
              <span>已是最新版本 (v{check.current_version})</span>
              {check.checked_at && (
                <span className="text-xs text-tesla-gray-600 ml-1">
                  (检查于 {new Date(check.checked_at * 1000).toLocaleTimeString("zh-CN")})
                </span>
              )}
            </div>
          )
        ) : (
          <div className="text-sm text-tesla-gray-500">点击刷新检查获取最新信息</div>
        )}
      </div>

      {/* Apply Result */}
      {applyResult && (
        <div className={`p-5 rounded-xl border ${
          applyResult.success
            ? "bg-green-500/10 border-green-500/20"
            : "bg-red-500/10 border-red-500/20"
        }`}>
          <h2 className={`text-sm font-semibold mb-3 flex items-center gap-2 ${
            applyResult.success ? "text-green-400" : "text-red-400"
          }`}>
            {applyResult.success ? <CheckCircle className="w-4 h-4" /> : <AlertCircle className="w-4 h-4" />}
            {applyResult.success ? "更新成功" : "更新失败"}
          </h2>
          <div className="space-y-1">
            {applyResult.steps.map((s, i) => (
              <div key={i} className="text-sm text-tesla-gray-400 flex items-center gap-2">
                <span className="text-tesla-gray-600">{i + 1}.</span> {s}
              </div>
            ))}
          </div>
          {applyResult.error && (
            <div className="mt-3 text-sm text-red-400">{applyResult.error}</div>
          )}
          {applyResult.restarted && (
            <div className="mt-3 text-sm text-amber-400 flex items-center gap-2">
              <RefreshCw className="w-3 h-3 animate-spin" />
              服务已重启 — 刷新页面以加载新版本
            </div>
          )}
        </div>
      )}
    </div>
  );
}
