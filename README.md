# VPN Manager

macOS 菜单栏 VPN 管理应用，支持多 VPN 连接管理。

## 功能特性

- 🔐 支持多种认证方式：静态密码、OTP 动态密码、双密码认证
- 🚀 一键连接/断开多个 VPN
- 📊 实时连接状态显示
- 🔄 自动重连（仅限静态密码 VPN）
- 🛠 内置工具：DNS 修复、网络检测、公网 IP 查看
- 📝 日志查看

## 快速开始

### 1. 安装依赖

```bash
cd /path/to/vpn-manager-app
pip3 install -r requirements.txt
```

### 2. 配置 VPN

首次运行会自动生成配置文件 `~/.vpn-manager/config.yaml`。之后有三种方式修改配置：

**方式 A：菜单栏编辑（推荐）**

点击菜单栏 → ⚙️ 设置 → 📝 编辑配置文件，在系统文本编辑器中修改，保存后点击「🔄 重新加载配置」即可生效。

**方式 B：快速添加**

点击菜单栏 → ⚙️ 设置 → ➕ 快速添加 VPN，按照弹窗向导依次输入信息即可。

**方式 C：直接编辑 YAML**

```bash
vim ~/.vpn-manager/config.yaml
```

配置文件格式参考 `config.example.yaml`：

```yaml
dns_servers:
  - "8.8.8.8"
  - "114.114.114.114"
network_service: "Wi-Fi"

vpns:
  VPN名称:
    id: vpn-ascii-id
    server: "https://vpn.example.com:443"
    user: "username"
    group: ""                # 认证组名，不需要则留空
    auth_type: otp           # static / otp / two_pass
    password: ""             # static 和 two_pass 需要
    order: ""                # two_pass 时: otp_first / pass_first
    options: ""              # openconnect 额外参数
    totp_secret: ""          # TOTP 密钥，配置后全自动连接
```

### 3. 运行

**前台运行**（关闭终端会停止）：

```bash
/opt/homebrew/bin/python3.11 vpn_manager.py
```

**后台运行**（推荐，关闭终端不会停止）：

```bash
bash run.sh
```

或者手动执行：

```bash
nohup /opt/homebrew/bin/python3.11 vpn_manager.py > /tmp/vpn-manager.log 2>&1 &
disown
```

运行后，菜单栏会出现 🔒 图标。

**查看后台日志**：

```bash
tail -f /tmp/vpn-manager.log
```

**停止后台运行的程序**：

```bash
pkill -f "python3.11 vpn_manager.py"
```

## 打包成 .app

打包后可以双击运行，无需命令行。

```bash
# 安装打包工具
pip3 install py2app

# 打包
python setup.py py2app

# 应用在 dist/ 目录下
open dist/
```

### 移动到应用程序

```bash
mv "dist/VPN Manager.app" /Applications/
```

## 开机自启动

### 方法 1：系统设置（推荐）

1. 打开 **系统设置** → **通用** → **登录项**
2. 点击 **+** 添加 `VPN Manager.app`

### 方法 2：LaunchAgent

创建 `~/Library/LaunchAgents/com.local.vpnmanager.plist`：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.local.vpnmanager</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Applications/VPN Manager.app/Contents/MacOS/VPN Manager</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
```

加载：

```bash
launchctl load ~/Library/LaunchAgents/com.local.vpnmanager.plist
```

## sudo 免密码配置

VPN 连接需要 root 权限。可以配置 sudoers 免密码：

```bash
sudo visudo
```

添加以下内容（将 `your_username` 替换为你的用户名）：

```
your_username ALL=(ALL) NOPASSWD: /usr/local/bin/openconnect, /opt/homebrew/bin/openconnect, /usr/bin/killall, /usr/sbin/networksetup
```

## 认证类型说明

| 类型 | 说明 | 所需配置 |
|------|------|----------|
| `static` | 静态密码 | password |
| `otp` | 动态密码/OTP | 运行时输入 |
| `two_pass` | 双密码（静态+动态） | password + order |

### two_pass 顺序说明

- `pass_first`: 先输入静态密码，再输入动态码
- `otp_first`: 先输入动态码，再输入静态密码

## 依赖

- Python 3.8+
- [rumps](https://github.com/jaredks/rumps) - macOS 菜单栏应用框架
- [pyotp](https://github.com/pyauth/pyotp) - TOTP 动态码生成
- [PyYAML](https://pyyaml.org/) - YAML 配置文件解析
- [openconnect](https://www.infradead.org/openconnect/) - VPN 客户端

安装 openconnect：

```bash
brew install openconnect
```

## 目录结构

```
vpn-manager-app/
├── vpn_manager.py          # 主程序
├── config.example.yaml     # 配置文件模板
├── setup.py                # 打包配置
├── requirements.txt        # 依赖
├── run.sh                  # 快速启动脚本
└── README.md               # 说明文档

~/.vpn-manager/
└── config.yaml             # 实际配置文件（自动生成，含敏感信息）
```

## License

MIT
