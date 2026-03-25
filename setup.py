"""
macOS VPN Manager 打包配置

使用方法：
    python setup.py py2app

打包后的应用在 dist/ 目录下
"""

from setuptools import setup

APP = ["vpn_manager.py"]
DATA_FILES = ["config.example.yaml"]
OPTIONS = {
    "argv_emulation": False,
    "iconfile": None,  # 可以指定 .icns 图标文件路径
    "plist": {
        "CFBundleName": "macOS VPN Manager",
        "CFBundleDisplayName": "macOS VPN Manager",
        "CFBundleIdentifier": "com.local.vpnmanager",
        "CFBundleVersion": "1.0.0",
        "CFBundleShortVersionString": "1.0.0",
        "LSUIElement": True,  # 重要！不显示 Dock 图标，只显示菜单栏
        "NSHighResolutionCapable": True,
    },
    "packages": ["rumps", "yaml"],
}

setup(
    name="macOS VPN Manager",
    app=APP,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
