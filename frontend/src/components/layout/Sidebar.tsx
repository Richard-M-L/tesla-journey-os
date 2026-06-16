import { useEffect, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import {
  LayoutDashboard,
  Clock,
  AlertTriangle,
  BarChart3,
  Map,
  Car,
  Music,
  Zap,
  Disc,
  Film,
  HardDrive,
  Image,
  FileText,
  Volume2,
  Download,
  Usb,
  Settings,
  ChevronDown,
} from "lucide-react";

const navItems = [
  { to: "/", icon: LayoutDashboard, label: "仪表盘" },
  { to: "/timeline", icon: Clock, label: "时间线" },
  { to: "/videos", icon: Film, label: "视频" },
  { to: "/events", icon: AlertTriangle, label: "事件" },
  { to: "/statistics", icon: BarChart3, label: "统计" },
  { to: "/storage", icon: HardDrive, label: "存储" },
  { to: "/map", icon: Map, label: "地图" },
];

const mediaItems = [
  { to: "/media/chimes", icon: Music, label: "锁车音效" },
  { to: "/media/lightshows", icon: Zap, label: "灯光秀" },
  { to: "/media/music", icon: Disc, label: "音乐" },
  { to: "/media/wraps", icon: Image, label: "车衣" },
  { to: "/media/plates", icon: FileText, label: "车牌" },
  { to: "/media/boombox", icon: Volume2, label: "Boombox" },
];

export function Sidebar() {
  const location = useLocation();
  const [usbMode, setUsbMode] = useState<string>("unknown");
  const [mediaOpen, setMediaOpen] = useState(false);

  useEffect(() => {
    fetch("/api/usb/status")
      .then((r) => r.json())
      .then((d) => setUsbMode(d.mode || "unknown"))
      .catch(() => setUsbMode("unknown"));
  }, []);

  const isMediaActive = mediaItems.some((item) =>
    location.pathname.startsWith(item.to)
  );

  return (
    <aside className="w-56 border-r border-tesla-gray-800 bg-tesla-gray-900 flex flex-col shrink-0">
      {/* Logo */}
      <div className="px-5 py-4 border-b border-tesla-gray-800">
        <div className="flex items-center gap-2.5">
          <Car className="w-6 h-6 text-tesla-red" />
          <div>
            <div className="text-sm font-semibold tracking-tight">Tesla Journey OS</div>
            <div className="text-[10px] text-tesla-gray-400 tracking-widest uppercase">
              Digital Twin
            </div>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        {navItems.map((item) => {
          const isActive =
            item.to === "/"
              ? location.pathname === "/"
              : location.pathname.startsWith(item.to);
          return (
            <NavLink
              key={item.to}
              to={item.to}
              className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                isActive
                  ? "bg-tesla-gray-800 text-white"
                  : "text-tesla-gray-400 hover:text-white hover:bg-tesla-gray-800/50"
              }`}
            >
              <item.icon className="w-4 h-4" />
              {item.label}
            </NavLink>
          );
        })}

        {/* Media section */}
        <div className="pt-2 mt-2 border-t border-tesla-gray-800">
          <button
            onClick={() => setMediaOpen(!mediaOpen)}
            className="flex items-center justify-between w-full px-3 py-2 text-xs uppercase tracking-wider text-tesla-gray-500 hover:text-tesla-gray-300 transition-colors"
          >
            <span>Media</span>
            <ChevronDown
              className={`w-3 h-3 transition-transform ${mediaOpen || isMediaActive ? "rotate-180" : ""}`}
            />
          </button>
          {(mediaOpen || isMediaActive) && (
            <div className="mt-1 space-y-1">
              {mediaItems.map((item) => {
                const isActive = location.pathname.startsWith(item.to);
                return (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                      isActive
                        ? "bg-tesla-gray-800 text-white"
                        : "text-tesla-gray-400 hover:text-white hover:bg-tesla-gray-800/50"
                    }`}
                  >
                    <item.icon className="w-4 h-4" />
                    {item.label}
                  </NavLink>
                );
              })}
            </div>
          )}
        </div>

        {/* Settings section */}
        <div className="pt-2 mt-2 border-t border-tesla-gray-800">
          <button
            onClick={() => {
              const el = document.getElementById("settings-sub");
              if (el) el.classList.toggle("hidden");
            }}
            className="flex items-center justify-between w-full px-3 py-2 text-xs uppercase tracking-wider text-tesla-gray-500 hover:text-tesla-gray-300 transition-colors"
          >
            <div className="flex items-center gap-3">
              <Settings className="w-4 h-4" />
              <span>设置</span>
            </div>
            <ChevronDown className="w-3 h-3" />
          </button>
          <div id="settings-sub" className="mt-1 space-y-1">
            <NavLink
              to="/settings"
              className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                location.pathname === "/settings"
                  ? "bg-tesla-gray-800 text-white"
                  : "text-tesla-gray-400 hover:text-white hover:bg-tesla-gray-800/50"
              }`}
            >WiFi & 高级</NavLink>
            <NavLink
              to="/settings/usb"
              className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                location.pathname === "/settings/usb"
                  ? "bg-tesla-gray-800 text-white"
                  : "text-tesla-gray-400 hover:text-white hover:bg-tesla-gray-800/50"
              }`}
            >USB 设置</NavLink>
            <NavLink
              to="/settings/updates"
              className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                location.pathname === "/settings/updates"
                  ? "bg-tesla-gray-800 text-white"
                  : "text-tesla-gray-400 hover:text-white hover:bg-tesla-gray-800/50"
              }`}
            >
              <Download className="w-4 h-4" />
              系统更新
            </NavLink>
          </div>
        </div>
      </nav>

      {/* Footer: USB mode indicator */}
      <div className="px-5 py-3 border-t border-tesla-gray-800">
        <div className="flex items-center gap-2 text-xs">
          <span
            className={`w-1.5 h-1.5 rounded-full ${
              usbMode === "present"
                ? "bg-green-500"
                : usbMode === "edit"
                ? "bg-blue-400"
                : "bg-gray-600"
            }`}
          />
          <span className="text-tesla-gray-500">
            {usbMode === "present"
              ? "USB Present"
              : usbMode === "edit"
              ? "USB Edit"
              : "USB Offline"}
          </span>
        </div>
      </div>
    </aside>
  );
}
