@echo off
rem opengl32.dll（代わり）を組み立てる。gen.py が作る。
rem   build.bat       配布版。ウルティマI は out\opengl32.dll、ほかは out\<作品>\opengl32.dll
rem   build.bat test  試験版（/DUJ_TEST。dump=1 で絵を BMP に保存できる）。out\test\<作品>\opengl32.dll。配布しない
rem   ソース: ウルティマI は gl_proxy.c、II は u2\、0・III～VI・外伝2作は more\（どれも配布物に入れている形のまま）
rem   バージョン情報は ver\<作品>.rc
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars32.bat" >nul
cd /d "%~dp0"
set MODE=%1
call :one ultima1 . || exit /b 1
call :one ultima2 u2 || exit /b 1
for %%g in (akalabeth ultima3 ultima4 ultima5 ultima6 martian savage) do call :one %%g more || exit /b 1
echo ok
exit /b 0

:one
set O=out\%1
if "%1"=="ultima1" set O=out
set B=out\obj\%1
set DEF=
if "%MODE%"=="test" set O=out\test\%1
if "%MODE%"=="test" set B=out\test\obj\%1
if "%MODE%"=="test" set DEF=/DUJ_TEST
if not exist %O% mkdir %O%
if not exist %B% mkdir %B%
rc /nologo /fo %B%\ver.res ver\%1.rc || exit /b 1
cl /nologo /utf-8 /D_CRT_SECURE_NO_WARNINGS /O2 /LD /MT /W3 %DEF% /I. /Fo%B%\ %2\gl_proxy.c %B%\ver.res /link /OUT:%O%\opengl32.dll /IMPLIB:%B%\opengl32.lib user32.lib gdi32.lib kernel32.lib >%B%\log.txt || (type %B%\log.txt & exit /b 1)
del %O%\opengl32.exp %O%\opengl32.lib 2>nul
exit /b 0
