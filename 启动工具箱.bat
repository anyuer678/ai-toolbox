@echo off
chcp 65001 >nul
title AI 工具箱
echo.
echo  ==========================================
echo    AI 工具箱 - 启动中...
echo  ==========================================
echo.
echo  启动后浏览器会自动打开仪表盘
echo  点击页面上的按钮即可刷新用量 / 导出聊天记录
echo  按 Ctrl+C 停止服务
echo.
python "%~dp0scripts\server.py"
