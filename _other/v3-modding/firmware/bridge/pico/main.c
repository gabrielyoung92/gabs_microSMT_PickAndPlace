/* USB CDC -> custom open-drain feeder bench bus; Pico SDK, no Arduino. */
#include "pico/stdlib.h"
#include "pico/stdio_usb.h"
#include "hardware/sync.h"
#include "hardware/watchdog.h"
#include "bus_packet.h"
#include "softwire.h"
#include "controller.h"
#include "wifi.h"
#include <stdio.h>
#include <string.h>
#define BUS_GPIO 2u
static softwire_t wire;
static uint32_t last_tick;
static bool tick(struct repeating_timer *timer)
{
    (void)timer;
    const uint32_t now=time_us_32();
    bool low=false;
    if ((uint32_t)(now-last_tick)>SOFTWIRE_TICK_US*2u) softwire_timing_fault(&wire);
    else low=softwire_tick(&wire,gpio_get(BUS_GPIO));
    last_tick=now;
    /* Output latch is always zero. Direction selects sink LOW or high-Z. */
    gpio_set_dir(BUS_GPIO,low ? GPIO_OUT : GPIO_IN);
    return true;
}
static bridge_controller_t controller;
static bool usb_owner;
static uint32_t network_session;
static bool send_frame(void *context, const uint8_t frame[BUS_FRAME_SIZE])
{
    (void)context;
    const uint32_t irq=save_and_disable_interrupts();
    const bool queued=softwire_send(&wire,frame,BUS_FRAME_SIZE);
    restore_interrupts(irq);return queued;
}
static void cancel(void *context)
{
    (void)context;
    const uint32_t irq=save_and_disable_interrupts();
    softwire_cancel(&wire);wire.rx_read=wire.rx_write;
    gpio_set_dir(BUS_GPIO,GPIO_IN);restore_interrupts(irq);
}
static void output(void *context, const char *line)
{
    (void)context;
    if (usb_owner) puts(line);
    else bridge_wifi_write(network_session,line);
}
int main(void)
{
    gpio_init(BUS_GPIO);gpio_put(BUS_GPIO,0);gpio_disable_pulls(BUS_GPIO);
    gpio_set_dir(BUS_GPIO,GPIO_IN);
    softwire_init(&wire);stdio_init_all();
    bridge_init(&controller,(bridge_io_t){.send=send_frame,.cancel=cancel,.emit=output});
    bridge_wifi_init();
    struct repeating_timer timer;
    last_tick=time_us_32();
    if (!add_repeating_timer_us(-(int64_t)SOFTWIRE_TICK_US,tick,NULL,&timer)) {
        for (;;) {puts("ERR TIMER");sleep_ms(1000);}
    }
    watchdog_enable(1000,true);
    for (;;) {
        const uint32_t now=to_ms_since_boot(get_absolute_time());
        const bool usb=stdio_usb_connected();
        bridge_wifi_poll(now,usb);
        const uint32_t session=usb ? 0 : bridge_wifi_session();
        if (usb!=usb_owner || session!=network_session) {
            bridge_disconnect(&controller);
            usb_owner=usb;network_session=session;
        }
        const uint32_t irq=save_and_disable_interrupts();
        const bridge_stats_t stats={wire.framing_errors,wire.overruns,wire.collisions,wire.timing_errors};
        restore_interrupts(irq);
        if (usb || session) {
            bridge_poll(&controller,now,stats);
            /* Read after poll, because a timeout/cancel may flush stale RX. */
            uint8_t byte=0;
            const uint32_t lock=save_and_disable_interrupts();
            const bool got=softwire_read(&wire,&byte);
            restore_interrupts(lock);
            if (got) bridge_receive(&controller,byte,now);
            const int ch=usb ? getchar_timeout_us(0) : bridge_wifi_read(session);
            if (ch>=0) bridge_input(&controller,(uint8_t)ch,now);
        } else {
            /* Unsolicited traffic without an owner must not accumulate. */
            const uint32_t lock=save_and_disable_interrupts();
            wire.rx_read=wire.rx_write;restore_interrupts(lock);
        }
        watchdog_update();tight_loop_contents();
    }
}
