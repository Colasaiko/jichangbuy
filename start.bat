@echo off
chcp 65001 >nul
title JichangBuy 购买中心本地服务器
echo ======================================================
echo 正在启动 JichangBuy 本地网站...
echo ======================================================
npm run dev
pause
