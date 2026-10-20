#ifndef MICROSMT_BRIDGE_WIFI_H
#define MICROSMT_BRIDGE_WIFI_H
#include <stdbool.h>
#include <stdint.h>
void bridge_wifi_init(void);
/* Called from main context. USB ownership closes/rejects network clients. */
void bridge_wifi_poll(uint32_t now, bool usb_owner);
uint32_t bridge_wifi_session(void); /* zero disconnected; changes per client */
int bridge_wifi_read(uint32_t expected_session);
void bridge_wifi_write(uint32_t expected_session, const char *line);
#endif
