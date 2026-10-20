#include "wifi.h"
#if defined(BRIDGE_WIFI)
#include "pico/cyw43_arch.h"
#include "pico/stdlib.h"
#include "lwip/tcp.h"
#include <string.h>

/* Private build configuration, never committed or printed to the console. */
#if __has_include("bridge_wifi_config.h")
#include "bridge_wifi_config.h"
#endif
#ifndef BRIDGE_WIFI_SSID
#define BRIDGE_WIFI_SSID ""
#endif
#ifndef BRIDGE_WIFI_PASSWORD
#define BRIDGE_WIFI_PASSWORD ""
#endif
#define TCP_PORT 4242u
#define RX_SIZE 256u
#define TX_SIZE 2048u
#define CLIENT_IDLE_MS 30000u

static struct tcp_pcb *listener, *client;
static uint8_t rx[RX_SIZE],tx[TX_SIZE];
static unsigned rx_read,rx_write,tx_length;
static uint32_t sequence,session,last_activity,last_attempt;
static bool enabled,usb_blocked,joining;

/* All network state is protected by the cyw43 lwIP lock, including access from
 * main. Callbacks already run inside that lock. No bus/printf work in callbacks. */
static void drop_client(void)
{
    if (client) {
        tcp_recv(client,NULL);tcp_err(client,NULL);tcp_arg(client,NULL);
        tcp_abort(client);client=NULL;
    }
    session=0;rx_read=rx_write=tx_length=0;
}
static void tcp_error(void *arg, err_t error)
{
    (void)arg;(void)error;
    client=NULL;session=0;rx_read=rx_write=tx_length=0;
}
static err_t receive(void *arg, struct tcp_pcb *pcb, struct pbuf *p, err_t error)
{
    (void)arg;
    if (!p || error!=ERR_OK || usb_blocked) {
        if (p) pbuf_free(p);
        drop_client();return ERR_ABRT;
    }
    const unsigned used=(rx_write+RX_SIZE-rx_read)%RX_SIZE;
    if (p->tot_len>RX_SIZE-1u-used) {
        pbuf_free(p);drop_client();return ERR_ABRT;
    }
    for (struct pbuf *part=p;part;part=part->next) {
        const uint8_t *bytes=part->payload;
        for (unsigned i=0;i<part->len;++i) {rx[rx_write]=bytes[i];rx_write=(rx_write+1u)%RX_SIZE;}
    }
    tcp_recved(pcb,p->tot_len);pbuf_free(p);
    last_activity=to_ms_since_boot(get_absolute_time());
    return ERR_OK;
}
static err_t accept_client(void *arg, struct tcp_pcb *pcb, err_t error)
{
    (void)arg;
    if (error!=ERR_OK || client || usb_blocked) {tcp_abort(pcb);return ERR_ABRT;}
    client=pcb;
    if (++sequence==0) ++sequence;
    session=sequence;rx_read=rx_write=tx_length=0;
    last_activity=to_ms_since_boot(get_absolute_time());
    tcp_recv(pcb,receive);tcp_err(pcb,tcp_error);tcp_nagle_disable(pcb);
    return ERR_OK;
}
void bridge_wifi_init(void)
{
    if (!BRIDGE_WIFI_SSID[0] || !BRIDGE_WIFI_PASSWORD[0]) return;
    if (cyw43_arch_init()!=0) return;
    cyw43_arch_enable_sta_mode();
    enabled=true;
    /* First asynchronous join starts in poll. USB diagnostics work without it. */
    last_attempt=to_ms_since_boot(get_absolute_time())-10000u;
}
void bridge_wifi_poll(uint32_t now, bool usb_owner)
{
    if (!enabled) return;
    cyw43_arch_lwip_begin();
    usb_blocked=usb_owner;
    const int status=cyw43_tcpip_link_status(&cyw43_state,CYW43_ITF_STA);
    if (usb_owner || status!=CYW43_LINK_UP ||
        (client && (uint32_t)(now-last_activity)>=CLIENT_IDLE_MS)) drop_client();
    if (status==CYW43_LINK_UP) {
        joining=false;
        if (!listener) {
            struct tcp_pcb *pcb=tcp_new_ip_type(IPADDR_TYPE_V4);
            if (pcb) {
                if (tcp_bind(pcb,IP_ANY_TYPE,TCP_PORT)==ERR_OK) {
                    listener=tcp_listen_with_backlog(pcb,1);
                    if (listener) tcp_accept(listener,accept_client);
                    else tcp_abort(pcb);
                } else tcp_abort(pcb);
            }
        }
        if (client && tx_length) {
            unsigned n=tx_length;
            if (n>tcp_sndbuf(client)) n=tcp_sndbuf(client);
            if (n) {
                const err_t err=tcp_write(client,tx,(u16_t)n,TCP_WRITE_FLAG_COPY);
                if (err==ERR_OK) {
                    tx_length-=n;memmove(tx,tx+n,tx_length);
                    (void)tcp_output(client);
                } else if (err!=ERR_MEM) drop_client();
            }
        }
    }
    cyw43_arch_lwip_end();
    if (status!=CYW43_LINK_UP &&
        (uint32_t)(now-last_attempt)>=(joining ? 30000u : 10000u)) {
        last_attempt=now;
        joining=cyw43_arch_wifi_connect_async(BRIDGE_WIFI_SSID,BRIDGE_WIFI_PASSWORD,CYW43_AUTH_WPA2_AES_PSK)==0;
    }
}
uint32_t bridge_wifi_session(void)
{
    if (!enabled) return 0;
    cyw43_arch_lwip_begin();const uint32_t s=session;cyw43_arch_lwip_end();return s;
}
int bridge_wifi_read(uint32_t expected_session)
{
    if (!enabled) return -1;
    int value=-1;
    cyw43_arch_lwip_begin();
    if (session==expected_session && rx_read!=rx_write) {value=rx[rx_read];rx_read=(rx_read+1u)%RX_SIZE;}
    cyw43_arch_lwip_end();return value;
}
void bridge_wifi_write(uint32_t expected_session, const char *line)
{
    if (!enabled) return;
    const size_t n=strlen(line);
    cyw43_arch_lwip_begin();
    if (client && session==expected_session) {
        if (n+1>TX_SIZE-tx_length) drop_client();
        else {memcpy(tx+tx_length,line,n);tx_length+=(unsigned)n;tx[tx_length++]='\n';}
    }
    cyw43_arch_lwip_end();
}
#else
void bridge_wifi_init(void) {}
void bridge_wifi_poll(uint32_t now, bool usb_owner) {(void)now;(void)usb_owner;}
uint32_t bridge_wifi_session(void) {return 0;}
int bridge_wifi_read(uint32_t expected_session) {(void)expected_session;return -1;}
void bridge_wifi_write(uint32_t expected_session, const char *line) {(void)expected_session;(void)line;}
#endif
