@echo off
rem opengl32.dll（代わり）を組み立てる。gen.py が作る。
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars32.bat" >nul
cd /d "%~dp0"
if not exist out mkdir out
cl /nologo /utf-8 /D_CRT_SECURE_NO_WARNINGS /O2 /LD /MT /W3 gl_proxy.c /link /OUT:out\opengl32.dll user32.lib gdi32.lib kernel32.lib || exit /b 1
del gl_proxy.obj gl_proxy.exp gl_proxy.lib out\opengl32.exp out\opengl32.lib 2>nul
