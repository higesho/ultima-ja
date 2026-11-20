# 改造 Exult を Release x64 でビルドする（動いている試験用の Exult は先に止める）
$w = Split-Path -Parent $PSScriptRoot
& "$PSScriptRoot\exult.ps1" -Stop
Start-Sleep -Milliseconds 500
$vs = 'C:\Program Files\Microsoft Visual Studio\18\Community'
$env:VCPKG_ROOT = "$vs\VC\vcpkg"
$log = "$w\build_exult.log"
& "$vs\MSBuild\Current\Bin\amd64\MSBuild.exe" "$w\exult\msvcstuff\vs2019\Exult.sln" /t:Exult /p:Configuration=Release /p:Platform=x64 /m /v:minimal `
    "/p:ForceImportBeforeCppTargets=$vs\VC\vcpkg\scripts\buildsystems\msbuild\vcpkg.props" `
    "/p:ForceImportAfterCppTargets=$vs\VC\vcpkg\scripts\buildsystems\msbuild\vcpkg.targets" *> $log
$code = $LASTEXITCODE
Select-String -Path $log -Pattern ': (fatal )?error' | Select-Object -First 20 | ForEach-Object Line
"ビルド終了コード: $code"
