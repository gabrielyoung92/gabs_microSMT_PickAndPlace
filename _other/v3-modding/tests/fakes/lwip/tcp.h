#ifndef TEST_TCP_H
#define TEST_TCP_H
#include <stdint.h>
typedef int err_t;
typedef uint16_t u16_t;
#define ERR_OK 0
#define ERR_ABRT (-13)
#define ERR_MEM (-1)
#define IPADDR_TYPE_V4 0
#define IP_ANY_TYPE ((void *)0)
#define TCP_WRITE_FLAG_COPY 1
struct tcp_pcb { int aborted; };
struct pbuf { struct pbuf *next;void *payload;u16_t len,tot_len; };
typedef err_t (*test_recv_fn)(void *,struct tcp_pcb *,struct pbuf *,err_t);
typedef err_t (*test_accept_fn)(void *,struct tcp_pcb *,err_t);
void tcp_recv(struct tcp_pcb *p,test_recv_fn cb);
void tcp_err(struct tcp_pcb *p,void (*cb)(void *,err_t));
void tcp_arg(struct tcp_pcb *p,void *arg);
void tcp_abort(struct tcp_pcb *p);
void pbuf_free(struct pbuf *p);
void tcp_recved(struct tcp_pcb *p,u16_t length);
void tcp_nagle_disable(struct tcp_pcb *p);
struct tcp_pcb *tcp_new_ip_type(int type);
err_t tcp_bind(struct tcp_pcb *p,void *address,u16_t port);
struct tcp_pcb *tcp_listen_with_backlog(struct tcp_pcb *p,int backlog);
void tcp_accept(struct tcp_pcb *p,test_accept_fn cb);
u16_t tcp_sndbuf(struct tcp_pcb *p);
err_t tcp_write(struct tcp_pcb *p,const void *bytes,u16_t length,int flags);
err_t tcp_output(struct tcp_pcb *p);
#endif
