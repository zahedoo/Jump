#include <windows.h>
#include <stdint.h>
#include <stdlib.h>

#ifndef NO_ERROR
#define NO_ERROR 0
#endif

/*
 * Minimal Windows Filtering Platform shim for running the Windows XVPN SDK
 * under Wine. sing-box/sing-tun opens WFP to add process/network filters for
 * the TUN inbound. On Linux/Wine we only need those calls to be harmless no-ops
 * so the SDK can keep its SOCKS inbound alive.
 */

typedef struct FWP_BYTE_BLOB_SHIM {
    uint32_t size;
    uint8_t *data;
} FWP_BYTE_BLOB_SHIM;

uint32_t WINAPI FwpmEngineOpen0(
    const wchar_t *serverName,
    uint32_t authnService,
    void *authIdentity,
    const void *session,
    HANDLE *engineHandle
) {
    (void)serverName;
    (void)authnService;
    (void)authIdentity;
    (void)session;
    if (engineHandle) *engineHandle = (HANDLE)(uintptr_t)0xF001;
    return NO_ERROR;
}

uint32_t WINAPI FwpmEngineClose0(HANDLE engineHandle) {
    (void)engineHandle;
    return NO_ERROR;
}

uint32_t WINAPI FwpmSubLayerAdd0(HANDLE engineHandle, const void *subLayer, void *sd) {
    (void)engineHandle;
    (void)subLayer;
    (void)sd;
    return NO_ERROR;
}

uint32_t WINAPI FwpmFilterAdd0(HANDLE engineHandle, const void *filter, void *sd, uint64_t *id) {
    (void)engineHandle;
    (void)filter;
    (void)sd;
    if (id) *id = 1;
    return NO_ERROR;
}

uint32_t WINAPI FwpmGetAppIdFromFileName0(const wchar_t *fileName, FWP_BYTE_BLOB_SHIM **appId) {
    (void)fileName;
    if (appId) {
        FWP_BYTE_BLOB_SHIM *blob = (FWP_BYTE_BLOB_SHIM *)calloc(1, sizeof(FWP_BYTE_BLOB_SHIM));
        if (!blob) return 8;
        *appId = blob;
    }
    return NO_ERROR;
}

void WINAPI FwpmFreeMemory0(void **p) {
    if (p && *p) {
        free(*p);
        *p = NULL;
    }
}
