/*
 * u9run.exe — u9.exe を止めた状態で起動し、u9probe.dll を読み込ませてから動かす（32ビット）
 * 使い方: u9run.exe <ゲームのフォルダ> <u9probe.dll のフルパス> [EXE の名前（既定 u9.exe）]
 * 起動したプロセス番号を標準出力に書く。
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>

int main(int argc, char **argv)
{
    STARTUPINFOA si = { sizeof si }; PROCESS_INFORMATION pi; char exe[MAX_PATH];
    void *mem; HANDLE th; DWORD code = 0;
    if (argc < 3) { fprintf(stderr, "使い方: u9run <ゲームのフォルダ> <dll>\n"); return 1; }
    sprintf(exe, "%s\\%s", argv[1], argc > 3 ? argv[3] : "u9.exe");   /* 3つ目で EXE の名前を変えられる */
    si.dwFlags = STARTF_USESHOWWINDOW; si.wShowWindow = SW_SHOWNOACTIVATE;
    if (!CreateProcessA(exe, NULL, NULL, NULL, FALSE, CREATE_SUSPENDED, NULL, argv[1], &si, &pi)) {
        fprintf(stderr, "起動できません %lu\n", GetLastError()); return 1;
    }
    mem = VirtualAllocEx(pi.hProcess, NULL, 4096, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    WriteProcessMemory(pi.hProcess, mem, argv[2], strlen(argv[2]) + 1, NULL);
    th = CreateRemoteThread(pi.hProcess, NULL, 0,
        (LPTHREAD_START_ROUTINE)GetProcAddress(GetModuleHandleA("kernel32.dll"), "LoadLibraryA"), mem, 0, NULL);
    WaitForSingleObject(th, 10000);
    GetExitCodeThread(th, &code);
    if (!code) { fprintf(stderr, "DLL を読み込めませんでした\n"); TerminateProcess(pi.hProcess, 1); return 1; }
    ResumeThread(pi.hThread);
    printf("%lu\n", pi.dwProcessId);
    return 0;
}
