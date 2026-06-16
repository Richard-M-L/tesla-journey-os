# Tesla Journey OS

**树莓派车载固件。插在 Tesla USB 口，模拟 U 盘保存行车记录，同时提供驾驶行为分析和媒体管理 Web 界面。**

只有一个前提：**树莓派插在车的 USB 口上**。没有这个前提，这个项目没有意义。

车往树莓派写行车记录视频 → 树莓派自动解析遥测数据 → 检测行程和驾驶事件 → 生成评分和图表。所有处理在 Pi 上本地完成。

## 为什么不用 GPS

Tesla 在中国及部分地区的车辆无法获取 GPS 遥测。TJOS 从设计上就不依赖 GPS——行程检测用速度、档位、时间戳；距离计算在无 GPS 时自动回退到速度×时间积分；所有界面在 GPS 不可用时优雅降级。

## 硬件要求

- Raspberry Pi Zero 2 W / 3 / 4 / 5
- MicroSD 卡（16GB 起步，建议 64GB+）
- USB 数据线连接 Pi 和 Tesla
- Raspberry Pi OS Bookworm

## 安装

### 方式一：一行命令（全新 Raspberry Pi OS）

在刷好 Raspberry Pi OS Lite 的树莓派上直接运行：

```bash
curl -sSL https://raw.githubusercontent.com/Richard-M-L/tesla-journey-os/master/deploy/install.sh | sudo bash
```

### 方式二：制作镜像（预先装好一切）

在 Linux 机器上运行，生成一个 `.img` 文件，刷入 SD 卡即可直接使用，无需联网安装：

```bash
git clone https://github.com/Richard-M-L/tesla-journey-os.git
cd tesla-journey-os
sudo ./deploy/build_image.sh --size 8G --output tjos.img
```

生成的 `tjos.img` 用 Raspberry Pi Imager 刷入 SD 卡，插上树莓派开机即用。

### 方式三：手动安装

```bash
git clone https://github.com/Richard-M-L/tesla-journey-os.git
cd tesla-journey-os
sudo ./deploy/install.sh
sudo reboot
```

安装程序会：
1. 装系统依赖
2. 启用 USB Gadget 内核驱动（dwc2 peripheral 模式）
3. 创建 Python 虚拟环境并安装依赖
4. 编译 dashcam protobuf
5. 初始化数据库
6. **创建 USB 磁盘镜像**（自动检测 SD 卡容量，交互式选择大小）
7. 配置 Nginx（端口 80，API 代理，Captive Portal）
8. 安装 systemd 服务
9. 构建前端并启动全部服务

### 指定磁盘镜像大小

```bash
sudo ./deploy/install.sh 32 2 16   # TeslaCam 32G, LightShow 2G, Music 16G
sudo ./deploy/install.sh 16 2 0    # 不要 Music 分区
```

不带参数运行会进入交互式模式，自动检测可用空间并显示建议值。

## 重启后

Pi 插到车 USB 口上，车会看到 **3 个驱动器**：

| LUN | 名称 | 权限 | 用途 |
|-----|------|------|------|
| 0 | TeslaCam | 读写 | 车往这里写行车记录视频 |
| 1 | LightShow | 只读 | 车从这里读取灯光秀文件 |
| 2 | Music | 只读 | 车从这里读取音乐/锁车音效 |

视频写入后，Pi 自动提取 SEI 遥测 → 检测行程 → 检测事件。

### Web 界面

Pi 同时提供 WiFi 热点，手机/电脑连接后访问：

| 地址 | 内容 |
|------|------|
| `http://192.168.4.1` | 仪表盘 |
| `http://192.168.4.1/settings` | 设置（WiFi/热点/高级） |
| `http://192.168.4.1/videos` | 视频浏览器（HUD 遥测叠加） |
| `http://192.168.4.1/events` | 驾驶事件列表 |
| `http://192.168.4.1/statistics` | 统计图表 |

WiFi 可用时 Pi 自动连接；WiFi 断开时自动开启热点：**SSID:** `Tesla Journey OS`（默认无密码）。连上后打开任意浏览器自动跳转到仪表盘（Captive Portal）。

## 功能

**核心管道**：SEI 遥测提取（mmap protobuf 解码）→ 行程检测（speed×time，无需 GPS）→ 事件检测（急刹/急加速/急转弯/超速/AP 退出/低电量）→ 驾驶评分（0-100）

**前端**：React SPA，20+ 页面。仪表盘、时间线、视频播放器（实时 HUD：速度/档位/AP/刹车/转向灯）、存储分析、地图（GPS 不可用时隐藏）

**媒体管理**：锁车音效（WAV 验证+排程）、灯光秀（ZIP/FSEQ）、音乐、Boombox、车衣、车牌。一键导出到 U 盘。

**系统保护**：硬件看门狗（死机自动重启）、安全模式（3 次重启/10 分钟→保活降级）、任务协调器（Pi Zero 2 W SDIO 保护）、文件安全守卫

**在线更新**：Web UI → 检查 GitHub → changelog → 一键更新 → 自动重启

## 项目结构

```
├── backend/app/
│   ├── main.py              # FastAPI 入口
│   ├── event_bus.py         # 异步事件总线
│   ├── models/              # 8 个 SQLAlchemy 模型
│   ├── modules/
│   │   ├── ingestion/       # SEI parser + 文件监控
│   │   ├── telemetry/       # 遥测摄入管道
│   │   ├── trip/            # 行程检测引擎
│   │   ├── event/           # 驾驶事件检测
│   │   ├── analytics/       # 统计引擎
│   │   ├── query/           # 读查询
│   │   ├── usb/             # ConfigFS USB Gadget
│   │   ├── media/           # 锁车音效/灯光秀/音乐/车衣/车牌
│   │   ├── watchdog.py      # 硬件看门狗 + 安全模式
│   │   ├── task_coordinator.py  # SDIO 任务协调
│   │   └── ...
│   └── api/routes.py        # 65 个 API 端点
├── frontend/src/            # React + TypeScript + Tailwind
├── deploy/
│   ├── install.sh           # 一键安装
│   ├── present_usb.sh       # USB Gadget: Present 模式
│   ├── edit_usb.sh          # USB Gadget: Edit 模式
│   └── wifi-monitor.sh      # WiFi 监控 + 热点回退
├── tests/                   # pytest
└── config.yaml              # 统一配置
```

## 开发

```bash
# 后端
cd backend && pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 前端（开发时用 Vite dev server，生产用 Nginx 服务 dist/）
cd frontend && npm install && npm run dev

# 测试
pytest tests/ -v
```

## 与 TeslaUSB 的关系

本项目受 [TeslaUSB](https://github.com/cimryan/teslausb) 启发，是其架构思想的延续。核心差异：

| | TeslaUSB | Tesla Journey OS |
|---|---|---|
| 定位 | 行车记录仪管家 | 驾驶行为分析平台 |
| GPS | 必需 | 可选 |
| 前端 | Jinja2 模板 | React SPA |
| 驾驶评分 | 无 | 有 |
| 在线更新 | 无 | 有 |

## License

MIT
