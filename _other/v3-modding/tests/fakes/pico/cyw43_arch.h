#ifndef TEST_CYW43_H
#define TEST_CYW43_H
#include <stdint.h>
typedef struct { int unused; } cyw43_t;
extern cyw43_t cyw43_state;
#define CYW43_ITF_STA 0
#define CYW43_LINK_UP 3
#define CYW43_AUTH_WPA2_AES_PSK 1u
int cyw43_arch_init(void);
void cyw43_arch_enable_sta_mode(void);
void cyw43_arch_lwip_begin(void);
void cyw43_arch_lwip_end(void);
int cyw43_tcpip_link_status(cyw43_t *state,int interface);
int cyw43_arch_wifi_connect_async(const char *ssid,const char *password,uint32_t auth);
#endif
