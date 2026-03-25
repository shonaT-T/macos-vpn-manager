#!/bin/zsh
# VPN Manager 安装脚本

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="VPN Manager"

echo "🚀 VPN Manager 安装脚本"
echo "========================"
echo ""

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "❌ 错误: 未找到 python3，请先安装 Python 3"
    exit 1
fi

# 检查 openconnect
if ! command -v openconnect &> /dev/null; then
    echo "⚠️  警告: 未找到 openconnect"
    echo "   请运行: brew install openconnect"
    echo ""
fi

# 安装 Python 依赖
echo "📦 安装 Python 依赖..."
pip3 install -r "$SCRIPT_DIR/requirements.txt"

echo ""
echo "✅ 依赖安装完成！"
echo ""

# 询问是否打包
echo "是否打包成 .app 应用? (y/n)"
read -r answer

if [[ "$answer" == "y" || "$answer" == "Y" ]]; then
    echo ""
    echo "📦 开始打包..."
    cd "$SCRIPT_DIR"
    
    # 清理旧的构建
    rm -rf build dist
    
    # 打包
    python3 setup.py py2app
    
    if [[ -d "dist/$APP_NAME.app" ]]; then
        echo ""
        echo "✅ 打包成功！"
        echo ""
        
        # 询问是否移动到应用程序
        echo "是否移动到 /Applications? (y/n)"
        read -r move_answer
        
        if [[ "$move_answer" == "y" || "$move_answer" == "Y" ]]; then
            # 如果已存在，先删除
            if [[ -d "/Applications/$APP_NAME.app" ]]; then
                rm -rf "/Applications/$APP_NAME.app"
            fi
            
            mv "dist/$APP_NAME.app" /Applications/
            echo "✅ 已移动到 /Applications/$APP_NAME.app"
            echo ""
            echo "🎉 安装完成！"
            echo ""
            echo "启动方式:"
            echo "  1. 在 Launchpad 中找到 VPN Manager"
            echo "  2. 或运行: open '/Applications/$APP_NAME.app'"
            
            # 询问是否立即启动
            echo ""
            echo "是否立即启动? (y/n)"
            read -r start_answer
            
            if [[ "$start_answer" == "y" || "$start_answer" == "Y" ]]; then
                open "/Applications/$APP_NAME.app"
                echo "✅ 已启动！菜单栏应该出现 🔒 图标"
            fi
        else
            echo ""
            echo "应用位置: $SCRIPT_DIR/dist/$APP_NAME.app"
            echo "可以手动拖动到 /Applications 文件夹"
        fi
    else
        echo "❌ 打包失败，请检查错误信息"
        exit 1
    fi
else
    echo ""
    echo "✅ 安装完成！"
    echo ""
    echo "运行方式:"
    echo "  cd $SCRIPT_DIR"
    echo "  python3 vpn_manager.py"
    echo ""
    echo "或者运行:"
    echo "  $SCRIPT_DIR/run.sh"
fi

echo ""
echo "📖 更多信息请查看 README.md"
