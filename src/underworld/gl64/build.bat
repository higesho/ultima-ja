@echo off
rem 64-bit opengl32.dll for dosbox-staging (gl_proxy64.c). Run gen.py and gen_glyphs.py first.
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul
cd /d "%~dp0"
if not exist out mkdir out
ml64 /nologo /c /Fo stubs.obj stubs.asm || exit /b 1
cl /nologo /utf-8 /D_CRT_SECURE_NO_WARNINGS /O2 /LD /MT /W3 gl_proxy64.c stubs.obj /link /DEF:exports.def /OUT:out\opengl32.dll user32.lib kernel32.lib || exit /b 1
del gl_proxy64.obj stubs.obj out\opengl32.exp out\opengl32.lib 2>nul
