#ifndef _WIN32_WINNT
#define _WIN32_WINNT 0x0A00
#endif

#include <winsock2.h>
#include <windows.h>
#include <iptypes.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>

#ifndef NO_ERROR
#define NO_ERROR 0
#endif
#ifndef ERROR_INVALID_PARAMETER
#define ERROR_INVALID_PARAMETER 87
#endif
#ifndef ERROR_NOT_ENOUGH_MEMORY
#define ERROR_NOT_ENOUGH_MEMORY 8
#endif
#ifndef ERROR_NOT_FOUND
#define ERROR_NOT_FOUND 1168
#endif
#ifndef ERROR_NO_DATA
#define ERROR_NO_DATA 232
#endif
#ifndef ERROR_BUFFER_OVERFLOW
#define ERROR_BUFFER_OVERFLOW 111
#endif
#ifndef ERROR_PROC_NOT_FOUND
#define ERROR_PROC_NOT_FOUND 127
#endif

/*
 * Minimal IPHLPAPI shim for testing the Windows XVPN SDK under Wine.
 *
 * Wine 9.0 and current Wine master do not export InitializeIpInterfaceEntry.
 * The XVPN SDK uses sing-tun's Windows network monitor and aborts when the
 * procedure is missing. This shim intentionally returns an empty route table so
 * sing-tun treats default-route discovery as unavailable instead of crashing.
 *
 * It is a compatibility probe, not a full IP Helper implementation.
 */

typedef uint16_t ADDRESS_FAMILY;
typedef void *PVOID;
typedef void *HANDLE_VALUE;

typedef struct SHIM_EMPTY_TABLE {
    uint32_t NumEntries;
} SHIM_EMPTY_TABLE;

static uint32_t alloc_empty_table(void **Table) {
    SHIM_EMPTY_TABLE *table;
    if (!Table) return ERROR_INVALID_PARAMETER;
    table = (SHIM_EMPTY_TABLE *)calloc(1, sizeof(SHIM_EMPTY_TABLE));
    if (!table) return ERROR_NOT_ENOUGH_MEMORY;
    table->NumEntries = 0;
    *Table = table;
    return NO_ERROR;
}

static void set_fake_luid(uint64_t *InterfaceLuid) {
    if (InterfaceLuid) *InterfaceLuid = 1;
}

void WINAPI InitializeIpInterfaceEntry(void *Row) {
    (void)Row;
}

void WINAPI InitializeIpForwardEntry(void *Row) {
    (void)Row;
}

void WINAPI InitializeUnicastIpAddressEntry(void *Row) {
    (void)Row;
}

void WINAPI InitializeAnycastIpAddressEntry(void *Row) {
    (void)Row;
}

uint32_t WINAPI GetIpForwardTable2(ADDRESS_FAMILY Family, void **Table) {
    (void)Family;
    return alloc_empty_table(Table);
}

uint32_t WINAPI GetIpInterfaceTable(ADDRESS_FAMILY Family, void **Table) {
    (void)Family;
    return alloc_empty_table(Table);
}

uint32_t WINAPI GetUnicastIpAddressTable(ADDRESS_FAMILY Family, void **Table) {
    (void)Family;
    return alloc_empty_table(Table);
}

uint32_t WINAPI GetAnycastIpAddressTable(ADDRESS_FAMILY Family, void **Table) {
    (void)Family;
    return alloc_empty_table(Table);
}

uint32_t WINAPI GetIfTable2(void **Table) {
    return alloc_empty_table(Table);
}

uint32_t WINAPI GetIfTable2Ex(uint32_t Level, void **Table) {
    (void)Level;
    return alloc_empty_table(Table);
}

uint32_t WINAPI GetIpForwardEntry2(void *Row) {
    (void)Row;
    return ERROR_NOT_FOUND;
}

uint32_t WINAPI GetIpInterfaceEntry(void *Row) {
    (void)Row;
    return NO_ERROR;
}

uint32_t WINAPI GetUnicastIpAddressEntry(void *Row) {
    (void)Row;
    return ERROR_NOT_FOUND;
}

uint32_t WINAPI GetAnycastIpAddressEntry(void *Row) {
    (void)Row;
    return ERROR_NOT_FOUND;
}

uint32_t WINAPI GetIfEntry2(void *Row) {
    (void)Row;
    return NO_ERROR;
}

uint32_t WINAPI CreateIpForwardEntry2(void *Row) {
    (void)Row;
    return NO_ERROR;
}

uint32_t WINAPI CreateUnicastIpAddressEntry(void *Row) {
    (void)Row;
    return NO_ERROR;
}

uint32_t WINAPI CreateAnycastIpAddressEntry(void *Row) {
    (void)Row;
    return NO_ERROR;
}

uint32_t WINAPI DeleteIpForwardEntry2(void *Row) {
    (void)Row;
    return NO_ERROR;
}

uint32_t WINAPI DeleteUnicastIpAddressEntry(void *Row) {
    (void)Row;
    return NO_ERROR;
}

uint32_t WINAPI DeleteAnycastIpAddressEntry(void *Row) {
    (void)Row;
    return NO_ERROR;
}

uint32_t WINAPI SetIpForwardEntry2(void *Row) {
    (void)Row;
    return NO_ERROR;
}

uint32_t WINAPI SetIpInterfaceEntry(void *Row) {
    (void)Row;
    return NO_ERROR;
}

uint32_t WINAPI SetUnicastIpAddressEntry(void *Row) {
    (void)Row;
    return NO_ERROR;
}

void WINAPI FreeMibTable(void *Memory) {
    free(Memory);
}

uint32_t WINAPI NotifyRouteChange2(
    ADDRESS_FAMILY Family,
    void *Callback,
    void *CallerContext,
    unsigned char InitialNotification,
    HANDLE_VALUE *NotificationHandle
) {
    (void)Family;
    (void)Callback;
    (void)CallerContext;
    (void)InitialNotification;
    if (NotificationHandle) *NotificationHandle = (HANDLE_VALUE)(uintptr_t)1;
    return NO_ERROR;
}

uint32_t WINAPI NotifyIpInterfaceChange(
    ADDRESS_FAMILY Family,
    void *Callback,
    void *CallerContext,
    unsigned char InitialNotification,
    HANDLE_VALUE *NotificationHandle
) {
    (void)Family;
    (void)Callback;
    (void)CallerContext;
    (void)InitialNotification;
    if (NotificationHandle) *NotificationHandle = (HANDLE_VALUE)(uintptr_t)2;
    return NO_ERROR;
}

uint32_t WINAPI NotifyUnicastIpAddressChange(
    ADDRESS_FAMILY Family,
    void *Callback,
    void *CallerContext,
    unsigned char InitialNotification,
    HANDLE_VALUE *NotificationHandle
) {
    (void)Family;
    (void)Callback;
    (void)CallerContext;
    (void)InitialNotification;
    if (NotificationHandle) *NotificationHandle = (HANDLE_VALUE)(uintptr_t)3;
    return NO_ERROR;
}

uint32_t WINAPI CancelMibChangeNotify2(HANDLE_VALUE NotificationHandle) {
    (void)NotificationHandle;
    return NO_ERROR;
}

uint32_t WINAPI ConvertInterfaceLuidToGuid(const void *InterfaceLuid, GUID *InterfaceGuid) {
    (void)InterfaceLuid;
    if (!InterfaceGuid) return ERROR_INVALID_PARAMETER;
    InterfaceGuid->Data1 = 1;
    InterfaceGuid->Data2 = 0;
    InterfaceGuid->Data3 = 0;
    for (int i = 0; i < 8; i++) InterfaceGuid->Data4[i] = 0;
    return NO_ERROR;
}

uint32_t WINAPI ConvertInterfaceGuidToLuid(const GUID *InterfaceGuid, uint64_t *InterfaceLuid) {
    (void)InterfaceGuid;
    if (!InterfaceLuid) return ERROR_INVALID_PARAMETER;
    set_fake_luid(InterfaceLuid);
    return NO_ERROR;
}

uint32_t WINAPI ConvertInterfaceIndexToLuid(uint32_t InterfaceIndex, uint64_t *InterfaceLuid) {
    (void)InterfaceIndex;
    if (!InterfaceLuid) return ERROR_INVALID_PARAMETER;
    set_fake_luid(InterfaceLuid);
    return NO_ERROR;
}

uint32_t WINAPI ConvertInterfaceLuidToIndex(const uint64_t *InterfaceLuid, uint32_t *InterfaceIndex) {
    (void)InterfaceLuid;
    if (!InterfaceIndex) return ERROR_INVALID_PARAMETER;
    *InterfaceIndex = 1;
    return NO_ERROR;
}

uint32_t WINAPI ConvertInterfaceAliasToLuid(const wchar_t *InterfaceAlias, uint64_t *InterfaceLuid) {
    (void)InterfaceAlias;
    if (!InterfaceLuid) return ERROR_INVALID_PARAMETER;
    set_fake_luid(InterfaceLuid);
    return NO_ERROR;
}

uint32_t WINAPI ConvertInterfaceLuidToAlias(const uint64_t *InterfaceLuid, wchar_t *InterfaceAlias, size_t Length) {
    (void)InterfaceLuid;
    if (!InterfaceAlias || Length == 0) return ERROR_INVALID_PARAMETER;
    wcsncpy(InterfaceAlias, L"JumpJumpTun", Length - 1);
    InterfaceAlias[Length - 1] = 0;
    return NO_ERROR;
}

uint32_t WINAPI GetBestInterfaceEx(const void *Sockaddr, uint32_t *BestIfIndex) {
    (void)Sockaddr;
    if (!BestIfIndex) return ERROR_INVALID_PARAMETER;
    *BestIfIndex = 1;
    return NO_ERROR;
}

uint32_t WINAPI GetBestRoute2(
    const uint64_t *InterfaceLuid,
    uint32_t InterfaceIndex,
    const void *SourceAddress,
    const void *DestinationAddress,
    uint32_t AddressSortOptions,
    void *BestRoute,
    void *BestSourceAddress
) {
    (void)InterfaceLuid;
    (void)InterfaceIndex;
    (void)SourceAddress;
    (void)DestinationAddress;
    (void)AddressSortOptions;
    (void)BestRoute;
    (void)BestSourceAddress;
    return ERROR_NOT_FOUND;
}

uint32_t WINAPI GetAdaptersAddresses(
    uint32_t Family,
    uint32_t Flags,
    void *Reserved,
    void *AdapterAddresses,
    uint32_t *SizePointer
) {
    (void)Family;
    (void)Flags;
    (void)Reserved;
    if (!SizePointer) return ERROR_INVALID_PARAMETER;
    const uint32_t needed = (uint32_t)(sizeof(IP_ADAPTER_ADDRESSES_LH) + 256);
    if (!AdapterAddresses || *SizePointer < needed) {
        *SizePointer = needed;
        return ERROR_BUFFER_OVERFLOW;
    }
    memset(AdapterAddresses, 0, *SizePointer);
    IP_ADAPTER_ADDRESSES_LH *adapter = (IP_ADAPTER_ADDRESSES_LH *)AdapterAddresses;
    char *cursor = (char *)AdapterAddresses + sizeof(IP_ADAPTER_ADDRESSES_LH);
    char *nameA = cursor;
    strcpy(nameA, "JumpJumpTun");
    cursor += 32;
    wchar_t *nameW = (wchar_t *)cursor;
    wcscpy(nameW, L"JumpJumpTun");

    adapter->Length = sizeof(IP_ADAPTER_ADDRESSES_LH);
    adapter->IfIndex = 1;
    adapter->Next = NULL;
    adapter->AdapterName = nameA;
    adapter->Description = nameW;
    adapter->FriendlyName = nameW;
    adapter->PhysicalAddressLength = 0;
    adapter->Flags = IP_ADAPTER_IPV4_ENABLED | IP_ADAPTER_IPV6_ENABLED;
    adapter->Mtu = 1500;
    adapter->IfType = IF_TYPE_TUNNEL;
    adapter->OperStatus = IfOperStatusUp;
    adapter->Ipv6IfIndex = 1;
    adapter->Ipv4Metric = 1;
    adapter->Ipv6Metric = 1;
    adapter->Luid.Value = 1;
    adapter->ConnectionType = NET_IF_CONNECTION_DEDICATED;
    adapter->TunnelType = TUNNEL_TYPE_NONE;
    return NO_ERROR;
}

uint32_t WINAPI GetNetworkParams(void *FixedInfo, uint32_t *OutBufLen) {
    (void)FixedInfo;
    if (OutBufLen) *OutBufLen = 0;
    return ERROR_NO_DATA;
}

uint32_t WINAPI SetInterfaceDnsSettings(const GUID *Interface, const void *Settings) {
    (void)Interface;
    (void)Settings;
    return NO_ERROR;
}
