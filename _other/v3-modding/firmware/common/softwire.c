#include "softwire.h"
#include <string.h>
void softwire_init(softwire_t *w) { memset(w,0,sizeof(*w)); }
bool softwire_busy(const softwire_t *w) { return w->transmitting || w->tx_length!=0; }
void softwire_cancel(softwire_t *w)
{
    w->transmitting=false; w->tx_length=0; w->drive_low=false;
    w->rx_state=0; w->idle_high=0;
}
void softwire_timing_fault(softwire_t *w)
{
    ++w->timing_errors; softwire_cancel(w); w->rx_read=w->rx_write;
}
bool softwire_send(softwire_t *w,const uint8_t *data,size_t length)
{
    if (!length || length>SOFTWIRE_QUEUE || softwire_busy(w)) return false;
    memcpy(w->tx,data,length); w->tx_length=(uint8_t)length;
    w->tx_index=0; w->tx_bit=0; w->tx_phase=0;
    return true;
}
bool softwire_read(softwire_t *w,uint8_t *byte)
{
    if (w->rx_read==w->rx_write) return false;
    *byte=w->rx[w->rx_read]; w->rx_read=(uint8_t)((w->rx_read+1u)%SOFTWIRE_QUEUE);
    return true;
}
static bool bit_is_low(const softwire_t *w)
{
    if (w->tx_bit==0) return true;
    if (w->tx_bit==9) return false;
    return (w->tx[w->tx_index] & (uint8_t)(1u<<(w->tx_bit-1u)))==0;
}
bool softwire_tick(softwire_t *w,bool high)
{
    if (w->transmitting) {
        /* Check after a half bit for a short or another transmitter. */
        if (w->tx_phase==2 && high==w->drive_low) {
            ++w->collisions; softwire_cancel(w); return false;
        }
        if (++w->tx_phase==4) {
            w->tx_phase=0;
            if (++w->tx_bit==10) {
                w->tx_bit=0;
                if (++w->tx_index==w->tx_length) {
                    softwire_cancel(w); return false;
                }
            }
            w->drive_low=bit_is_low(w);
        }
        return w->drive_low;
    }
    if (high) { if (w->idle_high<255) ++w->idle_high; }
    else w->idle_high=0;
    if (w->tx_length && w->rx_state==0 && w->idle_high>=8) {
        w->transmitting=true; w->drive_low=true; w->tx_phase=0; return true;
    }
    if (w->rx_state==0) {
        if (!high) { w->rx_state=1; w->rx_wait=2; }
    } else if (--w->rx_wait==0) {
        if (w->rx_state==1) {
            if (high) { w->rx_state=0; }
            else { w->rx_state=2; w->rx_wait=4; w->rx_bit=0; w->rx_value=0; }
        } else if (w->rx_state==2) {
            if (high) w->rx_value |= (uint8_t)(1u<<w->rx_bit);
            w->rx_wait=4;
            if (++w->rx_bit==8) w->rx_state=3;
        } else {
            if (high) {
                const uint8_t next=(uint8_t)((w->rx_write+1u)%SOFTWIRE_QUEUE);
                if (next==w->rx_read) ++w->overruns;
                else { w->rx[w->rx_write]=w->rx_value; w->rx_write=next; }
            } else ++w->framing_errors;
            w->rx_state=0;
        }
    }
    w->drive_low=false;
    return false;
}
