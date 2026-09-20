@echo off
chcp 65001 >nul
title 经营分析更新检测服务 v2
cd /d "D:\个人资料\Claude\MD"
echo 正在启动经营分析更新检测服务 v2(127.0.0.1:8765)...
echo 保持本窗口打开,关闭即停止服务。
python "经营分析更新服务_20260920_1625.py"
pause
