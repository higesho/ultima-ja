@echo off
rem build u9probe.dll and u9run.exe (x86)
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars32.bat" >nul || exit /b 1
cd /d "%~dp0"
cl /nologo /O2 /W3 /LD /MT /utf-8 u9probe.c /Fe:u9probe.dll /link user32.lib kernel32.lib || exit /b 1
cl /nologo /O2 /W3 /MT /utf-8 u9run.c /Fe:u9run.exe /link kernel32.lib || exit /b 1
echo BUILD OK
