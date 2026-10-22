#!/usr/bin/env python3
"""Offline checks of the actual feeder/RS485/packet sources; Python and gcc required.
No serial ports are opened. All generated files stay in a temporary directory.
"""
from pathlib import Path
import re,subprocess,tempfile
p=Path(__file__).resolve().parents[1]
# Minimal temporary hardware substitutes; production modules are included intact.
hal='''#pragma once
#include <stdint.h>
#include <stddef.h>
typedef struct {uint16_t levels;} GPIO_TypeDef;
extern GPIO_TypeDef testA,testB;
#define GPIOA (&testA)
#define GPIOB (&testB)
#define GPIO_PIN_RESET 0
#define GPIO_PIN_SET 1
#define RESET 0
#define HAL_OK 0
#define GPIO_MODE_AF_PP 1
#define GPIO_MODE_INPUT 2
#define GPIO_MODE_OUTPUT_PP 3
#define UART_WORDLENGTH_8B 0
#define UART_STOPBITS_1 0
#define UART_PARITY_NONE 0
#define UART_MODE_TX_RX 0
#define UART_HWCONTROL_NONE 0
#define UART_OVERSAMPLING_16 0
#define USART1_IRQn 0
#define USART_SR_RXNE (1U<<5)
#define USART_SR_ORE (1U<<3)
#define USART_SR_FE (1U<<1)
#define USART_SR_NE (1U<<2)
#define USART_SR_PE (1U<<0)
#define UART_FLAG_TXE (1U<<7)
#define UART_FLAG_TC (1U<<6)
#define UART_IT_RXNE 0
#define __HAL_RCC_USART1_CLK_ENABLE() ((void)0)
#define __HAL_UART_GET_FLAG(h,f) (1)
#define __HAL_UART_CLEAR_OREFLAG(h) ((void)(h))
#define __HAL_UART_ENABLE_IT(h,f) ((void)(h))
#define __HAL_GPIO_EXTI_GET_IT(pin) (pending & (pin))
#define __HAL_GPIO_EXTI_CLEAR_IT(pin) (pending &= ~(pin))
#define __DMB() __asm__ volatile("" ::: "memory")
typedef struct {volatile uint32_t SR,DR;} USART_TypeDef;
extern USART_TypeDef testUart;
#define USART1 (&testUart)
typedef struct {uint32_t BaudRate,WordLength,StopBits,Parity,Mode,HwFlowCtl,OverSampling;} UART_InitTypeDef;
typedef struct {USART_TypeDef* Instance;UART_InitTypeDef Init;} UART_HandleTypeDef;
extern uint16_t pending;
void HAL_GPIO_WritePin(GPIO_TypeDef*,uint16_t,int);
int HAL_GPIO_ReadPin(GPIO_TypeDef*,uint16_t);
uint32_t HAL_GetTick(void);
uint32_t HAL_GetUIDw0(void);
uint32_t HAL_GetUIDw1(void);
uint32_t HAL_GetUIDw2(void);
uint32_t __get_PRIMASK(void);
void __disable_irq(void);
void __set_PRIMASK(uint32_t);
int HAL_UART_Init(UART_HandleTypeDef*);
void HAL_NVIC_SetPriority(int,int,int);
void HAL_NVIC_EnableIRQ(int);
void HAL_NVIC_DisableIRQ(int);
int HAL_UART_DeInit(UART_HandleTypeDef*);
void NVIC_SystemReset(void);
'''+''.join(f'#define GPIO_PIN_{n} (1U<<{n})\n' for n in range(16))
idle=re.search(r'void Board_MotorIdle\(void\) \{.*?^\}',(p/'src/board.c').read_text(),re.M|re.S).group()
app='''#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "FEEDER_PATH"
GPIO_TypeDef testA,testB;
USART_TypeDef testUart;
uint16_t pending;
static uint32_t now,mask;
static int context,starts,displayCalls,renderDepth,lastNumber;
static int queued,address,count,injectAck,injectStartup,injectPulse,injectRender;
static uint8_t memory[256]={7,3};
static int resetCalls,failEEPROM;
static int failReadOffset=-1,settingWrites,failReadback;
static const char* updateLine;
static char response[80];
static void dispatch(void) {
 if(mask)return;
 int old=context;
 if(pending&TRIGGER_PIN){context=1;EXTI9_5_IRQHandler();}
 if(pending&COUNT_PIN){context=2;EXTI3_IRQHandler();}
 context=old;
}
static void trigger(void){pending|=TRIGGER_PIN;dispatch();}
static void pulse(void){pending|=COUNT_PIN;dispatch();}
uint32_t __get_PRIMASK(void){return mask;}
void __disable_irq(void){mask=1;}
void __set_PRIMASK(uint32_t value){mask=value;dispatch();}
void HAL_GPIO_WritePin(GPIO_TypeDef* port,uint16_t pins,int level){
 if(level)port->levels|=pins;else port->levels&=~pins;
 if(port==MOTOR_PORT&&(pins&MOTOR_INDEX_B_PIN)&&!level){
  assert(mask && feedState==FEED_RUNNING && motorCount>=1);starts++;
  if(injectPulse){injectPulse=0;pending|=COUNT_PIN;}
 }
}
int HAL_GPIO_ReadPin(GPIO_TypeDef* port,uint16_t pins){return !!(port->levels&pins);}
uint32_t HAL_GetTick(void){return now;}
uint32_t HAL_GetUIDw0(void){return 0x11111111U;}
uint32_t HAL_GetUIDw1(void){return 0x22222222U;}
uint32_t HAL_GetUIDw2(void){return 0x33333333U;}
void delay_ms(uint32_t ms){
 assert(!mask && context==0);
 if((injectAck&&ms==ACK_TURNAROUND_MS)||(injectStartup&&ms==150)){
  if(ms==ACK_TURNAROUND_MS)injectAck=0;
  trigger();
 }
 while(ms--){now++;int old=context;context=3;Feeder_Tick();context=old;}
}
void delay_us(uint32_t us){(void)us;}
void CH455_RefreshNum(uint16_t value){
 assert(context==0&&!renderDepth&&value<=99);renderDepth++;displayCalls++;lastNumber=value;
 if(injectRender){injectRender=0;pulse();}
 renderDepth--;
}
void CH455_SetDisplay(uint8_t digit,uint8_t segments){
 (void)digit;(void)segments;assert(context==0&&!renderDepth);displayCalls++;
}
uint8_t EEPROM_WriteByte(uint8_t offset,uint8_t value){settingWrites++;if(failEEPROM)return 0;memory[offset]=value;delay_ms(5);return !failReadback;}
uint8_t EEPROM_ReadChecked(uint8_t offset,uint8_t* value){if(failEEPROM)return 0;if(offset==failReadOffset){failReadOffset=-1;return 0;}*value=memory[offset];return 1;}
void RS485_Init(void){}
void RS485_SendString(const char* text){assert(context==0);snprintf(response,sizeof(response),"%s",text);}
uint8_t RS485_ReadLine(char* line,uint16_t size){if(updateLine){snprintf(line,size,"%s",updateLine);updateLine=NULL;return 1;}if(!queued)return 0;queued=0;snprintf(line,size,"N%d F%d",address,count);return 1;}
uint8_t RS485_ParseFeedCommand(const char* line,int* addr,int* n){return sscanf(line,"N%d F%d",addr,n)==2;}
void NVIC_SystemReset(void){resetCalls++;assert(!feedReady&&feedState==FEED_FAULT);assert((testA.levels&MOTOR_ALL_PINS)==MOTOR_ALL_PINS);assert(memory[BOOT_STATE_ADDR]==BOOT_REQUESTED);}
void Board_EnableFeedInterrupts(void){assert(mask && !feedReady);pending=0;}
MOTOR_IDLE
#include "boot.c"
static void command(int addr,int n){queued=1;address=addr;count=n;response[0]=0;ProcessRS485();}
static void idle(void){
 assert((testA.levels&(MOTOR_INDEX_A_PIN|MOTOR_INDEX_B_PIN))==(MOTOR_INDEX_A_PIN|MOTOR_INDEX_B_PIN));
 assert(testA.levels&MOTOR_PEEL_B_PIN);
 assert(testA.levels&MOTOR_PEEL_A_PIN);
}
static void press(uint16_t pin,uint32_t duration){
 testA.levels&=~pin;KeyScan();delay_ms(BUTTON_DEBOUNCE_MS);KeyScan();delay_ms(duration);KeyScan();
 testA.levels|=pin;KeyScan();delay_ms(BUTTON_DEBOUNCE_MS);KeyScan();
}
static void framedAt(uint8_t destination,const char* body){
 char line[RX_BUFFER_SIZE];int n=snprintf(line,sizeof(line),"B%02u %s",destination,body);
 snprintf(line+n,sizeof(line)-(size_t)n," %08X",Boot_Crc32(line,(size_t)n));
 updateLine=line;response[0]=0;ProcessRS485();
}
static void framed(const char* body){framedAt(7,body);}
int main(int argc,char** argv){
 assert(argc==2);testA.levels=0xffff;
 if(!strcmp(argv[1],"zero"))memory[1]=0;
 if(!strcmp(argv[1],"heldstartup"))testA.levels&=~BUTTON_PIN;
 if(!strcmp(argv[1],"startup"))injectStartup=1;
 if(!strcmp(argv[1],"readfail"))failReadOffset=0;
 if(!strcmp(argv[1],"countreadfail"))failReadOffset=1;
 if(!strcmp(argv[1],"blank")){memory[0]=memory[1]=0xff;}
 if(!strncmp(argv[1],"unassigned",10))memory[0]=0;
 if(!strcmp(argv[1],"bootblank")||!strcmp(argv[1],"bootblankfail")){
  uint8_t id=99;memory[0]=0xff;
  if(!strcmp(argv[1],"bootblankfail")){
   failReadback=1;assert(!Boot_ReadId(&id)&&id==99&&memory[0]==0);failReadback=0;
  }
  assert(Boot_ReadId(&id)&&id==0&&memory[0]==0);return 0;
 }
 if(!strcmp(argv[1],"invalidid")){memory[0]=100;assert(!LoadSettings()&&memory[0]==100&&!settingWrites);return 0;}
 Feeder_Init();assert(feedReady&&feedState==FEED_IDLE&&!starts);idle();
 assert(strstr(response,"v" FIRMWARE_VERSION " " FEEDER_VARIANT));injectStartup=0;
 
if(!strcmp(argv[1],"readfail")||!strcmp(argv[1],"countreadfail")){
 assert(currentAddr==7&&memory[0]==7&&currentCount==3&&!settingWrites);
}else if(!strcmp(argv[1],"blank")||!strncmp(argv[1],"unassigned",10)){
 assert(currentAddr==0&&memory[0]==0);
 if(!strcmp(argv[1],"blank"))assert(currentCount==1&&memory[1]==1);
 int writes=settingWrites;
 // Even with a closed tension switch, neither variant may run either motor.
 testA.levels&=~PEEL_SWITCH_PIN;
 delay_ms(PEEL_RESTART_MS+PEEL_DEBOUNCE_MS);assert(!peelRunning&&!Motor_Reserve(1));idle();
 trigger();press(BUTTON_PIN,10);command(0,1);assert(!starts);idle();
 framedAt(0,"FEED 12345678 00000001 00000001");assert(strstr(response,"B00 FAULT")&&!starts);
 uiLastAction=now;uiBlink=0;RefreshDisplay();assert(lastNumber==0);
 delay_ms(UI_BLINK_MS);KeyScan();assert(uiBlink&&displayDirty);
 int before=displayCalls;RefreshDisplay();assert(displayCalls==before+2);
 delay_ms(UI_BLINK_MS);KeyScan();assert(!uiBlink&&displayDirty);
 before=displayCalls;RefreshDisplay();assert(displayCalls==before+1&&lastNumber==0);
 assert(settingWrites==writes&&!peelRunning&&!starts);idle();
 if(!strcmp(argv[1],"unassignedboot")){
  press(BUTTON_PIN,2*BUTTON_HOLD_MS+50);assert(resetCalls==1&&memory[0]==0);
 }else if(!strcmp(argv[1],"unassignedremote")){
  press(BUTTON_PIN,BUTTON_HOLD_MS+50);assert(mode==MODE_ASSIGN);
  framedAt(0,"SETID 12345678 11111111 22222222 33333333 00000000");
  assert(strstr(response,"ERROR ID")&&currentAddr==0&&mode==MODE_ASSIGN);
  framedAt(0,"SETID 12345678 11111111 22222222 33333333 00000063");
  assert(strstr(response,"B00 ID 12345678 00000063")&&currentAddr==99&&memory[0]==99);
 }else{
  press(BUTTON_PIN,3*BUTTON_HOLD_MS+50);assert(mode==MODE_ADDR&&editValue==1);
  delay_ms(UI_TIMEOUT_MS);KeyScan();assert(currentAddr==0&&mode==MODE_NORMAL&&!starts);
  press(BUTTON_PIN,3*BUTTON_HOLD_MS+50);press(BUTTON_PIN,BUTTON_HOLD_MS+50);
  assert(currentAddr==1&&memory[0]==1&&mode==MODE_NORMAL);
 }
 if(currentAddr){
  uiBlink=1;int before=displayCalls;RefreshDisplay();assert(displayCalls==before+1&&lastNumber==currentAddr);
  assert(Motor_Reserve(1));Motor_Start();assert(starts==1);pulse();assert(feedState==FEED_IDLE);
 }
}else if(!strcmp(argv[1],"savefail")||!strcmp(argv[1],"readbackfail")){
 mode=MODE_ADDR;editValue=8;buttonReady=1;
 if(!strcmp(argv[1],"readbackfail"))failReadback=1;else failEEPROM=1;
 press(BUTTON_PIN,BUTTON_HOLD_MS+50);assert(currentAddr==7&&settingsFault&&!feedReady&&feedState==FEED_FAULT);
 assert(memory[0]==(failReadback?8:7));
 assert((testA.levels&MOTOR_ALL_PINS)==MOTOR_ALL_PINS);
 int before=starts;trigger();command(7,2);assert(starts==before&&!response[0]);
 char line[100];int n=sprintf(line,"B07 BOOT");sprintf(line+n," %08X",Boot_Crc32(line,n));
 updateLine=line;ProcessRS485();assert(!resetCalls);Feeder_Run();
 assert((testA.levels&MOTOR_ALL_PINS)==MOTOR_ALL_PINS);
}else if(!strcmp(argv[1],"buttons")){
 int writes=settingWrites;
 // Short PA4 tap advances; PA2 is never interpreted as a button.
 press(PEEL_SWITCH_PIN,10);assert(!starts&&mode==MODE_NORMAL);
 press(BUTTON_PIN,10);assert(starts==1&&motorCount==currentCount);
 while(feedState==FEED_RUNNING)pulse();idle();
 // A press starting during a feed cannot trigger a second feed on release.
 assert(Motor_Reserve(1));Motor_Start();
 testA.levels&=~BUTTON_PIN;KeyScan();delay_ms(BUTTON_DEBOUNCE_MS);KeyScan();
 pulse();testA.levels|=BUTTON_PIN;KeyScan();delay_ms(BUTTON_DEBOUNCE_MS);KeyScan();
 assert(starts==2&&mode==MODE_NORMAL);
 // One scan of contact bounce must do nothing.
 testA.levels&=~BUTTON_PIN;KeyScan();testA.levels|=BUTTON_PIN;KeyScan();
 delay_ms(BUTTON_DEBOUNCE_MS);KeyScan();assert(starts==2);
 // A long press selects 03, without advancing on release (also across wrap).
 now=UINT32_MAX-100U;press(BUTTON_PIN,3*BUTTON_HOLD_MS+50);
 assert(mode==MODE_ADDR&&editValue==7&&starts==2);
 trigger();command(7,1);assert(starts==2&&strstr(response,"Busy"));
 framed("FEED 12345678 00000001 00000001");assert(strstr(response,"BUSY"));
 press(BUTTON_PIN,10);assert(editValue==8&&currentAddr==7&&settingWrites==writes);
 press(BUTTON_PIN,BUTTON_HOLD_MS+50);assert(mode==MODE_NORMAL&&currentAddr==8&&memory[0]==8&&starts==2);
 press(BUTTON_PIN,4*BUTTON_HOLD_MS+50);assert(mode==MODE_COUNT&&editValue==3);
 editValue=99;press(BUTTON_PIN,10);assert(editValue==COUNT_MIN&&currentCount==3);
 press(BUTTON_PIN,BUTTON_HOLD_MS+50);assert(mode==MODE_NORMAL&&currentCount==COUNT_MIN&&memory[1]==COUNT_MIN);
 // Menu selections wrap; editing expires without any EEPROM write.
 press(BUTTON_PIN,7*BUTTON_HOLD_MS+50);assert(mode==MODE_ADDR);
 writes=settingWrites;editValue=99;press(BUTTON_PIN,10);assert(editValue==1);
 delay_ms(UI_TIMEOUT_MS);KeyScan();assert(mode==MODE_NORMAL&&currentAddr==8&&settingWrites==writes);
 // While held in an editor, timeout cannot return to normal and feed on release.
 press(BUTTON_PIN,3*BUTTON_HOLD_MS+50);assert(mode==MODE_ADDR);
 press(BUTTON_PIN,UI_TIMEOUT_MS+100);assert(mode==MODE_NORMAL&&starts==2);
 // Menu 01 arms only that feeder; a long press can cancel it.
 press(BUTTON_PIN,BUTTON_HOLD_MS+50);assert(mode==MODE_ASSIGN);
 framedAt(currentAddr,"IDENT 12345678");assert(strstr(response,"IDENT 12345678 11111111 22222222 33333333 00000001"));
 press(BUTTON_PIN,BUTTON_HOLD_MS+50);assert(mode==MODE_NORMAL&&starts==2);
}else if(!strcmp(argv[1],"heldstartup")){
 assert(!buttonReady);KeyScan();delay_ms(4*BUTTON_HOLD_MS);KeyScan();assert(mode==MODE_NORMAL&&!starts);
 testA.levels|=BUTTON_PIN;KeyScan();delay_ms(BUTTON_DEBOUNCE_MS);KeyScan();assert(buttonReady&&!starts);
 press(BUTTON_PIN,10);assert(starts==1);
}else if(!strcmp(argv[1],"menuboot")){
 press(BUTTON_PIN,2*BUTTON_HOLD_MS+50);assert(resetCalls==1&&!starts);
  }else if(!strcmp(argv[1],"menutiming")){
 now=UINT32_MAX-100U;
 testA.levels&=~BUTTON_PIN;KeyScan();delay_ms(BUTTON_DEBOUNCE_MS);KeyScan();
 delay_ms(BUTTON_HOLD_MS-1);KeyScan();assert(mode==MODE_NORMAL);
 delay_ms(1);KeyScan();assert(mode==MODE_MENU&&menuItem==1);
 delay_ms(BUTTON_HOLD_MS);KeyScan();assert(menuItem==2);
 delay_ms(BUTTON_HOLD_MS);KeyScan();assert(menuItem==3);
 testA.levels|=BUTTON_PIN;KeyScan();delay_ms(BUTTON_DEBOUNCE_MS);KeyScan();assert(mode==MODE_ADDR&&!starts);
 delay_ms(UI_BLINK_MS);KeyScan();assert(uiBlink);int before=displayCalls;RefreshDisplay();assert(displayCalls==before+2);
 delay_ms(UI_BLINK_MS);KeyScan();assert(!uiBlink);before=displayCalls;RefreshDisplay();assert(displayCalls==before+1);
}else if(!strcmp(argv[1],"menubootfail")){
 failReadback=1;press(BUTTON_PIN,2*BUTTON_HOLD_MS+50);assert(!resetCalls&&settingsFault&&!starts);
 assert((testA.levels&MOTOR_ALL_PINS)==MOTOR_ALL_PINS);
}else if(!strcmp(argv[1],"menufault")){
 Motor_Fault();press(BUTTON_PIN,3*BUTTON_HOLD_MS+50);assert(mode==MODE_NORMAL&&!resetCalls);
 press(BUTTON_PIN,2*BUTTON_HOLD_MS+50);assert(resetCalls==1&&!starts);
}else if(!strcmp(argv[1],"assignheld")){
 press(BUTTON_PIN,BUTTON_HOLD_MS+50);assert(mode==MODE_ASSIGN);
 testA.levels&=~BUTTON_PIN;KeyScan();delay_ms(BUTTON_DEBOUNCE_MS);KeyScan();assert(buttonDown);
 framed("SETID 12345678 11111111 22222222 33333333 00000008");assert(currentAddr==8&&mode==MODE_NORMAL);
 testA.levels|=BUTTON_PIN;KeyScan();delay_ms(BUTTON_DEBOUNCE_MS);KeyScan();assert(!starts);
}else if(!strcmp(argv[1],"menubusy")){
 assert(Motor_Reserve(1));Motor_Start();press(BUTTON_PIN,3*BUTTON_HOLD_MS+50);
 assert(mode==MODE_NORMAL&&feedState==FEED_RUNNING&&starts==1);pulse();
}else if(!strcmp(argv[1],"assign")){
 framed("IDENT 12345678");assert(strstr(response,"IDENT 12345678 11111111 22222222 33333333 00000000"));
 framed("SETID 12345678 11111111 22222222 33333333 00000008");assert(strstr(response,"ERROR NOTARMED")&&memory[0]==7);
 press(BUTTON_PIN,BUTTON_HOLD_MS+50);assert(mode==MODE_ASSIGN);
 framed("SETID 12345678 11111112 22222222 33333333 00000008");assert(!response[0]&&currentAddr==7);
 const char* bad[]={"SETID 12345678 11111111 22222222 33333333", "SETID 12345678 11111111 22222222 33333333 00000008x", "SETID 1234 11111111 22222222 33333333 00000008"};
 for(unsigned i=0;i<sizeof(bad)/sizeof(*bad);i++){framed(bad[i]);assert(!response[0]&&currentAddr==7);}
 framed("SETID 12345678 11111111 22222222 33333333 00000064");assert(strstr(response,"ERROR ID")&&currentAddr==7);
 framed("SETID 12345678 11111111 22222222 33333333 00000008");
 assert(strstr(response,"B07 ID 12345678 00000008")&&currentAddr==8&&memory[0]==8&&mode==MODE_NORMAL);
 framed("SETID 12345678 11111111 22222222 33333333 00000009");assert(!response[0]&&currentAddr==8);
}else if(!strcmp(argv[1],"assignexpired")){
 press(BUTTON_PIN,BUTTON_HOLD_MS+50);assert(mode==MODE_ASSIGN);
 delay_ms(UI_TIMEOUT_MS);KeyScan();assert(mode==MODE_NORMAL);
 framed("SETID 12345678 11111111 22222222 33333333 00000008");assert(strstr(response,"ERROR NOTARMED")&&currentAddr==7);
}else if(!strcmp(argv[1],"assignfail")){
 press(BUTTON_PIN,BUTTON_HOLD_MS+50);failReadback=1;
 framed("SETID 12345678 11111111 22222222 33333333 00000008");
 assert(strstr(response,"ERROR EEPROM")&&settingsFault&&currentAddr==7&&feedState==FEED_FAULT);
 assert((testA.levels&MOTOR_ALL_PINS)==MOTOR_ALL_PINS);
}else if(!strcmp(argv[1],"savesuccess")){
 press(BUTTON_PIN,3*BUTTON_HOLD_MS+50);press(BUTTON_PIN,10);
 assert(currentAddr==7&&memory[0]==7&&editValue==8);
 press(BUTTON_PIN,BUTTON_HOLD_MS+50);assert(currentAddr==8&&memory[0]==8&&!settingsFault);
 press(BUTTON_PIN,4*BUTTON_HOLD_MS+50);press(BUTTON_PIN,10);
 assert(currentCount==3&&memory[1]==3&&editValue==4);
 press(BUTTON_PIN,BUTTON_HOLD_MS+50);assert(currentCount==4&&memory[1]==4&&!settingsFault);
}else if(!strcmp(argv[1],"slowack")){
 // Menu blinking and feedback do not block read-only serial traffic.
 press(BUTTON_PIN,3*BUTTON_HOLD_MS+50);
 uint32_t start=now;char line[100];int n=sprintf(line,"B07 IDENT 12345678");
 sprintf(line+n," %08X",Boot_Crc32(line,n));updateLine=line;Feeder_Run();
 assert(now-start<100&&strstr(response,"IDENT")&&!starts);
}else if(!strcmp(argv[1],"peel")||!strcmp(argv[1],"peelwrap")||!strcmp(argv[1],"peeltimeout")){
 if(!strcmp(argv[1],"peelwrap")){now=UINT32_MAX-100U;peelOffAt=now;}
 if(!FEEDER_WIDE){assert(Motor_Reserve(99));Motor_Start();}
 testA.levels&=~PEEL_SWITCH_PIN;delay_ms(PEEL_RESTART_MS+PEEL_DEBOUNCE_MS);
 assert(peelRunning&&!(testA.levels&MOTOR_PEEL_A_PIN));
 if(!strcmp(argv[1],"peeltimeout")){
  // Keep index deadline out of the way to exercise the independent peel guard.
  feedStartedAt=now;delay_ms(PEEL_TIMEOUT_MS);assert(feedState==FEED_FAULT&&!peelRunning);
  assert((testA.levels&MOTOR_ALL_PINS)==MOTOR_ALL_PINS);trigger();assert(feedState==FEED_FAULT);
 }else{
  // Opening stops in one tick, without stopping index/counting.
  testA.levels|=PEEL_SWITCH_PIN;delay_ms(1);assert(!peelRunning&&(testA.levels&MOTOR_PEEL_A_PIN));
  if(!FEEDER_WIDE)assert(feedState==FEED_RUNNING&&!(testA.levels&MOTOR_INDEX_B_PIN));
  testA.levels&=~PEEL_SWITCH_PIN;delay_ms(PEEL_RESTART_MS-1);assert(!peelRunning);
  delay_ms(1);assert(peelRunning);
  // A transient closure cannot restart the motor.
  testA.levels|=PEEL_SWITCH_PIN;delay_ms(1);testA.levels&=~PEEL_SWITCH_PIN;delay_ms(2);
  testA.levels|=PEEL_SWITCH_PIN;delay_ms(PEEL_RESTART_MS+1);assert(!peelRunning);
  if(!FEEDER_WIDE){while(feedState==FEED_RUNNING)pulse();}
  testA.levels&=~PEEL_SWITCH_PIN;delay_ms(PEEL_RESTART_MS+PEEL_DEBOUNCE_MS);
  assert(!!peelRunning==FEEDER_WIDE);
  // Settings always stop idle peeling and opening the switch cannot restart it.
  press(BUTTON_PIN,3*BUTTON_HOLD_MS+50);assert(mode==MODE_ADDR&&!peelRunning);
  assert((testA.levels&MOTOR_ALL_PINS)==MOTOR_ALL_PINS);
 }
}else if(!strncmp(argv[1],"completion",10)){
 framed("STATUS 12345678 00000001");assert(strstr(response,"UNKNOWN 12345678 00000001")&&!starts);
 if(!strcmp(argv[1],"completionearly"))injectPulse=1;
 framed(!strcmp(argv[1],"completionearly")?"FEED 12345678 00000001 00000001":"FEED 12345678 00000001 00000002");
 assert(starts==1&&strstr(response,"ACCEPT 12345678 00000001"));
 framed("STATUS 12345679 00000001");assert(strstr(response,"UNKNOWN 12345679 00000001"));
 framed("STATUS 12345678 00000002");assert(strstr(response,"UNKNOWN 12345678 00000002"));
 if(!strcmp(argv[1],"completionfault")){
  delay_ms(FEED_TIMEOUT_MS);assert(feedState==FEED_FAULT&&requestResult==REQUEST_FAULT);
  assert((testA.levels&MOTOR_ALL_PINS)==MOTOR_ALL_PINS);
  framed("STATUS 12345678 00000001");assert(strstr(response,"FAULT 12345678 00000001"));
  framed("FEED 12345678 00000002 00000001");assert(strstr(response,"FAULT 12345678 00000002")&&starts==1);
 }else if(!strcmp(argv[1],"completioneeprom")){
  failReadback=1;assert(!SaveSetting(EEPROM_DATA_ADDR,8));
  assert(settingsFault&&requestResult==REQUEST_FAULT&&feedState==FEED_FAULT);
  framed("STATUS 12345678 00000001");assert(strstr(response,"FAULT 12345678 00000001"));
 }else{
  if(strcmp(argv[1],"completionearly")){
   framed("STATUS 12345678 00000001");assert(strstr(response,"RUNNING 12345678 00000001"));
   pulse();assert(feedState==FEED_RUNNING&&requestResult==REQUEST_RUNNING);
   framed("STATUS 12345678 00000001");assert(strstr(response,"RUNNING 12345678 00000001"));
   pulse();assert(strstr(response,"RUNNING")); // ISR sends no unsolicited reply.
  }
  assert(feedState==FEED_IDLE&&requestResult==REQUEST_DONE);idle();
  framed("STATUS 12345678 00000001");assert(strstr(response,"DONE 12345678 00000001"));
  framed("STATUS 12345678 00000001");assert(strstr(response,"DONE 12345678 00000001")&&starts==1);
  trigger();assert(feedState==FEED_RUNNING&&starts==2);
  framed("STATUS 12345678 00000001");assert(strstr(response,"DONE 12345678 00000001"));
  while(feedState==FEED_RUNNING)pulse();
  framed("FEED 12345678 00000002 00000001");assert(starts==3&&strstr(response,"ACCEPT"));
  framed("STATUS 12345678 00000001");assert(strstr(response,"UNKNOWN 12345678 00000001"));
 }
}else if(!strcmp(argv[1],"framed")){
 char line[100];int n=sprintf(line,"B07 FEED 12345678 00000001 00000002");
 sprintf(line+n," %08X",Boot_Crc32(line,n));updateLine=line;ProcessRS485();
 assert(starts==1&&motorCount==2&&strstr(response,"B07 ACCEPT 12345678 00000001 "));
 n=sprintf(line,"B07 FEED 12345678 00000002 00000004");sprintf(line+n," %08X",Boot_Crc32(line,n));
 updateLine=line;ProcessRS485();assert(starts==1&&motorCount==2&&strstr(response,"B07 BUSY 12345678 00000002 "));
}else if(!strcmp(argv[1],"badframed")){
 const char* bodies[]={"FEED 12345678 00000001 00000064","FEED 12345678 00000001 00000004x","FEED 1234 00000001 00000004"};
 for(unsigned i=0;i<sizeof(bodies)/sizeof(*bodies);i++){
  char line[100];int n=sprintf(line,"B07 %s",bodies[i]);sprintf(line+n," %08X",Boot_Crc32(line,n));
  response[0]=0;updateLine=line;ProcessRS485();assert(!starts&&!response[0]);
 }
}else if(!strncmp(argv[1],"boot",4))
{
  char line[100];int id=!strcmp(argv[1],"bootwrong")?8:7;
  int n=sprintf(line,"B%02d BOOT",id);sprintf(line+n," %08X",Boot_Crc32(line,n));
  if(!strcmp(argv[1],"bootcrc"))line[n+2]^=1;
  if(!strcmp(argv[1],"bootbusy")){assert(Motor_Reserve(2));Motor_Start();}
  if(!strcmp(argv[1],"bootreserved"))assert(Motor_Reserve(2));
  if(!strcmp(argv[1],"bootfault")){feedState=FEED_FAULT;}
  if(!strcmp(argv[1],"booteeprom"))failEEPROM=1;
  updateLine=line;response[0]=0;ProcessRS485();
  if(!strcmp(argv[1],"bootbusy")||!strcmp(argv[1],"bootreserved")){
   assert(!resetCalls&&feedReady&&strstr(response,"ERROR BUSY"));
  }else if(!strcmp(argv[1],"bootwrong")||!strcmp(argv[1],"bootcrc")){
   assert(!resetCalls&&feedReady&&feedState==FEED_IDLE&&!response[0]);
  }else if(!strcmp(argv[1],"booteeprom")){
   assert(!resetCalls&&!feedReady&&feedState==FEED_FAULT&&strstr(response,"ERROR EEPROM"));
   assert((testA.levels&MOTOR_ALL_PINS)==MOTOR_ALL_PINS);trigger();assert(!starts);
  }else{
   assert(resetCalls==1&&strstr(response,"RESET"));trigger();assert(!starts);
   assert(memory[0]==7&&memory[1]==3);
  }
 }else if(!strcmp(argv[1],"race")){
  injectAck=1;command(7,9);assert(starts==1&&motorCount==9&&feedState==FEED_RUNNING);
  command(7,2);assert(!strcmp(response,"Busy\\n")&&motorCount==9&&starts==1);
  for(int n=0;n<8;n++)pulse();assert(feedState==FEED_RUNNING);pulse();assert(feedState==FEED_IDLE);idle();
 }else if(!strcmp(argv[1],"startup")){
  command(7,2);assert(!strcmp(response,"OK\\n")&&feedState==FEED_RUNNING);
 }else if(!strcmp(argv[1],"zero")){
  assert(currentCount==1&&memory[1]==1);command(7,0);assert(motorCount==1);pulse();assert(feedState==FEED_IDLE);idle();
  mode=MODE_COUNT;editValue=99;press(BUTTON_PIN,10);assert(editValue==1&&currentCount==1);mode=MODE_NORMAL;
  currentCount=0;assert(!Motor_Reserve(0));assert(feedState==FEED_IDLE);
 }else if(!strcmp(argv[1],"early")){
  injectPulse=1;command(7,1);assert(starts==1&&feedState==FEED_IDLE);idle();
 }else if(!strcmp(argv[1],"display")){
  command(7,1);int before=displayCalls;injectRender=1;RefreshDisplay();
  assert(feedState==FEED_IDLE&&displayDirty);assert(displayCalls==before+1);
  Feeder_Run();assert(!displayDirty);idle();
  before=displayCalls;trigger();assert(displayCalls==before&&feedState==FEED_RUNNING);
 }else if(!strcmp(argv[1],"timeout")||!strcmp(argv[1],"wrap")){
  if(!strcmp(argv[1],"wrap"))now=UINT32_MAX-5U;
  assert(Motor_Reserve(2));Motor_Start();int before=displayCalls;
  delay_ms(FEED_TIMEOUT_MS-1);assert(feedState==FEED_RUNNING);
  delay_ms(1);assert(feedState==FEED_FAULT&&displayCalls==before);
  assert((testA.levels&MOTOR_ALL_PINS)==MOTOR_ALL_PINS);
  trigger();assert(feedState==FEED_FAULT&&starts==1);
  command(7,2);assert(!strcmp(response,"Busy\\n")&&starts==1);
  Feeder_Run();assert(!displayDirty&&(testA.levels&MOTOR_ALL_PINS)==MOTOR_ALL_PINS);
 }else if(!strcmp(argv[1],"feedback")){
  uint32_t before=now;StartFeedback(3);assert(now==before&&feedbackToggles==5);
  for(int i=0;i<5;i++){delay_ms(200);UpdateFeedback();}
  assert(!feedbackToggles&&!feedbackOn);
  command(7,2);StartFeedback(3);delay_ms(FEED_TIMEOUT_MS);UpdateFeedback();
  assert(feedState==FEED_FAULT&&(testA.levels&MOTOR_ALL_PINS)==MOTOR_ALL_PINS);

 }
 assert(!mask);printf("%s variant %d passed\\n",argv[1],FEEDER_WIDE);
}
'''.replace('FEEDER_PATH','feeder.c').replace('MOTOR_IDLE',idle)
rx='''#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "RX_PATH"
GPIO_TypeDef testA,testB;
USART_TypeDef testUart;
uint16_t pending;
void HAL_GPIO_WritePin(GPIO_TypeDef* p,uint16_t n,int v){(void)p;(void)n;(void)v;}
int HAL_UART_Init(UART_HandleTypeDef* h){(void)h;return HAL_OK;}
void HAL_NVIC_SetPriority(int a,int b,int c){(void)a;(void)b;(void)c;}
void HAL_NVIC_EnableIRQ(int a){(void)a;}
void HAL_NVIC_DisableIRQ(int a){(void)a;}
int HAL_UART_DeInit(UART_HandleTypeDef* h){(void)h;return HAL_OK;}
void Board_ConfigurePin(GPIO_TypeDef* p,uint16_t n,uint32_t m){(void)p;(void)n;(void)m;}
void Board_ErrorHandler(void){assert(0);}
void delay_us(uint32_t n){(void)n;}
static void byte(uint8_t ch,uint32_t errors){testUart.SR=USART_SR_RXNE|errors;testUart.DR=ch;USART1_IRQHandler();}
static void input(const char* s){while(*s)byte((uint8_t)*s++,0);}
static uint8_t readFeedCommand(int* address,int* count){
 char line[RX_BUFFER_SIZE];
 return RS485_ReadLine(line,sizeof(line)) && RS485_ParseFeedCommand(line,address,count);
}
static void empty(void){int a=-123,c=-123;assert(!readFeedCommand(&a,&c));assert(a==-123&&c==-123);}
static void expect(int addr,int count){int a=-1,c=-1;assert(readFeedCommand(&a,&c)&&a==addr&&c==count);}
int main(void){
 RS485_Init();
 input("N1 F1\\nN2 F2\\nN3 F0\\r\\n");expect(1,1);expect(2,2);expect(3,0);empty();
 input("N7 F");empty();input("2\\n");expect(7,2);empty();
 for(unsigned i=0;i<RX_BUFFER_SIZE-1;i++)byte('X',0);input("N7 F2\\n");empty();input("N7 F3\\n");expect(7,3);
 input("N7 F2");byte(0,0);input("garbage\\n");empty();input("N7 F4\\n");expect(7,4);
 input("N7 F1");byte('9',USART_SR_FE);input("\\n");empty();input("N7 F5\\n");expect(7,5);
 input("N7 F1");testUart.SR=USART_SR_ORE;testUart.DR=0;USART1_IRQHandler();input("\\n");empty();
 const char* bad[]={"N0 F1\\n","N00 F0\\n","N7F2\\n","N+7 F2\\n","N7 F-1\\n","N100 F2\\n","N7 F100\\n","N7 F2x\\n","N7 F1\\r9\\n","N F2\\n","N7 F\\n","\\n","N7 F99999999999999999999999\\n"};
 for(unsigned i=0;i<sizeof(bad)/sizeof(*bad);i++){input(bad[i]);empty();}
 input(" \\tN07 \\tF02 \\t\\r\\n");expect(7,2);
 // Full ring preserves its ten committed six-byte commands, dropping only
 // the incomplete overflowing frame. A later clean frame is accepted again.
 for(unsigned i=0;i<(RS485_RX_BUF_SIZE-1)/6;i++)input("N1 F1\\n");input("N7 F9\\n");
 for(unsigned i=0;i<(RS485_RX_BUF_SIZE-1)/6;i++)expect(1,1);empty();input("N7 F8\\n");expect(7,8);
 // A too-small consumer output cannot turn the suffix into a second command.
 input("N7 F2\\nN8 F3\\n");char tiny[3];assert(!RS485_ReadLine(tiny,sizeof(tiny)));expect(8,3);
 // Thousands of wraps with interleaved partial delivery; no premature parse.
 for(int i=0;i<10000;i++){
  char line[24];int n=snprintf(line,sizeof(line),"N%d F%d\\n",1+i%99,(i*7)%100);
  for(int j=0;j<n-1;j++)byte((uint8_t)line[j],0);empty();byte('\\n',0);expect(1+i%99,(i*7)%100);
 }
 empty();puts("Actual UART ISR/parser: queue order, framing, overflow, UART errors, bounds and ring wraps passed");
}
'''.replace('RX_PATH','rs485.c')
with tempfile.TemporaryDirectory(prefix='v485-fix-check-') as d:
 q=Path(d);(q/'stm32f1xx_hal.h').write_text(hal);(q/'app.c').write_text(app);(q/'rx.c').write_text(rx)
 for wide in [0,1]:
  for module in ['app','rx']:
   exe=q/(module+str(wide));subprocess.run(['gcc','-std=c11','-Wall','-Wextra','-Wno-misleading-indentation','-Werror','-fsanitize=undefined,address','-g','-I',d,'-I',str(p/'src'),'-DFEEDER_WIDE='+str(wide),str(q/(module+'.c')),'-o',str(exe)],check=True)
   if module=='app':
    for case in ['race','startup','zero','early','display','timeout','wrap','feedback','readfail','countreadfail','blank','unassigned','unassignedremote','unassignedboot','bootblank','bootblankfail','invalidid','savefail','readbackfail','buttons','heldstartup','menuboot','menutiming','menubootfail','menufault','assignheld','menubusy','assign','assignexpired','assignfail','peel','peelwrap','peeltimeout','savesuccess','slowack','framed','badframed','completion','completionearly','completionfault','completioneeprom','bootidle','bootbusy','bootreserved','bootwrong','bootcrc','bootfault','booteeprom']:subprocess.run([str(exe),case],check=True)
   else:subprocess.run([str(exe)],check=True)
print('All actual-source checks passed. Temporary files only; no project tests folder created.')
