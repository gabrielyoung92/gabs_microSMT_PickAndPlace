// Derived from MicroSMT/Bing-feeder V485 firmware. Local HAL/PlatformIO port.
// Original authors retain credit; see README.md and CHANGELOG.md.
//
// Owns the MCU clock, GPIO startup levels, interrupt routing and delay timing.
// Pin assignments come from config.h; variant-specific idle levels are below.

#include "board.h"
#include "config.h"

// Keep output speed and input bias consistent across the software bus drivers.
// The caller must enable the GPIO port clock before using this helper.
void Board_ConfigurePin(GPIO_TypeDef* port, uint16_t pins, uint32_t mode) {
    GPIO_InitTypeDef pin = {0};
    pin.Pin = pins;
    pin.Mode = mode;
    pin.Pull = GPIO_NOPULL;  // Retain floating inputs; board supplies input bias.
    pin.Speed = GPIO_SPEED_FREQ_HIGH;
    HAL_GPIO_Init(port, &pin);
}

// Unrecoverable setup failure: stop both motor channels, light the LED and halt.
// The application watchdog resets the processor if execution stays here.
void Board_ErrorHandler(void) {
    // GPIO_Config() runs before clock/UART setup, so motor outputs are driven.
    __disable_irq();
    HAL_GPIO_WritePin(MOTOR_PORT, MOTOR_ALL_PINS, GPIO_PIN_SET);
    LED_ON();
    while (1) __NOP();
}

// Configure the assumed external crystal/PLL, then select it with bus dividers.
// HSE_VALUE in platformio.ini must match this board's actual crystal frequency.
static void SystemClock_Config(void) {
    // 8 MHz crystal -> PLL x9 -> 72 MHz CPU; APB1 36 MHz, APB2 72 MHz.
    RCC_OscInitTypeDef oscillator = {0};
    oscillator.OscillatorType = RCC_OSCILLATORTYPE_HSE;
    oscillator.HSEState = RCC_HSE_ON;
    oscillator.HSEPredivValue = RCC_HSE_PREDIV_DIV1;
    oscillator.HSIState = RCC_HSI_ON;
    oscillator.PLL.PLLState = RCC_PLL_ON;
    oscillator.PLL.PLLSource = RCC_PLLSOURCE_HSE;
    oscillator.PLL.PLLMUL = RCC_PLL_MUL9;
    if (HAL_RCC_OscConfig(&oscillator) != HAL_OK) Board_ErrorHandler();

    RCC_ClkInitTypeDef clocks = {0};
    clocks.ClockType = RCC_CLOCKTYPE_SYSCLK | RCC_CLOCKTYPE_HCLK |
                       RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;
    clocks.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
    clocks.AHBCLKDivider = RCC_SYSCLK_DIV1;
    clocks.APB1CLKDivider = RCC_HCLK_DIV2;
    clocks.APB2CLKDivider = RCC_HCLK_DIV1;
    if (HAL_RCC_ClockConfig(&clocks, FLASH_LATENCY_2) != HAL_OK) Board_ErrorHandler();
}

// Enable the Cortex-M3 free-running counter once, after setting the CPU clock.
static void Delay_Init(void) {
    // Cortex-M3 cycle counting replaces the compiler-dependent empty/NOP loop.
    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
    DWT->CYCCNT = 0;
    DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
}

// Wait on the HAL tick without masking interrupts. Unsigned subtraction handles
// tick wraparound; this cannot progress if SysTick is prevented from running.
void delay_ms(uint32_t ms) {
    uint32_t start = HAL_GetTick();
    while (HAL_GetTick() - start < ms);
}

// Use CPU cycles for short bus timing delays. Interrupts may extend the wait;
// this is not a hardware waveform generator or a long-duration sleep.
void delay_us(uint32_t us) {
    uint32_t startedAt = DWT->CYCCNT;
    uint32_t cycles = us * (SystemCoreClock / 1000000U);
    while ((uint32_t)(DWT->CYCCNT - startedAt) < cycles) __NOP();
}

// Safe idle for startup/loader. Only Feeder_Tick may start the peel motor.
void Board_MotorIdle(void) {
    HAL_GPIO_WritePin(MOTOR_PORT, MOTOR_ALL_PINS, GPIO_PIN_SET);
}

// Establish output levels before setting the clock/UART. Existing inputs retain
// their board bias; the PB6 tension input also uses an internal pull-up.
static void GPIO_Config(void) {
    __HAL_RCC_GPIOA_CLK_ENABLE();
    __HAL_RCC_GPIOB_CLK_ENABLE();
    __HAL_RCC_AFIO_CLK_ENABLE();
    HAL_NVIC_SetPriorityGrouping(NVIC_PRIORITYGROUP_2);

    // Preload the inactive motor levels before enabling the output drivers.
    HAL_GPIO_WritePin(MOTOR_PORT, MOTOR_ALL_PINS, GPIO_PIN_SET);
    Board_ConfigurePin(MOTOR_PORT, MOTOR_ALL_PINS, GPIO_MODE_OUTPUT_PP);
    Board_MotorIdle();
    // Release the shared RS485 bus from early startup, including the loader's
    // immediate app-jump path which never initialises the UART itself.
    HAL_GPIO_WritePin(RS485_DIR_PORT, RS485_DIR_PIN, GPIO_PIN_RESET);
    Board_ConfigurePin(RS485_DIR_PORT, RS485_DIR_PIN, GPIO_MODE_OUTPUT_PP);
    LED_OFF();
    Board_ConfigurePin(LED_PORT, LED_PIN, GPIO_MODE_OUTPUT_PP);
    Board_ConfigurePin(COUNT_PORT, COUNT_PIN, GPIO_MODE_INPUT);
    Board_ConfigurePin(BUTTON_PORT, BUTTON_PIN, GPIO_MODE_INPUT);
    Board_ConfigurePin(MENU_BUTTON_PORT, MENU_BUTTON_PIN, GPIO_MODE_INPUT);
    GPIO_InitTypeDef tension = {0};
    tension.Pin = PEEL_SWITCH_PIN;
    tension.Mode = GPIO_MODE_INPUT;
    tension.Pull = GPIO_PULLUP;
    HAL_GPIO_Init(PEEL_SWITCH_PORT, &tension);
}

// Clear stale count edges before enabling EXTI3. UART/SysTick have higher priority.
void Board_EnableFeedInterrupts(void) {
    Board_ConfigurePin(COUNT_PORT, COUNT_PIN, GPIO_MODE_IT_RISING);
    __HAL_GPIO_EXTI_CLEAR_IT(COUNT_PIN);
    HAL_NVIC_SetPriority(EXTI3_IRQn, 1, 1);
    HAL_NVIC_EnableIRQ(EXTI3_IRQn);
}

#if !FEEDER_BOOTLOADER
void Board_WatchdogFeed(void) {
    IWDG->KR = 0xAAAAU;
}

// Independent LSI clock: nominally 4 seconds (actual time follows LSI tolerance).
static void Watchdog_Start(void) {
    IWDG->KR = 0xCCCCU;
    IWDG->KR = 0x5555U;
    IWDG->PR = 4U;       // LSI / 64
    IWDG->RLR = 2499U;
    while (IWDG->SR) {}  // A stuck register update must also cause a reset.
    Board_WatchdogFeed();
}
#endif

// Prepare the hardware services required by every other module. Startup code
// has already run SystemInit; apply only this board's clock configuration here.
void Board_Init(void) {
    HAL_StatusTypeDef status = HAL_Init();
    GPIO_Config();
#if !FEEDER_BOOTLOADER
    Watchdog_Start();
#endif
    if (status != HAL_OK) Board_ErrorHandler();
    SystemClock_Config();
    Delay_Init();
    // ClockConfig reinitialises SysTick. Keep it above feeder EXTI priority.
    HAL_NVIC_SetPriority(SysTick_IRQn, 0, 0);
}
