/* Candidate STM32F103C8 only. Communications bench build; NO motor commands. */
#include "stm32f1xx.h"
#include "node.h"
#include "softwire.h"
#ifndef FEEDER_ADDRESS
#define FEEDER_ADDRESS 1
#endif
#if FEEDER_ADDRESS < 1 || FEEDER_ADDRESS > BUS_MAX_ADDRESS
#error FEEDER_ADDRESS must be 1..247 and unique on the bench bus
#endif
static softwire_t wire;
static volatile uint32_t milliseconds;
static uint32_t last_cycles;
void SysTick_Handler(void) { ++milliseconds; }
static uint32_t lock(void) { const uint32_t old=__get_PRIMASK(); __disable_irq(); return old; }
static void unlock(uint32_t old) { __set_PRIMASK(old); }
static void release_bus(void) { GPIOA->BSRR=GPIO_BSRR_BS5; }
void TIM2_IRQHandler(void)
{
    TIM2->SR=0;
    const uint32_t now=DWT->CYCCNT;
    bool low=false;
    if ((uint32_t)(now-last_cycles)>64u*SOFTWIRE_TICK_US*2u) softwire_timing_fault(&wire);
    else low=softwire_tick(&wire,(GPIOA->IDR & GPIO_IDR_IDR5)!=0);
    last_cycles=now;
    GPIOA->BSRR=low ? GPIO_BSRR_BR5 : GPIO_BSRR_BS5;
}
static void gpio_mode(unsigned pin,uint32_t mode)
{
    volatile uint32_t *reg=pin<8 ? &GPIOA->CRL : &GPIOA->CRH;
    const unsigned shift=(pin%8u)*4u;
    *reg=(*reg & ~(0xfu<<shift)) | (mode<<shift);
}
static void motor_inhibit(void)
{
    /* Set latch before changing direction. No path ever sets these pins high. */
    GPIOA->BRR=(1u<<6)|(1u<<7)|(1u<<8)|(1u<<12);
    gpio_mode(6,2); gpio_mode(7,2); gpio_mode(8,2); gpio_mode(12,2);
}
static bool clock_init(void)
{
    /* HSI/2 x16 = 64 MHz, APB1 /2. Do not depend on an unverified crystal. */
    RCC->CR |= RCC_CR_HSION;
    uint32_t timeout=1000000;
    while (!(RCC->CR & RCC_CR_HSIRDY) && --timeout) {}
    if (!timeout) return false;
    FLASH->ACR=FLASH_ACR_PRFTBE | FLASH_ACR_LATENCY_2;
    RCC->CFGR=RCC_CFGR_PPRE1_DIV2 | RCC_CFGR_PLLMULL16;
    RCC->CR |= RCC_CR_PLLON;
    timeout=1000000;
    while (!(RCC->CR & RCC_CR_PLLRDY) && --timeout) {}
    if (!timeout) return false;
    RCC->CFGR |= RCC_CFGR_SW_PLL;
    timeout=1000000;
    while ((RCC->CFGR & RCC_CFGR_SWS)!=RCC_CFGR_SWS_PLL && --timeout) {}
    SystemCoreClockUpdate();
    return timeout && SystemCoreClock==64000000u;
}
void HardFault_Handler(void)
{
    motor_inhibit(); release_bus();
    for (;;) {} /* Independent watchdog resets; no watchdog reload in fault. */
}
int main(void)
{
    RCC->APB2ENR |= RCC_APB2ENR_IOPAEN | RCC_APB2ENR_AFIOEN;
    motor_inhibit();
    /* PA5 open-drain, 2 MHz mode: HIGH is electrically released. */
    release_bus(); gpio_mode(5,6);
    /* PA3 optical and PA4 button: input with pull-up; PA11 remains untouched. */
    GPIOA->BSRR=(1u<<3)|(1u<<4); gpio_mode(3,8); gpio_mode(4,8);
    if (!clock_init()) for (;;) { __WFI(); }
    (void)SysTick_Config(SystemCoreClock/1000u);
    NVIC_SetPriority(SysTick_IRQn,2);
    softwire_init(&wire);
    feeder_node_t node;
    uint8_t uid[12];
    for (unsigned i=0; i<12; ++i) uid[i]=((const volatile uint8_t *)UID_BASE)[i];
    if (!feeder_node_init(&node,FEEDER_ADDRESS,uid)) for (;;) { __WFI(); }
    bus_parser_t parser; bus_parser_init(&parser);
    RCC->APB1ENR |= RCC_APB1ENR_TIM2EN;
    TIM2->PSC=63; TIM2->ARR=SOFTWIRE_TICK_US-1;
    TIM2->EGR=TIM_EGR_UG; TIM2->SR=0; TIM2->DIER=TIM_DIER_UIE;
    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
    DWT->CYCCNT=0; DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
    last_cycles=DWT->CYCCNT;
    NVIC_SetPriority(TIM2_IRQn,0); NVIC_EnableIRQ(TIM2_IRQn); TIM2->CR1=TIM_CR1_CEN;
    IWDG->KR=0x5555; IWDG->PR=4; IWDG->RLR=625; IWDG->KR=0xaaaa; IWDG->KR=0xcccc;
    uint32_t errors=0;
    for (;;) {
        uint8_t byte=0;
        const uint32_t saved=lock();
        const uint32_t faults=wire.overruns+wire.framing_errors+wire.collisions+wire.timing_errors;
        const bool received=softwire_read(&wire,&byte);
        unlock(saved);
        if (faults!=errors) { bus_parser_init(&parser); errors=faults; }
        bus_packet_t request,reply;
        if (received && bus_parser_byte(&parser,byte,milliseconds,&request)) {
            const uint8_t inputs=(uint8_t)((GPIOA->IDR>>3)&7u);
            if (feeder_node_request(&node,&request,milliseconds,inputs,&reply)) {
                uint8_t frame[BUS_FRAME_SIZE]; bus_encode(&reply,frame);
                const uint32_t held=lock();
                (void)softwire_send(&wire,frame,sizeof(frame));
                unlock(held);
            }
        }
        /* A failed reply cannot stay queued forever on a grounded bus. */
        static uint32_t pending_since;
        const uint32_t held=lock();
        if (!softwire_busy(&wire)) pending_since=milliseconds;
        else if ((uint32_t)(milliseconds-pending_since)>100u) { softwire_cancel(&wire); release_bus(); }
        unlock(held);
        IWDG->KR=0xaaaa;
    }
}
