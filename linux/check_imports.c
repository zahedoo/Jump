#include <windows.h>
#include <stdio.h>

static const char *kernel32_names[] = {
    "HeapCreate",
    "GetCurrentProcess",
    "LoadLibraryExA",
    "CloseHandle",
    "HeapDestroy",
    "GetProcAddress",
    "LocalFree",
    "GetModuleHandleW",
    "IsWow64Process",
    "HeapFree",
    "SetLastError",
    "WaitForSingleObject",
    "CreateFileW",
    "OpenProcess",
    "QueueUserWorkItem",
    "CreateEventW",
    "Sleep",
    "GetLastError",
    "SetEvent",
    "HeapAlloc",
    "GetCurrentProcessId",
    "GetProcessTimes",
    "RemoveDirectoryW",
    "DeleteFileW",
    "FormatMessageW",
    "EnterCriticalSection",
    "CreatePrivateNamespaceW",
    "OpenPrivateNamespaceW",
    "LeaveCriticalSection",
    "InitializeCriticalSection",
    "CreateBoundaryDescriptorW",
    "CreateMutexW",
    "ReleaseMutex",
    "ClosePrivateNamespace",
    "AddSIDToBoundaryDescriptor",
    "DeleteCriticalSection",
    "DeleteBoundaryDescriptor",
    "ExpandEnvironmentStringsW",
    "HeapReAlloc",
    "CreateDirectoryW",
    "SizeofResource",
    "WriteFile",
    "LockResource",
    "LoadResource",
    "FindResourceW",
    "GetWindowsDirectoryW",
    "VirtualFree",
    "DeviceIoControl",
    "VirtualAlloc",
    "InitializeCriticalSectionAndSpinCount",
    "ReadFile",
    "SetHandleInformation",
    "CreatePipe",
    "GetExitCodeThread",
    "CreateThread",
    "CreateProcessW",
    "WriteConsoleW",
    "GetConsoleMode",
    "GetConsoleOutputCP",
    "FlushFileBuffers",
    "HeapSize",
    "RaiseException",
    "GetSystemInfo",
    "VirtualProtect",
    "VirtualQuery",
    "FreeLibrary",
    "RtlCaptureContext",
    "RtlLookupFunctionEntry",
    "RtlVirtualUnwind",
    "UnhandledExceptionFilter",
    "SetUnhandledExceptionFilter",
    "TerminateProcess",
    "IsProcessorFeaturePresent",
    "QueryPerformanceCounter",
    "GetCurrentThreadId",
    "GetSystemTimeAsFileTime",
    "InitializeSListHead",
    "IsDebuggerPresent",
    "GetStartupInfoW",
    "RtlUnwindEx",
    "InterlockedFlushSList",
    "TlsAlloc",
    "TlsGetValue",
    "TlsSetValue",
    "TlsFree",
    "LoadLibraryExW",
    "EncodePointer",
    "RtlPcToFileHeader",
    "ExitProcess",
    "GetModuleHandleExW",
    "GetModuleFileNameW",
    "GetStdHandle",
    "GetFileType",
    "FindClose",
    "FindFirstFileExW",
    "FindNextFileW",
    "IsValidCodePage",
    "GetACP",
    "GetOEMCP",
    "GetCPInfo",
    "GetCommandLineA",
    "GetCommandLineW",
    "MultiByteToWideChar",
    "WideCharToMultiByte",
    "GetEnvironmentStringsW",
    "FreeEnvironmentStringsW",
    "FlsAlloc",
    "FlsGetValue",
    "FlsSetValue",
    "FlsFree",
    "LCMapStringW",
    "GetProcessHeap",
    "GetStringTypeW",
    "SetFilePointerEx",
    "SetStdHandle",
    NULL
};

static const char *ntdll_names[] = {
    "NtQuerySystemInformation",
    "RtlNtStatusToDosError",
    "RtlGetNtVersionNumbers",
    "NtQueryKey",
    "NtQuerySystemTime",
    NULL
};

static int check_module(const char *module_name, const char **names) {
    HMODULE mod = LoadLibraryA(module_name);
    int missing = 0;
    printf("MODULE %s handle=%p err=%lu\n", module_name, (void *)mod, GetLastError());
    if (!mod) return 1000;
    for (int i = 0; names[i]; i++) {
        FARPROC proc = GetProcAddress(mod, names[i]);
        if (!proc) {
            printf("MISSING %s!%s err=%lu\n", module_name, names[i], GetLastError());
            missing++;
        }
    }
    return missing;
}

int main(void) {
    int missing = 0;
    missing += check_module("KERNEL32.dll", kernel32_names);
    missing += check_module("ntdll.dll", ntdll_names);
    printf("TOTAL_MISSING=%d\n", missing);
    return missing ? 1 : 0;
}
