/* Exercise the actual adapter callbacks with a fake SDK, never a network. */
#define BRIDGE_WIFI 1
#define BRIDGE_WIFI_SSID "test"
#define BRIDGE_WIFI_PASSWORD "test-only"
#include "../firmware/bridge/pico/wifi.c"
#include <assert.h>
#include <stdio.h>

cyw43_t cyw43_state;
static uint32_t fake_time;
static int link_status=CYW43_LINK_UP;
static unsigned joins,locks,freed;
static u16_t capacity=2048;
static err_t write_error=ERR_OK;
static struct tcp_pcb listening;
static char written[2048];
int cyw43_arch_init(void) {return 0;}
void cyw43_arch_enable_sta_mode(void) {}
void cyw43_arch_lwip_begin(void) {++locks;}
void cyw43_arch_lwip_end(void) {assert(locks);--locks;}
int cyw43_tcpip_link_status(cyw43_t *s,int i) {(void)s;(void)i;return link_status;}
int cyw43_arch_wifi_connect_async(const char *s,const char *p,uint32_t a)
{(void)s;(void)p;(void)a;++joins;return 0;}
uint32_t get_absolute_time(void) {return fake_time;}
uint32_t to_ms_since_boot(uint32_t value) {return value;}
void tcp_recv(struct tcp_pcb *p,test_recv_fn cb) {(void)p;(void)cb;}
void tcp_err(struct tcp_pcb *p,void (*cb)(void *,err_t)) {(void)p;(void)cb;}
void tcp_arg(struct tcp_pcb *p,void *a) {(void)p;(void)a;}
void tcp_abort(struct tcp_pcb *p) {p->aborted=1;}
void pbuf_free(struct pbuf *p) {(void)p;++freed;}
void tcp_recved(struct tcp_pcb *p,u16_t n) {(void)p;(void)n;}
void tcp_nagle_disable(struct tcp_pcb *p) {(void)p;}
struct tcp_pcb *tcp_new_ip_type(int type) {(void)type;return &listening;}
err_t tcp_bind(struct tcp_pcb *p,void *a,u16_t port) {(void)p;(void)a;assert(port==4242);return ERR_OK;}
struct tcp_pcb *tcp_listen_with_backlog(struct tcp_pcb *p,int backlog) {assert(backlog==1);return p;}
void tcp_accept(struct tcp_pcb *p,test_accept_fn cb) {(void)p;assert(cb==accept_client);}
u16_t tcp_sndbuf(struct tcp_pcb *p) {(void)p;return capacity;}
err_t tcp_write(struct tcp_pcb *p,const void *bytes,u16_t n,int flags)
{
    (void)p;assert(flags==TCP_WRITE_FLAG_COPY);
    if (write_error!=ERR_OK) return write_error;
    assert(strlen(written)+n<sizeof(written));strncat(written,bytes,n);return ERR_OK;
}
err_t tcp_output(struct tcp_pcb *p) {(void)p;return ERR_OK;}
static err_t incoming(struct tcp_pcb *p,char *text)
{
    struct pbuf buf={.payload=text,.len=(u16_t)strlen(text),.tot_len=(u16_t)strlen(text)};
    return receive(NULL,p,&buf,ERR_OK);
}
int main(void)
{
    bridge_wifi_init();assert(enabled);
    bridge_wifi_poll(0,false);assert(listener==&listening);
    struct tcp_pcb a={0},b={0};
    assert(accept_client(NULL,&a,ERR_OK)==ERR_OK);
    const uint32_t first=bridge_wifi_session();assert(first);
    assert(accept_client(NULL,&b,ERR_OK)==ERR_ABRT && b.aborted);
    assert(incoming(&a,"UI")==ERR_OK);assert(incoming(&a,"D 1\n")==ERR_OK);
    const char *expected="UID 1\n";
    while (*expected) assert(bridge_wifi_read(first)==*expected++);
    assert(bridge_wifi_read(first)==-1);
    bridge_wifi_write(first,"PING OK");capacity=0;bridge_wifi_poll(1,false);assert(tx_length==8);
    capacity=3;bridge_wifi_poll(2,false);assert(tx_length==5);
    capacity=2048;write_error=ERR_MEM;bridge_wifi_poll(3,false);assert(tx_length==5);
    write_error=ERR_OK;bridge_wifi_poll(4,false);assert(!tx_length && strcmp(written,"PING OK\n")==0);
    /* USB takes exclusive ownership, flushing partial network input. */
    assert(incoming(&a,"UID ")==ERR_OK);bridge_wifi_poll(5,true);
    assert(a.aborted && !bridge_wifi_session() && rx_read==rx_write);
    b.aborted=0;assert(accept_client(NULL,&b,ERR_OK)==ERR_ABRT);
    bridge_wifi_poll(6,false);b.aborted=0;assert(accept_client(NULL,&b,ERR_OK)==ERR_OK);
    uint32_t second=bridge_wifi_session();assert(second && second!=first);
    bridge_wifi_write(first,"old reply");assert(!tx_length);
    assert(incoming(&b,"INFO\n")==ERR_OK);assert(bridge_wifi_read(first)==-1);
    assert(bridge_wifi_read(second)=='I');
    /* Loss, FIN, full input, full output and stale clients all tear down. */
    link_status=0;bridge_wifi_poll(7,false);assert(!bridge_wifi_session());
    link_status=CYW43_LINK_UP;bridge_wifi_poll(8,false);
    b.aborted=0;assert(accept_client(NULL,&b,ERR_OK)==ERR_OK);
    assert(receive(NULL,&b,NULL,ERR_OK)==ERR_ABRT && !bridge_wifi_session());
    b.aborted=0;assert(accept_client(NULL,&b,ERR_OK)==ERR_OK);
    char many[300];memset(many,'x',sizeof(many)-1);many[sizeof(many)-1]='\0';
    assert(incoming(&b,many)==ERR_ABRT && !bridge_wifi_session());
    b.aborted=0;assert(accept_client(NULL,&b,ERR_OK)==ERR_OK);second=bridge_wifi_session();
    for (unsigned i=0;i<10;++i) bridge_wifi_write(second,many);
    assert(!bridge_wifi_session());
    b.aborted=0;assert(accept_client(NULL,&b,ERR_OK)==ERR_OK);tcp_error(NULL,ERR_ABRT);
    assert(!bridge_wifi_session());
    b.aborted=0;assert(accept_client(NULL,&b,ERR_OK)==ERR_OK);
    bridge_wifi_poll(CLIENT_IDLE_MS,false);assert(!bridge_wifi_session());
    const unsigned previous_joins=joins;
    link_status=0;bridge_wifi_poll(CLIENT_IDLE_MS+10000,false);assert(joins==previous_joins+1);
    bridge_wifi_poll(CLIENT_IDLE_MS+10001,false);assert(joins==previous_joins+1);
    bridge_wifi_poll(CLIENT_IDLE_MS+40000,false);assert(joins==previous_joins+2);
    assert(!locks && freed>=4);
    puts("Wi-Fi adapter tests passed (fragmentation, ownership, reconnect, stale session, backpressure, disconnect, buffer limits, idle/rejoin)");
    return 0;
}
