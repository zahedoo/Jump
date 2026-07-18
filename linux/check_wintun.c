#include <windows.h>
#include <stdio.h>

int main(void) {
    HMODULE h = LoadLibraryExA("wintun.dll", NULL, 0x00000200 | 0x00000800);
    printf("h=%p err=%lu\n", (void *)h, GetLastError());
    if (!h) return 2;

    FARPROC p = GetProcAddress(h, "WintunCloseAdapter");
    printf("proc=%p err=%lu\n", (void *)p, GetLastError());
    return p ? 0 : 3;
}
