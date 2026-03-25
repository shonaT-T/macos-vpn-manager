#!/usr/bin/env python3.11
"""
VPN Manager - macOS 菜单栏应用
功能：多 VPN 管理、自动重连、状态监控、全自动 OTP 认证

配置文件：~/.vpn-manager/config.yaml
首次运行会自动生成默认配置，之后通过菜单栏「编辑配置文件」修改。

依赖：
    pip3 install rumps pyotp pyyaml
"""

import rumps
import subprocess
import threading
import time
from pathlib import Path

import yaml

try:
    import pyotp
    PYOTP_AVAILABLE = True
except ImportError:
    PYOTP_AVAILABLE = False
    print("⚠️  pyotp 未安装，自动 OTP 功能不可用。运行: pip3 install pyotp")

# 配置文件目录
CONFIG_DIR = Path.home() / ".vpn-manager"
CONFIG_FILE = CONFIG_DIR / "config.yaml"

# 运行时目录
PID_DIR = Path("/tmp/vpn-pids")
LOG_DIR = Path("/tmp/vpn-logs")

# 首次运行时写入的默认配置（迁移自原先硬编码的值）
_DEFAULT_CONFIG = {
    "dns_servers": ["8.8.8.8", "114.114.114.114"],
    "network_service": "Wi-Fi",
    "vpns": {
        "示例VPN": {
            "id": "example",
            "server": "https://vpn.example.com:443",
            "user": "your_username",
            "group": "",
            "auth_type": "otp",
            "password": "",
            "order": "",
            "options": "",
            "totp_secret": "",
        },
    },
}

_YAML_HEADER = """\
# ============================================
# VPN Manager 配置文件
# ============================================
# 修改后在菜单栏点击「重新加载配置」即可生效，无需重启
#
# VPN 参数说明：
#   id          : ASCII 标识符，用于 PID/日志文件名
#   server      : 服务器地址 https://host:port
#   user        : 用户名
#   group       : 认证组名，不需要则留空
#   auth_type   : static(静态密码) / otp(动态密码) / two_pass(双密码)
#   password    : 静态密码（static/two_pass 时填写）
#   order       : 双密码顺序（仅 two_pass）: otp_first / pass_first
#   options     : openconnect 额外参数，如 --servercert pin-sha256:XXXX
#   totp_secret : TOTP 密钥（Base32），配置后全自动连接
# ============================================

"""


def load_config(path: Path = None) -> dict:
    """从 YAML 文件加载配置，返回解析后的 dict"""
    path = path or CONFIG_FILE
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data


def save_config(data: dict, path: Path = None):
    """将配置 dict 写回 YAML 文件（带注释头部）"""
    path = path or CONFIG_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    yaml_body = yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)
    with open(path, "w", encoding="utf-8") as f:
        f.write(_YAML_HEADER)
        f.write(yaml_body)


def init_config():
    """首次运行时生成默认配置文件，返回加载后的配置"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        save_config(_DEFAULT_CONFIG)
        print(f"✅ 已生成默认配置文件: {CONFIG_FILE}")
    return load_config()


def apply_config(data: dict):
    """将配置 dict 应用到全局变量"""
    global VPN_CONFIGS, DNS_SERVERS, NETWORK_SERVICE
    VPN_CONFIGS = data.get("vpns", {})
    DNS_SERVERS = data.get("dns_servers", ["8.8.8.8", "114.114.114.114"])
    NETWORK_SERVICE = data.get("network_service", "Wi-Fi")


# 启动时加载配置
_config_data = init_config()
apply_config(_config_data)

# 确保目录存在
PID_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)


def get_vpn_id(name: str) -> str:
    """获取 VPN 的 ASCII ID（用于文件名）"""
    config = VPN_CONFIGS.get(name, {})
    return config.get("id", name)


def generate_otp(secret: str) -> str:
    """
    生成 TOTP 动态验证码
    
    Args:
        secret: TOTP 密钥（Base32 编码）
    
    Returns:
        6 位动态码，如果生成失败返回 None
    """
    if not secret or not PYOTP_AVAILABLE:
        return None
    try:
        totp = pyotp.TOTP(secret)
        return totp.now()
    except Exception as e:
        print(f"⚠️  OTP 生成失败: {e}")
        return None


class VPNManagerApp(rumps.App):
    """VPN 管理器菜单栏应用"""

    def __init__(self):
        super().__init__(
            name="VPN Manager",
            icon=None,
            title="🔒",
            quit_button=None,
        )

        # 自动重连设置
        self.auto_reconnect = False
        self.reconnect_interval = 30  # 秒
        
        # UI 更新标志（用于线程安全）
        self._needs_refresh = False

        # 构建菜单
        self.build_menu()
        
        # 启动定时器（主线程安全）
        self._setup_timer()

    def build_menu(self):
        """构建菜单"""
        self.menu.clear()

        # 状态标题
        connected_count = sum(1 for name in VPN_CONFIGS if self.is_connected(name))
        total_count = len(VPN_CONFIGS)
        status_text = f"已连接: {connected_count}/{total_count}"
        self.menu.add(rumps.MenuItem(status_text, callback=None))
        self.menu.add(rumps.separator)

        # VPN 列表
        for name, config in VPN_CONFIGS.items():
            is_conn = self.is_connected(name)
            icon = "🟢" if is_conn else "⚪"
            
            # 认证类型图标
            auth_type = config.get("auth_type", "static")
            totp_secret = config.get("totp_secret", "")
            
            # 如果配置了 totp_secret，显示自动化图标
            if auth_type in ("otp", "two_pass") and totp_secret:
                auth_icon = "⚡"  # 全自动
            else:
                auth_icon = {"static": "🔑", "otp": "📱", "two_pass": "🔐"}.get(auth_type, "🔑")

            # 创建子菜单
            vpn_menu = rumps.MenuItem(f"{icon} {auth_icon} {name}")

            if is_conn:
                vpn_menu.add(
                    rumps.MenuItem(
                        "断开连接", callback=lambda s, n=name: self.disconnect_vpn(n)
                    )
                )
                vpn_menu.add(
                    rumps.MenuItem(
                        "查看日志", callback=lambda s, n=name: self.view_log(n)
                    )
                )
            else:
                vpn_menu.add(
                    rumps.MenuItem(
                        "连接", callback=lambda s, n=name: self.connect_vpn(n)
                    )
                )

            self.menu.add(vpn_menu)

        self.menu.add(rumps.separator)

        # 快捷操作
        self.menu.add(rumps.MenuItem("🚀 连接全部", callback=self.connect_all))
        self.menu.add(rumps.MenuItem("🔌 断开全部", callback=self.disconnect_all))

        self.menu.add(rumps.separator)

        # 工具菜单
        tools_menu = rumps.MenuItem("🛠 工具")
        tools_menu.add(rumps.MenuItem("修复 DNS", callback=self.fix_dns))
        tools_menu.add(rumps.MenuItem("检测网络", callback=self.check_network))
        tools_menu.add(rumps.MenuItem("查看公网 IP", callback=self.show_public_ip))
        self.menu.add(tools_menu)

        # 设置菜单
        settings_menu = rumps.MenuItem("⚙️ 设置")

        auto_reconnect_item = rumps.MenuItem(
            f"{'✓ ' if self.auto_reconnect else ''}自动重连",
            callback=self.toggle_auto_reconnect,
        )
        settings_menu.add(auto_reconnect_item)
        settings_menu.add(rumps.separator)
        settings_menu.add(
            rumps.MenuItem("📝 编辑配置文件", callback=self.open_config_editor)
        )
        settings_menu.add(
            rumps.MenuItem("🔄 重新加载配置", callback=self.reload_config)
        )
        settings_menu.add(
            rumps.MenuItem("➕ 快速添加 VPN", callback=self.quick_add_vpn)
        )
        settings_menu.add(rumps.separator)
        settings_menu.add(
            rumps.MenuItem("打开日志目录", callback=self.open_log_dir)
        )
        self.menu.add(settings_menu)

        self.menu.add(rumps.separator)
        self.menu.add(rumps.MenuItem("🔄 刷新", callback=self.refresh))
        self.menu.add(rumps.MenuItem("退出", callback=self.quit_app))

        # 更新图标
        self.update_icon()

    def is_connected(self, name: str) -> bool:
        """检查 VPN 是否已连接（通过检测 openconnect 进程）"""
        config = VPN_CONFIGS.get(name, {})
        server = config.get("server", "")
        if not server:
            return False
        
        # 从服务器地址提取主机名用于匹配进程
        server_host = server.replace("https://", "").replace("http://", "").split(":")[0]
        
        try:
            # 直接检测 openconnect 进程是否在运行
            result = subprocess.run(
                ["pgrep", "-f", f"openconnect.*{server_host}"],
                capture_output=True, text=True
            )
            return result.returncode == 0 and result.stdout.strip() != ""
        except Exception:
            return False

    def connect_vpn(self, name: str, silent: bool = False):
        """
        连接指定 VPN
        
        Args:
            name: VPN 名称
            silent: 静默模式（用于自动重连，不弹窗）
        """
        config = VPN_CONFIGS.get(name)
        if not config:
            if not silent:
                rumps.notification("VPN Manager", "错误", f"未找到配置: {name}")
            return

        if self.is_connected(name):
            if not silent:
                rumps.notification("VPN Manager", name, "已经连接")
            return

        auth_type = config.get("auth_type", "static")
        otp = None

        # 需要 OTP 的情况
        if auth_type in ("otp", "two_pass"):
            totp_secret = config.get("totp_secret", "")
            
            if totp_secret:
                # ✨ 自动生成 OTP（全自动模式）
                otp = generate_otp(totp_secret)
                if otp:
                    if not silent:
                        rumps.notification("VPN Manager", f"🔐 {name}", f"已自动生成动态码")
                else:
                    if not silent:
                        rumps.notification("VPN Manager", "错误", "自动生成动态码失败")
                    return
            else:
                # 没有配置 TOTP 密钥，需要手动输入
                if silent:
                    # 静默模式下跳过需要手动输入的 VPN
                    return
                    
                response = rumps.Window(
                    message=f"请输入 {name} 的动态密码:\n\n💡 提示：配置 totp_secret 可实现全自动连接",
                    title="VPN 认证",
                    default_text="",
                    ok="连接",
                    cancel="取消",
                    dimensions=(200, 24),
                ).run()

                if not response.clicked:
                    return

                otp = response.text.strip()
                if not otp:
                    rumps.notification("VPN Manager", "错误", "动态密码不能为空")
                    return

        # 在后台线程中连接
        thread = threading.Thread(
            target=self._do_connect, args=(name, config, otp, silent), daemon=True
        )
        thread.start()

    def _do_connect(self, name: str, config: dict, otp: str = None, silent: bool = False):
        """
        执行连接（在后台线程中）
        
        Args:
            name: VPN 名称
            config: VPN 配置
            otp: OTP 动态码
            silent: 静默模式
        """
        try:
            # 构建命令
            vpn_id = get_vpn_id(name)
            cmd = [
                "openconnect",
                "--background",
                f"--pid-file={PID_DIR}/{vpn_id}.pid",
                f"--user={config['user']}",
            ]

            if config.get("group"):
                cmd.append(f"--authgroup={config['group']}")

            if config.get("options"):
                cmd.extend(config["options"].split())

            cmd.extend(["--passwd-on-stdin", config["server"]])

            # 构建密码输入
            auth_type = config.get("auth_type", "static")
            password_input = ""

            if auth_type == "static":
                password_input = config.get("password", "")
            elif auth_type == "otp":
                password_input = otp or ""
            elif auth_type == "two_pass":
                order = config.get("order", "pass_first")
                static_pass = config.get("password", "")
                if order == "otp_first":
                    password_input = f"{otp}\n{static_pass}"
                else:
                    password_input = f"{static_pass}\n{otp}"

            # 执行连接
            log_file = LOG_DIR / f"{vpn_id}.log"
            pid_file = PID_DIR / f"{vpn_id}.pid"

            with open(log_file, "w") as log:
                proc = subprocess.Popen(
                    ["sudo", "-S"] + cmd,
                    stdin=subprocess.PIPE,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )
                proc.communicate(input=password_input.encode(), timeout=30)

            # 等待连接建立
            time.sleep(3)

            # 手动获取 PID（因为 openconnect --pid-file 可能不工作）
            server_host = config["server"].replace("https://", "").split(":")[0]
            try:
                result = subprocess.run(
                    ["pgrep", "-f", f"openconnect.*{server_host}"],
                    capture_output=True, text=True
                )
                if result.returncode == 0 and result.stdout.strip():
                    pid = result.stdout.strip().split()[0]
                    pid_file.write_text(pid)
            except Exception:
                pass

            # 检查结果并发送通知（通知是线程安全的）
            if self.is_connected(name):
                if not silent:
                    rumps.notification("VPN Manager", f"✅ {name}", "连接成功")
            else:
                if not silent:
                    rumps.notification(
                        "VPN Manager", f"❌ {name}", "连接失败，请查看日志"
                    )

            # 标记需要刷新菜单（由主线程定时器处理）
            self._needs_refresh = True

        except subprocess.TimeoutExpired:
            if not silent:
                rumps.notification("VPN Manager", f"❌ {name}", "连接超时")
            self._needs_refresh = True
        except Exception as e:
            if not silent:
                rumps.notification("VPN Manager", "错误", str(e))
            self._needs_refresh = True

    def disconnect_vpn(self, name: str):
        """断开指定 VPN"""
        config = VPN_CONFIGS.get(name, {})
        server = config.get("server", "")
        
        if not self.is_connected(name):
            rumps.notification("VPN Manager", name, "未连接")
            return

        try:
            # 从服务器地址提取主机名
            server_host = server.replace("https://", "").replace("http://", "").split(":")[0]
            
            # 获取进程 PID 并终止
            result = subprocess.run(
                ["pgrep", "-f", f"openconnect.*{server_host}"],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                pids = result.stdout.strip().split()
                for pid in pids:
                    subprocess.run(["sudo", "kill", pid], capture_output=True)
            
            rumps.notification("VPN Manager", f"🔌 {name}", "已断开")
        except Exception as e:
            rumps.notification("VPN Manager", "错误", str(e))

        self._needs_refresh = True

    def connect_all(self, _):
        """连接所有 VPN（按顺序，因为需要输入 OTP）"""
        for name in VPN_CONFIGS:
            if not self.is_connected(name):
                self.connect_vpn(name)

    def disconnect_all(self, _):
        """断开所有 VPN"""
        subprocess.run(["sudo", "killall", "openconnect"], capture_output=True)

        for f in PID_DIR.glob("*.pid"):
            f.unlink(missing_ok=True)

        rumps.notification("VPN Manager", "全部断开", "所有 VPN 已断开")
        self.build_menu()

    def fix_dns(self, _):
        """修复 DNS"""
        try:
            subprocess.run(
                ["sudo", "networksetup", "-setdnsservers", NETWORK_SERVICE]
                + DNS_SERVERS,
                capture_output=True,
                check=True,
            )
            rumps.notification("VPN Manager", "DNS 已修复", ", ".join(DNS_SERVERS))
        except Exception as e:
            rumps.notification("VPN Manager", "错误", str(e))

    def check_network(self, _):
        """检测网络连通性"""
        tests = [
            ("8.8.8.8", "Google DNS"),
            ("114.114.114.114", "114 DNS"),
            ("baidu.com", "百度"),
        ]

        results = []
        for host, name in tests:
            result = subprocess.run(
                ["ping", "-c", "1", "-W", "2", host],
                capture_output=True,
            )
            status = "✓" if result.returncode == 0 else "✗"
            results.append(f"{status} {name}")

        rumps.notification("网络检测", "结果", "\n".join(results))

    def show_public_ip(self, _):
        """显示公网 IP"""
        try:
            result = subprocess.run(
                ["curl", "-s", "--max-time", "5", "https://api.ipify.org"],
                capture_output=True,
                text=True,
            )
            ip = result.stdout.strip()
            if ip:
                rumps.notification("公网 IP", ip, "已复制到剪贴板")
                subprocess.run(["pbcopy"], input=ip.encode(), check=True)
            else:
                rumps.notification("VPN Manager", "错误", "无法获取公网 IP")
        except Exception as e:
            rumps.notification("VPN Manager", "错误", str(e))

    def view_log(self, name: str):
        """查看日志"""
        vpn_id = get_vpn_id(name)
        log_file = LOG_DIR / f"{vpn_id}.log"
        if log_file.exists():
            subprocess.run(["open", "-a", "Console", str(log_file)])
        else:
            rumps.notification("VPN Manager", name, "日志文件不存在")

    def toggle_auto_reconnect(self, _):
        """切换自动重连"""
        self.auto_reconnect = not self.auto_reconnect
        status = "已开启" if self.auto_reconnect else "已关闭"
        rumps.notification("VPN Manager", "自动重连", status)
        self.build_menu()

    def open_log_dir(self, _):
        """打开日志目录"""
        subprocess.run(["open", str(LOG_DIR)])

    def refresh(self, _):
        """刷新状态"""
        self.build_menu()

    def update_icon(self):
        """更新菜单栏图标"""
        connected = any(self.is_connected(name) for name in VPN_CONFIGS)
        self.title = "🔐" if connected else "🔒"

    def _setup_timer(self):
        """设置定时器（在主线程中运行，线程安全）"""
        # 使用 rumps.Timer 确保回调在主线程执行
        self._timer = rumps.Timer(self._on_timer, 5)  # 每 5 秒检查一次
        self._timer.start()
    
    def _on_timer(self, _):
        """定时器回调（主线程中执行，线程安全）"""
        # 检查是否需要刷新菜单
        if self._needs_refresh:
            self._needs_refresh = False
            self.build_menu()
        
        # 更新图标
        self.update_icon()
        
        # 自动重连检查
        if self.auto_reconnect:
            for name, config in VPN_CONFIGS.items():
                if not self.is_connected(name):
                    auth_type = config.get("auth_type", "static")
                    totp_secret = config.get("totp_secret", "")
                    
                    # 可以自动重连的情况：
                    # 1. 静态密码类型
                    # 2. 配置了 totp_secret 的 OTP/two_pass 类型
                    can_auto_reconnect = (
                        auth_type == "static" or
                        (auth_type in ("otp", "two_pass") and totp_secret)
                    )
                    
                    if can_auto_reconnect:
                        self.connect_vpn(name, silent=True)

    def open_config_editor(self, _):
        """用系统文本编辑器打开配置文件"""
        if not CONFIG_FILE.exists():
            init_config()
        subprocess.run(["open", "-e", str(CONFIG_FILE)])

    def reload_config(self, _):
        """热重载配置文件并刷新菜单"""
        try:
            data = load_config()
            apply_config(data)
            self.build_menu()
            rumps.notification("VPN Manager", "配置已重新加载",
                              f"共 {len(VPN_CONFIGS)} 个 VPN")
        except Exception as e:
            rumps.notification("VPN Manager", "配置加载失败", str(e))

    def quick_add_vpn(self, _):
        """多步弹窗向导：快速添加一个 VPN 配置"""
        # Step 1: 名称
        resp = rumps.Window(
            message="请输入 VPN 显示名称（如：公司VPN）",
            title="添加 VPN - 1/5 名称",
            default_text="",
            ok="下一步",
            cancel="取消",
            dimensions=(260, 24),
        ).run()
        if not resp.clicked:
            return
        vpn_name = resp.text.strip()
        if not vpn_name:
            rumps.notification("VPN Manager", "错误", "名称不能为空")
            return
        if vpn_name in VPN_CONFIGS:
            rumps.notification("VPN Manager", "错误", f"「{vpn_name}」已存在")
            return

        # Step 2: 服务器地址
        resp = rumps.Window(
            message="请输入服务器地址\n格式：https://host:port",
            title="添加 VPN - 2/5 服务器",
            default_text="https://",
            ok="下一步",
            cancel="取消",
            dimensions=(300, 24),
        ).run()
        if not resp.clicked:
            return
        server = resp.text.strip()
        if not server:
            rumps.notification("VPN Manager", "错误", "服务器地址不能为空")
            return

        # Step 3: 用户名
        resp = rumps.Window(
            message="请输入登录用户名",
            title="添加 VPN - 3/5 用户名",
            default_text="",
            ok="下一步",
            cancel="取消",
            dimensions=(200, 24),
        ).run()
        if not resp.clicked:
            return
        user = resp.text.strip()

        # Step 4: 认证类型
        resp = rumps.Window(
            message="请输入认证类型：\n"
                    "  static   - 仅静态密码\n"
                    "  otp      - 仅动态密码\n"
                    "  two_pass - 静态密码 + 动态码",
            title="添加 VPN - 4/5 认证",
            default_text="otp",
            ok="下一步",
            cancel="取消",
            dimensions=(200, 24),
        ).run()
        if not resp.clicked:
            return
        auth_type = resp.text.strip()
        if auth_type not in ("static", "otp", "two_pass"):
            auth_type = "otp"

        # Step 5: TOTP 密钥（可选）
        resp = rumps.Window(
            message="请输入 TOTP 密钥（Base32 编码）\n"
                    "配置后可全自动连接，留空则每次手动输入动态码",
            title="添加 VPN - 5/5 TOTP 密钥（可选）",
            default_text="",
            ok="完成",
            cancel="取消",
            dimensions=(300, 24),
        ).run()
        if not resp.clicked:
            return
        totp_secret = resp.text.strip()

        vpn_id = vpn_name.encode("ascii", errors="ignore").decode() or vpn_name
        vpn_id = vpn_id.lower().replace(" ", "_")

        new_vpn = {
            "id": vpn_id,
            "server": server,
            "user": user,
            "group": "",
            "auth_type": auth_type,
            "password": "",
            "order": "",
            "options": "",
            "totp_secret": totp_secret,
        }

        try:
            data = load_config()
            if "vpns" not in data:
                data["vpns"] = {}
            data["vpns"][vpn_name] = new_vpn
            save_config(data)
            apply_config(data)
            self.build_menu()
            rumps.notification("VPN Manager", f"✅ 已添加「{vpn_name}」",
                              "配置已保存到文件")
        except Exception as e:
            rumps.notification("VPN Manager", "保存失败", str(e))

    def quit_app(self, _):
        """退出应用"""
        rumps.quit_application()


if __name__ == "__main__":
    VPNManagerApp().run()
