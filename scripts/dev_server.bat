@echo off
rem 薄包装：cmd 下直接 scripts\dev_server.bat start|stop|restart|status
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0dev_server.ps1" %1
