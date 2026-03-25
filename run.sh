#!/bin/zsh
# 快速运行 VPN Manager（后台运行，关闭终端不会停止）

cd "$(dirname "$0")"

# 如果已在运行，先提示
if pgrep -f "python3.11 vpn_manager.py" > /dev/null 2>&1; then
    echo "⚠️  VPN Manager 已在运行中 (PID: $(pgrep -f 'python3.11 vpn_manager.py'))"
    echo "如需重启，请先运行: kill $(pgrep -f 'python3.11 vpn_manager.py')"
    exit 1
fi

# 使用 nohup 后台运行，终端关闭后程序不会停止
nohup /opt/homebrew/bin/python3.11 vpn_manager.py > /tmp/vpn-manager.log 2>&1 &
echo "✅ VPN Manager 已在后台启动 (PID: $!)"
echo "📋 日志文件: /tmp/vpn-manager.log"
echo "🛑 停止命令: kill $!"
