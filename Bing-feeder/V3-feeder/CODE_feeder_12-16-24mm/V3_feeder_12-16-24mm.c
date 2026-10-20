#include "stm32f10x.h"
#include "stm32f10x_iwdg.h" 
#include <stdint.h>  // 添加头文件以使用uint32_t类型


//////////////////////////////////////////////////////////////   开始
///////////////////8mm12mm16mm24mm
/////////////////////////////////////////////////////////////


// 全局变量b
uint32_t b=2;
uint32_t a;
uint32_t c=1;
 //定义Flash存储器的地址
#define FLASH_ADDR ((uint32_t)0x08010100) // 使用STM32F103的最后一页作为用户Flash存储区域

// Flash操作函数
void flash_read(uint32_t address, uint32_t *data) {
  *data = *(uint32_t *)address;
}

void flash_erase_page(uint32_t page_address) {
  FLASH_Unlock();
  FLASH_ErasePage(page_address);
  FLASH_Lock();
}

void flash_write(uint32_t address, uint32_t data) {
  FLASH_Unlock();
  FLASH_ProgramWord(address, data);
  FLASH_Lock();
}

// 更新Flash中的数据
void update_flash_data(void) {
  // 读取Flash中的数据并赋值给变量a
  
  flash_read(FLASH_ADDR, &a);

   //判断a的值并进行相应操作
  if (a <  6) {
        a++;  
  } else {
    a = 1;
 }

  // 将更新后的值写入Flash
  flash_erase_page(FLASH_ADDR);
  flash_write(FLASH_ADDR, a);
}



//////////////////////////////////////////////////////////////    结束
///////////////////8mm12mm16mm24mm
/////////////////////////////////////////////////////////////



void delay(uint32_t ms)                    // 延时函数，延时500毫秒
{
    for (uint32_t i = 0; i < ms * 1000000; i++) {       // 空操作，用于消耗时间
       
    }
}


void Iwdg_init() {
    // 允许访问独立看门狗寄存器（解除独立看门狗的封印，允许访问）
    // 向IWDG_KR寄存器写入0x5555,允许寄存器访问
    IWDG_WriteAccessCmd(IWDG_WriteAccess_Enable);
    
    /* IWDG counter clock: LSI/32=32KHz/32=1000Hz */
    IWDG_SetPrescaler(IWDG_Prescaler_32);
    
    // 设置独立看门狗的重载值，决定独立看门狗的超时时间1S
    IWDG_SetReload(1000 - 1);
    
    // 将重载值传递计数器(喂狗操作)
    IWDG_ReloadCounter(); // 将KR寄存器写入oxAAAA
    
    // 使能独立看门狗工作
    IWDG_Enable(); // 向KR寄存器写入0xCCCC
}



void GPIO_Config(void)
{
    GPIO_InitTypeDef GPIO_InitStructure;

    // 使能GPIO时钟
    RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOA | RCC_APB2Periph_AFIO, ENABLE);
	
	RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOB | RCC_APB2Periph_AFIO, ENABLE);



    // 配置PA8和PA12引脚为推挽输出模式
    GPIO_InitStructure.GPIO_Pin = GPIO_Pin_8 | GPIO_Pin_12; // L298N驱动模块的IN1和IN2引脚
    GPIO_InitStructure.GPIO_Mode = GPIO_Mode_Out_PP;
    GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz;
    GPIO_Init(GPIOA, &GPIO_InitStructure);
	
	//.... // 配置PA6和PA7引脚为推挽输出模式
    GPIO_InitStructure.GPIO_Pin = GPIO_Pin_6 | GPIO_Pin_7 ; // L298N驱动模块的IN3和IN4引脚
    GPIO_InitStructure.GPIO_Mode = GPIO_Mode_Out_PP;
    GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz;
    GPIO_Init(GPIOA, &GPIO_InitStructure);
	
	//.... // 配置PB5引脚为推挽输出模式
    GPIO_InitStructure.GPIO_Pin = GPIO_Pin_5 ; // L298N驱动模块的IN3和IN4引脚
    GPIO_InitStructure.GPIO_Mode = GPIO_Mode_Out_PP;
    GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz;
    GPIO_Init(GPIOB, &GPIO_InitStructure);
	

    // 配置PA5和PA3，PA 4引脚为上拉输入模式
    GPIO_InitStructure.GPIO_Pin = GPIO_Pin_5 | GPIO_Pin_3 | GPIO_Pin_4;
    GPIO_InitStructure.GPIO_Mode = GPIO_Mode_IPU;
    GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz;
    GPIO_Init(GPIOA, &GPIO_InitStructure);
	
	
	
	
	
	GPIO_ResetBits(GPIOA, GPIO_Pin_8 | GPIO_Pin_12); // 将IN1和IN2都设置为高电平
}
    

void Motor_Start(void)
{
    // 启动电机
    GPIO_SetBits(GPIOA, GPIO_Pin_6); // 设置IN1为高电平
    GPIO_ResetBits(GPIOA, GPIO_Pin_7); // 设置IN2为低电平
	GPIO_ResetBits(GPIOB, GPIO_Pin_5); // 设置LED2为地电平  亮灯
}

void Motor_Stop(void)
{
    // 停止电机
    GPIO_SetBits(GPIOA, GPIO_Pin_6 | GPIO_Pin_7); // 将IN1和IN2都设置为高电平
	GPIO_SetBits(GPIOB, GPIO_Pin_5); // 设置LED2为高电平  熄灯
}

void EXTI_Config(void)
{
    EXTI_InitTypeDef EXTI_InitStructure;
    NVIC_InitTypeDef NVIC_InitStructure;

    // 配置PA5引脚为外部中断
    GPIO_EXTILineConfig(GPIO_PortSourceGPIOA, GPIO_PinSource5);

    // 配置外部中断
    EXTI_InitStructure.EXTI_Line = EXTI_Line5;
    EXTI_InitStructure.EXTI_Mode = EXTI_Mode_Interrupt;
    EXTI_InitStructure.EXTI_Trigger = EXTI_Trigger_Rising;
    EXTI_InitStructure.EXTI_LineCmd = ENABLE;
    EXTI_Init(&EXTI_InitStructure);

    // 配置中断优先级
    NVIC_InitStructure.NVIC_IRQChannel = EXTI9_5_IRQn;
    NVIC_InitStructure.NVIC_IRQChannelPreemptionPriority = 0x01;
    NVIC_InitStructure.NVIC_IRQChannelSubPriority = 0x01;
    NVIC_InitStructure.NVIC_IRQChannelCmd = ENABLE;
    NVIC_Init(&NVIC_InitStructure);

    // 配置PA3引脚为外部中断
    GPIO_EXTILineConfig(GPIO_PortSourceGPIOA, GPIO_PinSource3);

    // 配置外部中断
    EXTI_InitStructure.EXTI_Line = EXTI_Line3;
    EXTI_InitStructure.EXTI_Trigger = EXTI_Trigger_Rising;
    EXTI_Init(&EXTI_InitStructure);

    // 配置中断优先级
    NVIC_InitStructure.NVIC_IRQChannel = EXTI3_IRQn;
    NVIC_InitStructure.NVIC_IRQChannelPreemptionPriority = 0x01;
    NVIC_InitStructure.NVIC_IRQChannelSubPriority = 0x01;
    NVIC_InitStructure.NVIC_IRQChannelCmd = ENABLE;
    NVIC_Init(&NVIC_InitStructure);
	
	
	 // 配置PA4引脚为外部中断
    GPIO_EXTILineConfig(GPIO_PortSourceGPIOA, GPIO_PinSource4);

    // 配置外部中断
    EXTI_InitStructure.EXTI_Line = EXTI_Line4;
    EXTI_InitStructure.EXTI_Trigger = EXTI_Trigger_Rising;
    EXTI_Init(&EXTI_InitStructure);

    // 配置中断优先级
    NVIC_InitStructure.NVIC_IRQChannel = EXTI4_IRQn;
    NVIC_InitStructure.NVIC_IRQChannelPreemptionPriority = 0x01;
    NVIC_InitStructure.NVIC_IRQChannelSubPriority = 0x01;
    NVIC_InitStructure.NVIC_IRQChannelCmd = ENABLE;
    NVIC_Init(&NVIC_InitStructure);
}

int main(void)
{
	
	
	
	Iwdg_init();    // 初始化独立看门狗
    GPIO_Config();
    EXTI_Config();
	flash_read(FLASH_ADDR, &a);
	
	GPIO_SetBits(GPIOB, GPIO_Pin_5); // 设置LED2为高电平，熄灯
	GPIO_ResetBits(GPIOB, GPIO_Pin_5); // 设置LED2为低电平亮灯
	delay(4);
	GPIO_SetBits(GPIOB, GPIO_Pin_5); // 设置LED2为高电平，熄灯
	
	
	//....// 启动N30电机
    GPIO_SetBits(GPIOA, GPIO_Pin_12); // 设置IN3为高电平
    GPIO_ResetBits(GPIOA, GPIO_Pin_8); // 设置IN4为低电平
	
	// 停止电机
    GPIO_SetBits(GPIOA, GPIO_Pin_6 | GPIO_Pin_7); // 将IN1和IN2都设置为高电平
	
	
	
	
	
    while (1)
    {
		
        // 循环等待中断触发
		
		//将重载值传递计数器(喂狗操作)
	IWDG_ReloadCounter();//将KR寄存器写入oxAAAA, // 通常需要在主循环中定期调用
		
		
		
    }

    return 0;
}

void EXTI9_5_IRQHandler(void)
{
	if (EXTI_GetITStatus(EXTI_Line5) != RESET)
    {
        
        //不要停止N30电机
    //GPIO_SetBits(GPIOA, GPIO_Pin_12); // 设置IN3为高电平
    //GPIO_SetBits(GPIOA, GPIO_Pin_8); // 设置IN4为高电平
		
        Motor_Start();
        EXTI_ClearITPendingBit(EXTI_Line5);
		delay(2);
		EXTI_ClearITPendingBit(EXTI_Line3);
        
      }
}

void EXTI3_IRQHandler(void)
{
	
	
    if (EXTI_GetITStatus(EXTI_Line3) != RESET)
       {
         // 判断b的值
           if (b <= a) {
             b++;
			// Motor_Start(); // 执行停止电机函数 
			  // EXTI_ClearITPendingBit(EXTI_Line5);
			   
			   delay(2);
		       EXTI_ClearITPendingBit(EXTI_Line3);
             
            } else {
              
			 b=1;
		     Motor_Stop(); // 执行停止电机函数	
				

				//// 不用启动N30电机，因为不会停止
		     // delay(2); 我认为不延时，否则会夹住胶带
       //GPIO_SetBits(GPIOA, GPIO_Pin_12); // 设置IN3为高电平
       //GPIO_ResetBits(GPIOA, GPIO_Pin_8); // 设置IN4为低电平			   
			    
           }
            
		    
		
		   
        }

    
}


void EXTI4_IRQHandler(void)
{
	if (EXTI_GetITStatus(EXTI_Line4) != RESET)
    {
        
		// 更新Flash中的数据
            update_flash_data();
		
		    delay(2);
		EXTI_ClearITPendingBit(EXTI_Line4);
        
      }
	
	
}
