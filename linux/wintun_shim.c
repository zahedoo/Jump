#ifndef _WIN32_WINNT
#define _WIN32_WINNT 0x0A00
#endif

#include <windows.h>
#include <stdint.h>
#include <stdlib.h>

/*
 * Experimental Wintun compatibility shim for Wine.
 *
 * This does NOT create a real TUN adapter. It only exports the Wintun symbols
 * required by sing-tun so we can verify whether XVPN's Xray SOCKS inbound can
 * stay alive without a real Windows kernel driver.
 */

typedef void *WINTUN_ADAPTER_HANDLE;
typedef void *WINTUN_SESSION_HANDLE;
typedef void (CALLBACK *WINTUN_LOGGER_CALLBACK)(DWORD Level, DWORD64 Timestamp, const WCHAR *Message);

static HANDLE g_read_event = NULL;

static HANDLE shim_event(void) {
    if (!g_read_event) {
        g_read_event = CreateEventW(NULL, TRUE, FALSE, NULL);
    }
    return g_read_event;
}

WINTUN_ADAPTER_HANDLE WINAPI WintunCreateAdapter(const WCHAR *Name, const WCHAR *TunnelType, const GUID *RequestedGUID) {
    (void)Name;
    (void)TunnelType;
    (void)RequestedGUID;
    SetLastError(ERROR_SUCCESS);
    return (WINTUN_ADAPTER_HANDLE)(uintptr_t)0x1111;
}

WINTUN_ADAPTER_HANDLE WINAPI WintunOpenAdapter(const WCHAR *Name) {
    (void)Name;
    SetLastError(ERROR_SUCCESS);
    return (WINTUN_ADAPTER_HANDLE)(uintptr_t)0x1111;
}

void WINAPI WintunCloseAdapter(WINTUN_ADAPTER_HANDLE Adapter) {
    (void)Adapter;
}

BOOL WINAPI WintunDeleteDriver(void) {
    SetLastError(ERROR_SUCCESS);
    return TRUE;
}

void WINAPI WintunGetAdapterLUID(WINTUN_ADAPTER_HANDLE Adapter, uint64_t *Luid) {
    (void)Adapter;
    if (Luid) *Luid = 1;
}

DWORD WINAPI WintunGetRunningDriverVersion(void) {
    return 0x000E0000;
}

WINTUN_SESSION_HANDLE WINAPI WintunStartSession(WINTUN_ADAPTER_HANDLE Adapter, DWORD Capacity) {
    (void)Adapter;
    (void)Capacity;
    shim_event();
    SetLastError(ERROR_SUCCESS);
    return (WINTUN_SESSION_HANDLE)(uintptr_t)0x2222;
}

void WINAPI WintunEndSession(WINTUN_SESSION_HANDLE Session) {
    (void)Session;
}

HANDLE WINAPI WintunGetReadWaitEvent(WINTUN_SESSION_HANDLE Session) {
    (void)Session;
    return shim_event();
}

BYTE *WINAPI WintunReceivePacket(WINTUN_SESSION_HANDLE Session, DWORD *PacketSize) {
    (void)Session;
    if (PacketSize) *PacketSize = 0;
    SetLastError(ERROR_NO_MORE_ITEMS);
    return NULL;
}

void WINAPI WintunReleaseReceivePacket(WINTUN_SESSION_HANDLE Session, const BYTE *Packet) {
    (void)Session;
    (void)Packet;
}

BYTE *WINAPI WintunAllocateSendPacket(WINTUN_SESSION_HANDLE Session, DWORD PacketSize) {
    (void)Session;
    if (PacketSize == 0) PacketSize = 1;
    SetLastError(ERROR_SUCCESS);
    return (BYTE *)malloc(PacketSize);
}

void WINAPI WintunSendPacket(WINTUN_SESSION_HANDLE Session, const BYTE *Packet) {
    (void)Session;
    free((void *)Packet);
}

void WINAPI WintunSetLogger(WINTUN_LOGGER_CALLBACK NewLogger) {
    (void)NewLogger;
}
