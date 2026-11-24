@echo off
rem opengl32.dll（gl_proxy.c）を、32 ビットと 64 ビットの DOSBox 用に作る
rem   アンダーワールド  : out32\opengl32.dll と out64\opengl32.dll
rem   アンダーワールドII: out32_uw2\opengl32.dll と out64_uw2\opengl32.dll
rem   2 作の違いはバージョン情報（ver\<作品>.rc）だけ。試験用のコードはないので、配布版だけを作る
cd /d "%~dp0"
python -I gen_fwd.py . glTexImage2D:36,glTexSubImage2D:36,glNewList:8,glEndList:0,glTexCoord2f:8,glDrawArrays:12,wglGetProcAddress:4 || exit /b 1
call :pair underworld out32 out64 || exit /b 1
call :pair underworld2 out32_uw2 out64_uw2 || exit /b 1
echo ok
exit /b 0

:pair
if not exist %2 mkdir %2
if not exist %3 mkdir %3
if not exist obj\%1\32 mkdir obj\%1\32
if not exist obj\%1\64 mkdir obj\%1\64
setlocal
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars32.bat" >nul
rc /nologo /fo obj\%1\32\ver.res ver\%1.rc || exit /b 1
cl /nologo /utf-8 /D_CRT_SECURE_NO_WARNINGS /O2 /LD /MT /W3 /Foobj\%1\32\ gl_proxy.c obj\%1\32\ver.res /link /OUT:%2\opengl32.dll /IMPLIB:obj\%1\32\opengl32.lib user32.lib kernel32.lib || exit /b 1
endlocal
setlocal
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul
ml64 /nologo /c /Foobj\%1\64\fwd64.obj fwd64.asm || exit /b 1
rc /nologo /fo obj\%1\64\ver.res ver\%1.rc || exit /b 1
cl /nologo /utf-8 /D_CRT_SECURE_NO_WARNINGS /O2 /LD /MT /W3 /Foobj\%1\64\ gl_proxy.c obj\%1\64\fwd64.obj obj\%1\64\ver.res /link /DEF:fwd64.def /OUT:%3\opengl32.dll /IMPLIB:obj\%1\64\opengl32.lib user32.lib kernel32.lib || exit /b 1
endlocal
del %2\*.exp %2\*.lib %3\*.exp %3\*.lib 2>nul
exit /b 0
