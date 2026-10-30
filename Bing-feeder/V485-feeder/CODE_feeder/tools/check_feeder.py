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
static int context,starts,displayCalls,renderDepth,lastNumber,lastFault;
static int queued,address,count,injectAck,injectStartup,injectPulse,injectRender;
static uint8_t memory[256]={7,3,FEEDER_WIDE ? 12 : 8,FEEDER_WIDE ? 243 : 247,0,255,OPTIONS_VERSION};
static int resetCalls,failEEPROM;
static int failReadOffset=-1,settingWrites,failReadback,checkRemoteSave;
static const char* updateLine;
static char response[80];
static void dispatch(void) {
 if(mask)return;
 int old=context;
 if(pending&COUNT_PIN){context=2;EXTI3_IRQHandler();}
 context=old;
}
// Exercise the shared reservation guard independently of button debounce.
static void manualRequest(void){if(Motor_Reserve(0))Motor_Start();}
static void pulse(void){pending|=COUNT_PIN;dispatch();}
uint32_t __get_PRIMASK(void){return mask;}
void __disable_irq(void){mask=1;}
void __set_PRIMASK(uint32_t value){mask=value;dispatch();}
void HAL_GPIO_WritePin(GPIO_TypeDef* port,uint16_t pins,int level){
 if(level)port->levels|=pins;else port->levels&=~pins;
 if(port==MOTOR_PORT&&(pins&((!!(motorOptions & OPTION_FEED_REVERSE) ^ retractMove) ? MOTOR_INDEX_A_PIN : MOTOR_INDEX_B_PIN))&&!level){
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
  manualRequest();
 }
 while(ms--){now++;int old=context;context=3;Feeder_Tick();context=old;}
}
void delay_us(uint32_t us){(void)us;}
void Board_WatchdogFeed(void){assert(context==0&&!mask);}
void CH455_RefreshNum(uint16_t value){
 assert(context==0&&!renderDepth&&value<=99);renderDepth++;displayCalls++;lastNumber=value;
 if(injectRender){injectRender=0;pulse();}
 renderDepth--;
}
void CH455_RefreshFault(uint8_t code){lastFault=code;displayCalls+=2;}
void CH455_SetDisplay(uint8_t digit,uint8_t segments){
 (void)digit;(void)segments;assert(context==0&&!renderDepth);displayCalls++;
}
uint8_t EEPROM_WriteByte(uint8_t offset,uint8_t value){if(checkRemoteSave){assert(!feedReady&&!peelRunning);manualRequest();assert(feedState==FEED_IDLE);assert((testA.levels&MOTOR_ALL_PINS)==MOTOR_ALL_PINS);}settingWrites++;if(failEEPROM)return 0;memory[offset]=value;delay_ms(5);return !failReadback;}
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
 GPIO_TypeDef* port = pin==PEEL_SWITCH_PIN ? PEEL_SWITCH_PORT : GPIOA;
 port->levels&=~pin;KeyScan();delay_ms(BUTTON_DEBOUNCE_MS);KeyScan();delay_ms(duration);KeyScan();
 port->levels|=pin;KeyScan();delay_ms(BUTTON_DEBOUNCE_MS);KeyScan();
}
static void framedAt(uint8_t destination,const char* body){
 char line[RX_BUFFER_SIZE];int n=snprintf(line,sizeof(line),"B%02u %s",destination,body);
 snprintf(line+n,sizeof(line)-(size_t)n," %08X",Boot_Crc32(line,(size_t)n));
 updateLine=line;response[0]=0;ProcessRS485();
}
static void framed(const char* body){framedAt(7,body);}
int main(int argc,char** argv){
 assert(argc==2);testA.levels=testB.levels=0xffff;
 if(!strcmp(argv[1],"defaults")){memory[1]=memory[4]=memory[5]=memory[6]=255;}
 if(!strcmp(argv[1],"zero"))memory[1]=0;
 if(!strcmp(argv[1],"untyped"))memory[3]=0; // Valid-looking width with a damaged check byte must be inhibited.
 if(!strcmp(argv[1],"typereadfail"))failReadOffset=2;
 if(!strcmp(argv[1],"heldstartup"))testA.levels&=~(MENU_BUTTON_PIN|BUTTON_PIN);
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
 if(!strcmp(argv[1],"optionscorrupt")){
  memory[EEPROM_OPTIONS_VERSION_ADDR]=0;Feeder_Init();
  assert(optionsFault&&!feedReady&&faultReason==FAULT_SETTINGS);idle();
  framed("CONFIG 12345678");assert(strstr(response,"CONFIG 12345678"));
  assert(mode==MODE_NORMAL);
  framed("SETCONFIG 12345678 11111111 22222222 33333333 00000001 00000000 00000000");
  assert(strstr(response,"CONFIGSET")&&!optionsFault&&!feedReady&&feedState==FEED_FAULT);
  assert(LoadOptions()&&motorOptions==1);idle();
  framed("SETTYPE 12345678 11111111 22222222 33333333 0000000C");
  assert(strstr(response,"TYPESET")&&currentType==12&&!feedReady);idle();
  framed("SETCOUNT 12345678 11111111 22222222 33333333 00000002");
  assert(strstr(response,"COUNTSET")&&currentCount==2&&!feedReady);idle();
  framed("CLEAR 12345678 11111111 22222222 33333333");
  assert(strstr(response,"CLEARED")&&faultReason==FAULT_NONE&&feedReady&&jogPeelHold);idle();return 0;
 }
 if(!strcmp(argv[1],"optionsrecords")){
  for(uint8_t value=0;value<=OPTIONS_MASK;value++){
   memory[4]=value;memory[5]=(uint8_t)~value;
   memory[6]=OPTIONS_VERSION;assert(LoadOptions()&&!optionsFault&&motorOptions==value);
   memory[6]=0;assert(LoadOptions()&&optionsFault); // Invalidation/data/check write interrupted
   memory[6]=255;assert(LoadOptions()&&optionsFault); // Partial legacy extension is not blank
   memory[6]=OPTIONS_VERSION;memory[5]^=1;assert(LoadOptions()&&optionsFault);
  }
  memory[4]=8;memory[5]=247;memory[6]=OPTIONS_VERSION;assert(LoadOptions()&&optionsFault);
  return 0;
 }
 if(!strcmp(argv[1],"optionsreadfail")){
  failReadOffset=EEPROM_OPTIONS_ADDR;assert(!LoadSettings());assert(LoadSettings()&&motorOptions==0);return 0;
 }
 Feeder_Init();assert(feedReady&&feedState==FEED_IDLE&&!starts);idle();
 char hello[100];snprintf(hello,sizeof(hello),"%s",response);
 hello[strcspn(hello,"\\r\\n")]=0;
 char* body=Boot_DecodePacket(hello,currentAddr);
 assert(body&&!strcmp(body,"ONLINE 11111111 22222222 33333333"));injectStartup=0;
 
if(!strcmp(argv[1],"defaults")){
 assert(currentCount==(FEEDER_WIDE?1:2)&&motorOptions==(FEEDER_WIDE?0:OPTION_FEED_REVERSE));
 assert(memory[1]==currentCount&&optionsUnconfigured);
 assert(SaveType(8)&&motorOptions==OPTION_FEED_REVERSE);
 assert(SaveType(12)&&motorOptions==0);return 0;
}else if(!strncmp(argv[1],"longjog",7)){
 currentCount=2;
 if(!strcmp(argv[1],"longjogwrap"))now=UINT32_MAX-1500U;
 uint32_t target=!strcmp(argv[1],"longjoglimit")?10000U:300U;
 if(target==10000){
  framed("JOG 12345678 00000001 00000000 00001389");assert(strstr(response,"ERROR JOG")&&!starts);
 }
 framed(target==10000?"JOG 12345678 00000001 00000000 00001388":"JOG 12345678 00000001 00000000 00000096");
 assert(strstr(response,"ACCEPT")&&motorCount==target&&jogItems==target/2);
 assert(moveDeadlineMs==JOG_STARTUP_BUDGET_MS+target*JOG_EVENT_BUDGET_MS);
 RefreshDisplay();assert(lastNumber==99); // Two-digit hardware display saturates safely.
 if(!strcmp(argv[1],"longjogstall")){
  delay_ms(JOG_STALL_TIMEOUT_MS-1);assert(feedState==FEED_RUNNING);
  delay_ms(1);assert(feedState==FEED_FAULT&&faultReason==FAULT_INDEX);idle();return 0;
 }
 if(!strcmp(argv[1],"longjogdeadline")){
  // Progress continues but cannot extend the total deadline indefinitely.
  moveDeadlineMs=5000;
  for(int i=0;i<4;i++){delay_ms(1000);pulse();assert(feedState==FEED_RUNNING);}
  delay_ms(1000);assert(feedState==FEED_FAULT&&faultReason==FAULT_INDEX);idle();return 0;
 }
 if(!strcmp(argv[1],"longjogstop")){
  framed("STOP 12345678");assert(strstr(response,"STOPPED 12345678")&&feedState==FEED_FAULT&&faultReason==FAULT_STOP);
  framed("STATUS 12345678 00000001");assert(strstr(response,"FAULT"));idle();return 0;
 }
 for(uint32_t i=0;i<target-1;i++){delay_ms(target==10000?0:500);pulse();assert(feedState==FEED_RUNNING);}
 delay_ms(target==10000?0:500);pulse();assert(feedState==FEED_IDLE&&requestResult==REQUEST_DONE);
 assert(pa3TriggerCount==0);idle();return 0;
}else if(!strcmp(argv[1],"jog")){
 currentCount=2;int writes=settingWrites;
 const char* invalid[]={"JOG 12345678 00000001 00000002 00000001","JOG 12345678 00000001 00000000 00000000","JOG 12345678 00000001 00000000 FFFFFFFF","JOG 12345678 00000001 00000000 00002711"};
 for(unsigned i=0;i<sizeof(invalid)/sizeof(*invalid);i++){framed(invalid[i]);assert(strstr(response,"ERROR JOG")&&!starts);}
 for(uint8_t reverse=0;reverse<=1;reverse++)for(uint8_t retract=0;retract<=1;retract++){
  motorOptions=reverse;testB.levels&=~PEEL_SWITCH_PIN;delay_ms(200);
  char body[90];snprintf(body,sizeof(body),"JOG 12345678 00000001 %08X 0000001E",retract);
  framed(body);assert(strstr(response,"ACCEPT")&&motorCount==60&&feedState==FEED_RUNNING&&jogPeelHold&&!peelRunning);
  assert(!!(testA.levels&MOTOR_INDEX_B_PIN)==(reverse^retract));
  framed("STATUS 12345678 00000001");assert(strstr(response,"RUNNING"));
  for(int i=0;i<59;i++)pulse();assert(feedState==FEED_RUNNING);
  pulse();assert(feedState==FEED_IDLE);idle();delay_ms(200);idle();
  framed("STATUS 12345678 00000001");assert(strstr(response,"DONE"));
  assert(motorOptions==reverse&&currentCount==2&&settingWrites==writes);
 }
 // Normal feeding leaves jog peel suppression and restores saved direction.
 assert(Motor_Reserve(1));Motor_Start();assert(!jogPeelHold&&!retractMove);pulse();
 testB.levels|=PEEL_SWITCH_PIN;delay_ms(1);idle();
 framed("JOG 12345678 00000002 00000001 00000001");delay_ms(FEED_TIMEOUT_MS);
 assert(feedState==FEED_FAULT&&requestResult==REQUEST_FAULT&&faultReason==FAULT_INDEX);idle();return 0;
}else if(!strcmp(argv[1],"remotecount")){
 assert(mode==MODE_NORMAL);int writes=settingWrites;
 framed("SETCOUNT 12345678 11111110 22222222 33333333 00000002");assert(!response[0]&&settingWrites==writes);
 framed("SETCOUNT 12345678 11111111 22222222 33333333 00000000");assert(strstr(response,"ERROR COUNT")&&settingWrites==writes);
 framed("SETCOUNT 12345678 11111111 22222222 33333333 00000064");assert(strstr(response,"ERROR COUNT")&&settingWrites==writes);
 framed("SETCOUNT 12345678 11111111 22222222 33333333 00000002 extra");assert(!response[0]&&settingWrites==writes);
 for(int n=1;n<=99;n+=n==1?1:97){
  char body[90];snprintf(body,sizeof(body),"SETCOUNT 12345678 11111111 22222222 33333333 %08X",n);
  checkRemoteSave=1;framed(body);checkRemoteSave=0;
  assert(strstr(response,"COUNTSET")&&currentCount==n&&memory[1]==n&&mode==MODE_NORMAL);
  currentCount=0;assert(LoadSettings()&&currentCount==n);
  command(7,0);assert(feedState==FEED_RUNNING&&motorCount==(uint32_t)n);
  writes=settingWrites;framed(body);assert(strstr(response,"ERROR BUSY")&&settingWrites==writes);
  for(int i=0;i<n;i++)pulse();assert(feedState==FEED_IDLE);
 }
 failReadback=1;uint8_t before=currentCount;
 framed("SETCOUNT 12345678 11111111 22222222 33333333 00000002");
 assert(strstr(response,"ERROR EEPROM")&&currentCount==before&&settingsFault&&!feedReady);idle();return 0;
}else if(!strcmp(argv[1],"options")){
 assert(motorOptions==0&&!settingWrites);
 framed("CONFIG 12345678");assert(strstr(response,"CONFIG 12345678 00000000 00000000 00000000"));
 assert(mode==MODE_NORMAL);idle();
 framed("SETCONFIG 12345678 11111110 22222222 33333333 00000001 00000001 00000001");assert(!response[0]&&!settingWrites);
 framed("SETCONFIG 12345678 11111111 22222222 33333333 00000002 00000001 00000001");assert(strstr(response,"ERROR CONFIG")&&!settingWrites);
 framed("SETCONFIG 12345678 11111111 22222222 33333333 00000001 00000001 00000001 extra");assert(!response[0]&&!settingWrites);
 for(uint8_t options=0;options<=OPTIONS_MASK;options++){
  char body[100];snprintf(body,sizeof(body),"SETCONFIG 12345678 11111111 22222222 33333333 %08X %08X %08X",!!(options&1),!!(options&2),!!(options&4));
  checkRemoteSave=1;framed(body);checkRemoteSave=0;assert(strstr(response,"CONFIGSET")&&motorOptions==options);idle();
  motorOptions=0;assert(LoadSettings()&&motorOptions==options); // Simulated EEPROM reload
  framed("CONFIG 12345678");assert(strstr(response,"CONFIG 12345678"));
  assert(mode==MODE_NORMAL&&!peelRunning);
  testB.levels|=PEEL_SWITCH_PIN;
  if(options&4)testB.levels&=~PEEL_SWITCH_PIN;
  delay_ms(50);idle();
  LeaveMenu();
  // Both physical contact levels obey the selected polarity.
  testB.levels|=PEEL_SWITCH_PIN;assert(PeelRequested()==!!(options&4));
  testB.levels&=~PEEL_SWITCH_PIN;assert(PeelRequested()==!(options&4));
  if(options&4)testB.levels|=PEEL_SWITCH_PIN;
  assert(Motor_Reserve(1));Motor_Start();
  int writesBefore=settingWrites;framed(body);assert(strstr(response,"ERROR BUSY")&&settingWrites==writesBefore&&motorOptions==options);
  assert(!!(testA.levels&MOTOR_INDEX_A_PIN)==!(options&1));
  assert(!!(testA.levels&MOTOR_INDEX_B_PIN)==!!(options&1));
  delay_ms(PEEL_RESTART_MS+PEEL_DEBOUNCE_MS);assert(peelRunning);
  assert(!!(testA.levels&MOTOR_PEEL_A_PIN)==!!(options&2));
  assert(!!(testA.levels&MOTOR_PEEL_B_PIN)==!(options&2));
  // Release request: immediate stop even with reversed direction/polarity.
  testB.levels^=PEEL_SWITCH_PIN;delay_ms(1);assert(!peelRunning);
  pulse();assert(feedState==FEED_IDLE);idle();
  mode=MODE_NORMAL;
 }
 // A failed readback latches E3 and never changes runtime options.
 uint8_t previous=motorOptions;failReadback=1;
 framed("SETCONFIG 12345678 11111111 22222222 33333333 00000000 00000000 00000000");
 assert(strstr(response,"ERROR EEPROM")&&settingsFault&&motorOptions==previous&&!feedReady);idle();
 failReadback=0;assert(LoadOptions()&&optionsFault); // Interrupted/invalid record cannot default to normal.
 return 0;
}else if(!strcmp(argv[1],"readfail")||!strcmp(argv[1],"countreadfail")||!strcmp(argv[1],"typereadfail")){
 assert(currentAddr==7&&memory[0]==7&&currentCount==3&&!settingWrites);
}else if(!strcmp(argv[1],"blank")||!strncmp(argv[1],"unassigned",10)){
 assert(currentAddr==0&&memory[0]==0);
 if(!strcmp(argv[1],"blank"))assert(currentCount==(FEEDER_WIDE?1:2)&&memory[1]==currentCount);
 int writes=settingWrites;
 // Even with a closed tension switch, neither variant may run either motor.
 testB.levels&=~PEEL_SWITCH_PIN;
 delay_ms(PEEL_RESTART_MS+PEEL_DEBOUNCE_MS);assert(!peelRunning&&!Motor_Reserve(1));idle();
 manualRequest();press(BUTTON_PIN,10);command(0,1);assert(!starts);idle();
 framedAt(0,"FEED 12345678 00000001 00000001");assert(strstr(response,"B00 FAULT")&&!starts);
 uiLastAction=now;uiBlink=0;RefreshDisplay();assert(lastNumber==0);
 delay_ms(UI_BLINK_MS);KeyScan();assert(uiBlink&&displayDirty);
 int before=displayCalls;RefreshDisplay();assert(displayCalls==before+2);
 delay_ms(UI_BLINK_MS);KeyScan();assert(!uiBlink&&displayDirty);
 before=displayCalls;RefreshDisplay();assert(displayCalls==before+1&&lastNumber==0);
 assert(settingWrites==writes&&!peelRunning&&!starts);idle();
 if(!strcmp(argv[1],"unassignedboot")){
  press(MENU_BUTTON_PIN,2*BUTTON_HOLD_MS+50);assert(resetCalls==1&&memory[0]==0);
 }else if(!strcmp(argv[1],"unassignedremote")){
  press(MENU_BUTTON_PIN,BUTTON_HOLD_MS+50);assert(mode==MODE_ASSIGN);
  framedAt(0,"SETID 12345678 11111111 22222222 33333333 00000000");
  assert(strstr(response,"ERROR ID")&&currentAddr==0&&mode==MODE_ASSIGN);
  framedAt(0,"SETID 12345678 11111111 22222222 33333333 00000063");
  assert(strstr(response,"B00 ID 12345678 00000063")&&currentAddr==99&&memory[0]==99);
 }else{
  press(MENU_BUTTON_PIN,3*BUTTON_HOLD_MS+50);assert(mode==MODE_ADDR&&editValue==1);
  delay_ms(UI_TIMEOUT_MS);KeyScan();assert(currentAddr==0&&mode==MODE_NORMAL&&!starts);
  press(MENU_BUTTON_PIN,3*BUTTON_HOLD_MS+50);press(MENU_BUTTON_PIN,BUTTON_HOLD_MS+50);
  assert(currentAddr==1&&memory[0]==1&&mode==MODE_NORMAL);
 }
 if(currentAddr){
  uiBlink=1;int before=displayCalls;RefreshDisplay();assert(displayCalls==before+1&&lastNumber==currentAddr);
  assert(Motor_Reserve(1));Motor_Start();assert(starts==1);pulse();assert(feedState==FEED_IDLE);
 }
}else if(!strcmp(argv[1],"savefail")||!strcmp(argv[1],"readbackfail")){
 mode=MODE_ADDR;editValue=8;buttonReady=1;
 if(!strcmp(argv[1],"readbackfail"))failReadback=1;else failEEPROM=1;
 press(MENU_BUTTON_PIN,BUTTON_HOLD_MS+50);assert(currentAddr==7&&settingsFault&&!feedReady&&feedState==FEED_FAULT);
 assert(memory[0]==(failReadback?8:7));
 assert((testA.levels&MOTOR_ALL_PINS)==MOTOR_ALL_PINS);
 int before=starts;manualRequest();command(7,2);assert(starts==before&&!response[0]);
 char line[100];int n=sprintf(line,"B07 BOOT");sprintf(line+n," %08X",Boot_Crc32(line,n));
 updateLine=line;ProcessRS485();assert(!resetCalls);Feeder_Run();
 assert((testA.levels&MOTOR_ALL_PINS)==MOTOR_ALL_PINS);
}else if(!strcmp(argv[1],"diagnostics")){
 int writes=settingWrites;framed("DIAG 12345678");
 unsigned nonce,hi,lo,total,flags;
 assert(sscanf(response,"B07 DIAG %x %x %x %x %x",&nonce,&hi,&lo,&total,&flags)==5);
 assert(nonce==0x12345678&&!hi&&!lo&&!total&&(flags&255)==3);
 framed("MONITOR 12345678 12345678 9ABCDEF0");assert(monitorToken[0]==0x12345678&&monitorToken[1]==0x9ABCDEF0);
 framed("MONITOR 12345678 11111111 22222222");assert(monitorToken[0]==0x12345678&&monitorToken[1]==0x9ABCDEF0);
 framed("MONITOR 12345678 00000000 00000000");assert(!response[0]);
 pulse();assert(movementTotal==1&&!starts); // Hand movement while idle counts.
 command(7,2);pulse();assert(movementTotal==2&&feedState==FEED_RUNNING);
 pulse();assert(movementTotal==3&&feedState==FEED_IDLE);
 press(BUTTON_PIN,10);while(feedState==FEED_RUNNING)pulse();assert(movementTotal==6);
 movementTotal=UINT32_MAX;pulse();assert(movementTotal==0);
 failReadback=1;assert(!SaveSetting(EEPROM_DATA_ADDR,8));assert(faultReason==FAULT_SETTINGS);
 framed("DIAG 12345678");assert(sscanf(response,"B07 DIAG %x %x %x %x %x",&nonce,&hi,&lo,&total,&flags)==5);
 assert(((flags>>8)&255)==FAULT_SETTINGS&&hi==0x12345678&&lo==0x9ABCDEF0);
 RefreshDisplay();assert(lastFault==FAULT_SETTINGS&&settingWrites==writes+1);
}else if(!strcmp(argv[1],"buttons")){
 int writes=settingWrites;
 // Short PA4 tap advances; PB6 only controls peel permission.
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
 now=UINT32_MAX-100U;press(MENU_BUTTON_PIN,3*BUTTON_HOLD_MS+50);
 assert(mode==MODE_ADDR&&editValue==7&&starts==2);
 manualRequest();command(7,1);assert(starts==2&&strstr(response,"Busy"));
 framed("FEED 12345678 00000001 00000001");assert(strstr(response,"BUSY"));
 press(MENU_BUTTON_PIN,10);assert(editValue==8&&currentAddr==7&&settingWrites==writes);
 press(MENU_BUTTON_PIN,BUTTON_HOLD_MS+50);assert(mode==MODE_NORMAL&&currentAddr==8&&memory[0]==8&&starts==2);
 press(MENU_BUTTON_PIN,4*BUTTON_HOLD_MS+50);assert(mode==MODE_COUNT&&editValue==3);
 editValue=99;press(MENU_BUTTON_PIN,10);assert(editValue==COUNT_MIN&&currentCount==3);
 press(MENU_BUTTON_PIN,BUTTON_HOLD_MS+50);assert(mode==MODE_NORMAL&&currentCount==COUNT_MIN&&memory[1]==COUNT_MIN);
 // Menu selections wrap; editing expires without any EEPROM write.
 press(MENU_BUTTON_PIN,8*BUTTON_HOLD_MS+50);assert(mode==MODE_ADDR);
 writes=settingWrites;editValue=99;press(MENU_BUTTON_PIN,10);assert(editValue==1);
 delay_ms(UI_TIMEOUT_MS);KeyScan();assert(mode==MODE_NORMAL&&currentAddr==8&&settingWrites==writes);
 // While held in an editor, timeout cannot return to normal and feed on release.
 press(MENU_BUTTON_PIN,3*BUTTON_HOLD_MS+50);assert(mode==MODE_ADDR);
 press(MENU_BUTTON_PIN,UI_TIMEOUT_MS+100);assert(mode==MODE_NORMAL&&starts==2);
 // Menu 01 arms only that feeder; a long press can cancel it.
 press(MENU_BUTTON_PIN,BUTTON_HOLD_MS+50);assert(mode==MODE_ASSIGN);
 framedAt(currentAddr,"IDENT 12345678");assert(strstr(response,"IDENT 12345678 11111111 22222222 33333333 00000001"));
 press(MENU_BUTTON_PIN,BUTTON_HOLD_MS+50);assert(mode==MODE_NORMAL&&starts==2);
}else if(!strcmp(argv[1],"untyped")){
 assert(currentType==0&&!Motor_Reserve(1));
 testB.levels&=~PEEL_SWITCH_PIN;delay_ms(500);assert(!peelRunning&&!starts);idle();
 command(7,1);assert(!starts&&strstr(response,"Busy"));
 framed("FEED 12345678 00000001 00000001");assert(strstr(response,"FAULT")&&!starts);
 framed("TYPE 12345678");assert(strstr(response,"TYPE 12345678 00000000 00000003"));
 press(MENU_BUTTON_PIN,5*BUTTON_HOLD_MS+50);assert(mode==MODE_TYPE&&editValue==8);
 press(MENU_BUTTON_PIN,BUTTON_HOLD_MS+50);assert(mode==MODE_NORMAL&&currentType==8&&memory[2]==8);
 assert(Motor_Reserve(1));Motor_Start();pulse();assert(starts==1);
}else if(!strcmp(argv[1],"type")){
 int writes=settingWrites;
 assert(mode==MODE_NORMAL);
 framed("SETTYPE 12345678 11111112 22222222 33333333 00000010");assert(!response[0]&&settingWrites==writes);
 framed("SETTYPE 12345678 11111111 22222222 33333333 00000108");assert(strstr(response,"ERROR TYPE")&&settingWrites==writes);
 framed("SETTYPE 12345678 11111111 22222222 33333333 00000010x");assert(!response[0]&&settingWrites==writes);
 assert(Motor_Reserve(1));Motor_Start();pulse();
 const int types[]={8,12,16,24};
 for(unsigned i=0;i<4;i++){
  char text[90];snprintf(text,sizeof(text),"SETTYPE 12345678 11111111 22222222 33333333 %08X",types[i]);framed(text);
  assert(strstr(response,"TYPESET")&&memory[2]==types[i]&&currentType==types[i]&&mode==MODE_NORMAL);
  LeaveMenu();testB.levels&=~PEEL_SWITCH_PIN;delay_ms(200);
  assert(peelRunning);
  testB.levels|=PEEL_SWITCH_PIN;delay_ms(1);idle();
  assert(mode==MODE_NORMAL);
 }
 LeaveMenu();press(MENU_BUTTON_PIN,5*BUTTON_HOLD_MS+50);assert(mode==MODE_TYPE&&editValue==24);
 press(MENU_BUTTON_PIN,10);assert(editValue==8);press(MENU_BUTTON_PIN,10);assert(editValue==12);
 press(MENU_BUTTON_PIN,10);assert(editValue==16);press(MENU_BUTTON_PIN,BUTTON_HOLD_MS+50);
 assert(currentType==16&&memory[2]==16&&mode==MODE_NORMAL);
 press(MENU_BUTTON_PIN,BUTTON_HOLD_MS+50);failReadback=1;
 framed("SETTYPE 12345678 11111111 22222222 33333333 00000008");assert(strstr(response,"ERROR EEPROM")&&currentType==16&&settingsFault);idle();
}else if(!strcmp(argv[1],"locate")){
 int writes=settingWrites;
 framed("IDENT 12345678");assert(!locateToggles);
 framed("LOCATE 12345678x");assert(!locateToggles&&!response[0]);
 framedAt(8,"LOCATE 12345678");assert(!locateToggles&&!response[0]);
 now=UINT32_MAX-100U;framed("LOCATE 12345678");assert(strstr(response,"LOCATING 12345678")&&locateToggles&&!Motor_Reserve(1));
 testB.levels&=~PEEL_SWITCH_PIN;
 delay_ms(200);UpdateLocate();RefreshDisplay();assert(locateBlank&&!peelRunning&&!starts);
 framed("DIAG 87654321");assert(strstr(response,"DIAG 87654321"));
 for(int i=0;i<20;i++){delay_ms(200);UpdateLocate();RefreshDisplay();assert(!starts);}
 assert(!locateToggles&&!locateBlank&&settingWrites==writes&&lastNumber==7);
 testB.levels|=PEEL_SWITCH_PIN;delay_ms(1);
 assert(Motor_Reserve(1));Motor_Start();framed("LOCATE 12345678");assert(strstr(response,"BUSY")&&!locateToggles);pulse();
 framed("LOCATE 12345678");press(MENU_BUTTON_PIN,3*BUTTON_HOLD_MS+50);UpdateLocate();assert(!locateToggles&&mode==MODE_ADDR);
}else if(!strcmp(argv[1],"twobuttons")){
 press(MENU_BUTTON_PIN,10);assert(!starts&&mode==MODE_NORMAL);
 press(BUTTON_PIN,3*BUTTON_HOLD_MS);assert(!starts&&mode==MODE_NORMAL);
 for(int i=0;i<4;i++){press(PEEL_SWITCH_PIN,10);assert(!starts&&mode==MODE_NORMAL);}
 press(MENU_BUTTON_PIN,3*BUTTON_HOLD_MS+50);assert(mode==MODE_ADDR);
 int value=editValue;press(BUTTON_PIN,10);assert(editValue==value&&!starts);
 // A PA4 press begun in the editor must not feed when the menu expires.
 testA.levels&=~BUTTON_PIN;KeyScan();delay_ms(BUTTON_DEBOUNCE_MS);KeyScan();
 delay_ms(UI_TIMEOUT_MS);KeyScan();assert(mode==MODE_NORMAL);
 testA.levels|=BUTTON_PIN;KeyScan();delay_ms(BUTTON_DEBOUNCE_MS);KeyScan();assert(!starts);
 // Pressing PA2 consumes an overlapping PA4 press, even a short PA2 tap.
 testA.levels&=~BUTTON_PIN;KeyScan();delay_ms(BUTTON_DEBOUNCE_MS);KeyScan();
 press(MENU_BUTTON_PIN,10);
 testA.levels|=BUTTON_PIN;KeyScan();delay_ms(BUTTON_DEBOUNCE_MS);KeyScan();assert(!starts);
 press(BUTTON_PIN,10);assert(starts==1);while(feedState==FEED_RUNNING)pulse();
}else if(!strcmp(argv[1],"heldstartup")){
 assert(!buttonReady&&!feedButtonReady);KeyScan();delay_ms(4*BUTTON_HOLD_MS);KeyScan();assert(mode==MODE_NORMAL&&!starts);
 testA.levels|=MENU_BUTTON_PIN|BUTTON_PIN;KeyScan();delay_ms(BUTTON_DEBOUNCE_MS);KeyScan();assert(buttonReady&&feedButtonReady&&!starts);
 press(BUTTON_PIN,10);assert(starts==1);
}else if(!strcmp(argv[1],"menuboot")){
 press(MENU_BUTTON_PIN,2*BUTTON_HOLD_MS+50);assert(resetCalls==1&&!starts);
  }else if(!strcmp(argv[1],"menutiming")){
 now=UINT32_MAX-100U;
 testA.levels&=~MENU_BUTTON_PIN;KeyScan();delay_ms(BUTTON_DEBOUNCE_MS);KeyScan();
 delay_ms(BUTTON_HOLD_MS-1);KeyScan();assert(mode==MODE_NORMAL);
 delay_ms(1);KeyScan();assert(mode==MODE_MENU&&menuItem==1);
 delay_ms(BUTTON_HOLD_MS);KeyScan();assert(menuItem==2);
 delay_ms(BUTTON_HOLD_MS);KeyScan();assert(menuItem==3);
 testA.levels|=MENU_BUTTON_PIN;KeyScan();delay_ms(BUTTON_DEBOUNCE_MS);KeyScan();assert(mode==MODE_ADDR&&!starts);
 delay_ms(UI_BLINK_MS);KeyScan();assert(uiBlink);int before=displayCalls;RefreshDisplay();assert(displayCalls==before+2);
 delay_ms(UI_BLINK_MS);KeyScan();assert(!uiBlink);before=displayCalls;RefreshDisplay();assert(displayCalls==before+1);
}else if(!strcmp(argv[1],"menubootfail")){
 failReadback=1;press(MENU_BUTTON_PIN,2*BUTTON_HOLD_MS+50);assert(!resetCalls&&settingsFault&&!starts);
 assert((testA.levels&MOTOR_ALL_PINS)==MOTOR_ALL_PINS);
}else if(!strcmp(argv[1],"menufault")){
 Motor_Fault(FAULT_INDEX);press(MENU_BUTTON_PIN,3*BUTTON_HOLD_MS+50);assert(mode==MODE_NORMAL&&!resetCalls);
 press(MENU_BUTTON_PIN,2*BUTTON_HOLD_MS+50);assert(resetCalls==1&&!starts);
}else if(!strcmp(argv[1],"assignheld")){
 press(MENU_BUTTON_PIN,BUTTON_HOLD_MS+50);assert(mode==MODE_ASSIGN);
 testA.levels&=~MENU_BUTTON_PIN;KeyScan();delay_ms(BUTTON_DEBOUNCE_MS);KeyScan();assert(buttonDown);
 framed("SETID 12345678 11111111 22222222 33333333 00000008");assert(currentAddr==8&&mode==MODE_NORMAL);
 testA.levels|=MENU_BUTTON_PIN;KeyScan();delay_ms(BUTTON_DEBOUNCE_MS);KeyScan();assert(!starts);
}else if(!strcmp(argv[1],"menubusy")){
 assert(Motor_Reserve(1));Motor_Start();press(MENU_BUTTON_PIN,3*BUTTON_HOLD_MS+50);
 assert(mode==MODE_NORMAL&&feedState==FEED_RUNNING&&starts==1);pulse();
}else if(!strcmp(argv[1],"assign")){
 framed("IDENT 12345678");assert(strstr(response,"IDENT 12345678 11111111 22222222 33333333 00000000"));
 framed("SETID 12345678 11111111 22222222 33333333 00000008");assert(strstr(response,"ERROR NOTARMED")&&memory[0]==7);
 press(MENU_BUTTON_PIN,BUTTON_HOLD_MS+50);assert(mode==MODE_ASSIGN);
 framed("SETID 12345678 11111112 22222222 33333333 00000008");assert(!response[0]&&currentAddr==7);
 const char* bad[]={"SETID 12345678 11111111 22222222 33333333", "SETID 12345678 11111111 22222222 33333333 00000008x", "SETID 1234 11111111 22222222 33333333 00000008"};
 for(unsigned i=0;i<sizeof(bad)/sizeof(*bad);i++){framed(bad[i]);assert(!response[0]&&currentAddr==7);}
 framed("SETID 12345678 11111111 22222222 33333333 00000064");assert(strstr(response,"ERROR ID")&&currentAddr==7);
 framed("SETID 12345678 11111111 22222222 33333333 00000008");
 assert(strstr(response,"B07 ID 12345678 00000008")&&currentAddr==8&&memory[0]==8&&mode==MODE_NORMAL);
 framed("SETID 12345678 11111111 22222222 33333333 00000009");assert(!response[0]&&currentAddr==8);
}else if(!strcmp(argv[1],"assignexpired")){
 press(MENU_BUTTON_PIN,BUTTON_HOLD_MS+50);assert(mode==MODE_ASSIGN);
 delay_ms(UI_TIMEOUT_MS);KeyScan();assert(mode==MODE_NORMAL);
 framed("SETID 12345678 11111111 22222222 33333333 00000008");assert(strstr(response,"ERROR NOTARMED")&&currentAddr==7);
}else if(!strcmp(argv[1],"assignfail")){
 press(MENU_BUTTON_PIN,BUTTON_HOLD_MS+50);failReadback=1;
 framed("SETID 12345678 11111111 22222222 33333333 00000008");
 assert(strstr(response,"ERROR EEPROM")&&settingsFault&&currentAddr==7&&feedState==FEED_FAULT);
 assert((testA.levels&MOTOR_ALL_PINS)==MOTOR_ALL_PINS);
}else if(!strcmp(argv[1],"savesuccess")){
 press(MENU_BUTTON_PIN,3*BUTTON_HOLD_MS+50);press(MENU_BUTTON_PIN,10);
 assert(currentAddr==7&&memory[0]==7&&editValue==8);
 press(MENU_BUTTON_PIN,BUTTON_HOLD_MS+50);assert(currentAddr==8&&memory[0]==8&&!settingsFault);
 press(MENU_BUTTON_PIN,4*BUTTON_HOLD_MS+50);press(MENU_BUTTON_PIN,10);
 assert(currentCount==3&&memory[1]==3&&editValue==4);
 press(MENU_BUTTON_PIN,BUTTON_HOLD_MS+50);assert(currentCount==4&&memory[1]==4&&!settingsFault);
}else if(!strcmp(argv[1],"slowack")){
 // Menu blinking and feedback do not block read-only serial traffic.
 press(MENU_BUTTON_PIN,3*BUTTON_HOLD_MS+50);
 uint32_t start=now;char line[100];int n=sprintf(line,"B07 IDENT 12345678");
 sprintf(line+n," %08X",Boot_Crc32(line,n));updateLine=line;Feeder_Run();
 assert(now-start<100&&strstr(response,"IDENT")&&!starts);
}else if(!strcmp(argv[1],"bootpeel")){
 assert(jogPeelHold);int writes=settingWrites;
 uint8_t saved[sizeof memory];memcpy(saved,memory,sizeof memory);
 const uint8_t widths[]={8,12,16,24};
 for(unsigned i=0;i<4;i++)for(unsigned no=0;no<2;no++){
  currentType=widths[i];motorOptions=no?OPTION_SWITCH_NO:0;jogPeelHold=1;
  if(no)testB.levels|=PEEL_SWITCH_PIN;else testB.levels&=~PEEL_SWITCH_PIN;
  int oldStarts=starts;
  delay_ms(PEEL_TIMEOUT_MS*2+100);
  assert(feedState==FEED_IDLE&&faultReason==FAULT_NONE&&feedReady&&!peelRunning&&starts==oldStarts);idle();
  // Read-only traffic, settings inspection and test exit must not arm peel.
  framed("DIAG 12345678");framed("CONFIG 12345678");
  framed("TEST 12345678 11111111 22222222 33333333 00000001");
  framed("TEST 12345678 11111111 22222222 33333333 00000000");
  delay_ms(PEEL_TIMEOUT_MS+100);assert(!peelRunning&&faultReason==FAULT_NONE);idle();
  if(i&1)press(BUTTON_PIN,10);
  else framed("FEED 12345678 00000001 00000001");
  assert(starts==oldStarts+1&&!jogPeelHold);
  while(feedState==FEED_RUNNING)pulse();
  delay_ms(PEEL_RESTART_MS+PEEL_DEBOUNCE_MS);assert(peelRunning);
  testB.levels^=PEEL_SWITCH_PIN;delay_ms(1);assert(!peelRunning);idle();
  testB.levels^=PEEL_SWITCH_PIN;delay_ms(PEEL_RESTART_MS+PEEL_DEBOUNCE_MS);assert(peelRunning);
  delay_ms(PEEL_TIMEOUT_MS);assert(faultReason==FAULT_PEEL&&feedState==FEED_FAULT);idle();
  framed("CLEAR 12345678 11111111 22222222 33333333");assert(strstr(response,"CLEARED")&&jogPeelHold);
 }
 assert(settingWrites==writes&&!memcmp(saved,memory,sizeof memory));
}else if(!strcmp(argv[1],"peelidle")){
 assert(Motor_Reserve(1));Motor_Start();pulse();
 int writes=settingWrites;uint8_t saved[sizeof memory];memcpy(saved,memory,sizeof memory);
 const uint8_t widths[]={8,12,16,24};
 for(unsigned i=0;i<sizeof widths;i++){
  currentType=widths[i];testB.levels|=PEEL_SWITCH_PIN;delay_ms(1);idle();
  testB.levels&=~PEEL_SWITCH_PIN;delay_ms(PEEL_RESTART_MS+PEEL_DEBOUNCE_MS);assert(peelRunning&&feedState==FEED_IDLE);
  testB.levels|=PEEL_SWITCH_PIN;delay_ms(1);assert(!peelRunning);idle();
 }
 assert(settingWrites==writes&&!memcmp(saved,memory,sizeof memory));
}else if(!strcmp(argv[1],"clearfault")){
 int writes=settingWrites;uint8_t saved[sizeof memory];memcpy(saved,memory,sizeof memory);
 for(uint8_t fault=1;fault<=4;fault++){
  if(fault==FAULT_SETTINGS)continue;
  Motor_Fault(fault);requestResult=REQUEST_FAULT;
  framed("CLEAR 12345678 00000000 22222222 33333333");assert(!response[0]&&feedState==FEED_FAULT);
  framed("CLEAR 12345678 11111111 22222222 33333333 trailing");assert(!response[0]&&feedState==FEED_FAULT);
  framed("CLEAR 12345678 11111111 22222222 33333333");assert(strstr(response,"CLEARED 12345678")&&feedState==FEED_IDLE&&feedReady&&!faultReason);
  testB.levels&=~PEEL_SWITCH_PIN;delay_ms(PEEL_RESTART_MS+PEEL_DEBOUNCE_MS);idle();
  assert(requestResult==REQUEST_FAULT&&!resetCalls);
  assert(Motor_Reserve(1));framed("CLEAR 12345678 11111111 22222222 33333333");assert(strstr(response,"BUSY")&&feedState==FEED_RESERVED);
  Motor_Start();framed("CLEAR 12345678 11111111 22222222 33333333");assert(strstr(response,"BUSY")&&feedState==FEED_RUNNING);pulse();
  delay_ms(PEEL_RESTART_MS+PEEL_DEBOUNCE_MS);assert(peelRunning);
  testB.levels|=PEEL_SWITCH_PIN;delay_ms(1);idle();
 }
 optionsFault=1;Motor_Fault(FAULT_SETTINGS);
 framed("CLEAR 12345678 11111111 22222222 33333333");assert(strstr(response,"ERROR SETTINGS")&&feedState==FEED_FAULT&&!feedReady);
 optionsFault=0;settingsFault=1;
 framed("CLEAR 12345678 11111111 22222222 33333333");assert(strstr(response,"ERROR SETTINGS")&&feedState==FEED_FAULT);
 settingsFault=0;mode=MODE_MENU;
 framed("CLEAR 12345678 11111111 22222222 33333333");assert(strstr(response,"BUSY")&&feedState==FEED_FAULT);
 mode=MODE_TEST;framed("CLEAR 12345678 11111111 22222222 33333333");assert(strstr(response,"CLEARED")&&mode==MODE_TEST&&!feedReady);idle();
 assert(settingWrites==writes&&!memcmp(saved,memory,sizeof memory)&&!resetCalls);
}else if(!strcmp(argv[1],"inputtest")){
 int writes=settingWrites;
 framed("TESTREAD 12345678");assert(strstr(response,"TEST 12345678")&&mode==MODE_NORMAL);
 framed("TEST 12345678 00000000 22222222 33333333 00000001");assert(!response[0]&&mode==MODE_NORMAL);
 assert(Motor_Reserve(1));Motor_Start();
 framed("TEST 12345678 11111111 22222222 33333333 00000001");assert(strstr(response,"BUSY")&&mode==MODE_NORMAL);pulse();
 testB.levels&=~PEEL_SWITCH_PIN;
 framed("TEST 12345678 11111111 22222222 33333333 00000001");assert(mode==MODE_TEST&&!feedReady&&!peelRunning);idle();
 int oldStarts=starts;
 delay_ms(UI_TIMEOUT_MS+PEEL_TIMEOUT_MS+100);KeyScan();assert(mode==MODE_TEST);idle();
 manualRequest();command(7,1);assert(starts==oldStarts&&mode==MODE_TEST);idle();
 press(BUTTON_PIN,20);press(MENU_BUTTON_PIN,BUTTON_HOLD_MS*6);assert(mode==MODE_TEST&&starts==oldStarts);idle();
 testB.levels|=PEEL_SWITCH_PIN;delay_ms(PEEL_DEBOUNCE_MS+2);assert(testSwitchChanges==1);idle();
 testB.levels&=~PEEL_SWITCH_PIN;delay_ms(PEEL_DEBOUNCE_MS+2);assert(testSwitchChanges==2);idle();
 framed("TESTREAD 12345678");assert(strstr(response,"TEST 12345678")&&testSwitchChanges==2);
 framed("TEST 12345678 11111111 22222222 33333333 00000001");assert(testSwitchChanges==2);idle();
 assert(settingWrites==writes);
 framed("TEST 12345678 11111111 22222222 33333333 00000000");assert(mode==MODE_NORMAL&&feedReady);
 delay_ms(PEEL_RESTART_MS+PEEL_DEBOUNCE_MS);assert(peelRunning);
}else if(!strcmp(argv[1],"peelafter")){
 // Every width takes up while idle and after a short index move.
 testB.levels&=~PEEL_SWITCH_PIN;assert(Motor_Reserve(1));Motor_Start();pulse();
 assert(feedState==FEED_IDLE);
 delay_ms(PEEL_RESTART_MS+PEEL_DEBOUNCE_MS);assert(peelRunning);
 testB.levels|=PEEL_SWITCH_PIN;delay_ms(1);assert(!peelRunning);
 testB.levels&=~PEEL_SWITCH_PIN;delay_ms(PEEL_RESTART_MS+PEEL_DEBOUNCE_MS);assert(peelRunning);
 if(!FEEDER_WIDE){assert(Motor_Reserve(1));Motor_Start();pulse();delay_ms(PEEL_RESTART_MS+PEEL_DEBOUNCE_MS);assert(peelRunning);}
 delay_ms(PEEL_TIMEOUT_MS);assert(feedState==FEED_FAULT&&faultReason==FAULT_PEEL);idle();
}else if(!strcmp(argv[1],"peel")||!strcmp(argv[1],"peelwrap")||!strcmp(argv[1],"peeltimeout")){
 if(!strcmp(argv[1],"peelwrap")){now=UINT32_MAX-100U;peelOffAt=now;}
 if(!FEEDER_WIDE){assert(Motor_Reserve(99));Motor_Start();}
 else {assert(Motor_Reserve(1));Motor_Start();pulse();}
 testB.levels&=~PEEL_SWITCH_PIN;delay_ms(PEEL_RESTART_MS+PEEL_DEBOUNCE_MS);
 assert(peelRunning&&!(testA.levels&MOTOR_PEEL_A_PIN));
 if(!strcmp(argv[1],"peeltimeout")){
  // Keep index deadline out of the way to exercise the independent peel guard.
  feedStartedAt=now;delay_ms(PEEL_TIMEOUT_MS);assert(feedState==FEED_FAULT&&!peelRunning&&faultReason==FAULT_PEEL);
  assert((testA.levels&MOTOR_ALL_PINS)==MOTOR_ALL_PINS);manualRequest();assert(feedState==FEED_FAULT);
 }else{
  // Opening stops in one tick, without stopping index/counting.
  testB.levels|=PEEL_SWITCH_PIN;delay_ms(1);assert(!peelRunning&&(testA.levels&MOTOR_PEEL_A_PIN));
  if(!FEEDER_WIDE)assert(feedState==FEED_RUNNING&&!(testA.levels&MOTOR_INDEX_B_PIN));
  testB.levels&=~PEEL_SWITCH_PIN;delay_ms(PEEL_RESTART_MS-1);assert(!peelRunning);
  delay_ms(1);assert(peelRunning);
  // A transient closure cannot restart the motor.
  testB.levels|=PEEL_SWITCH_PIN;delay_ms(1);testB.levels&=~PEEL_SWITCH_PIN;delay_ms(2);
  testB.levels|=PEEL_SWITCH_PIN;delay_ms(PEEL_RESTART_MS+1);assert(!peelRunning);
  if(!FEEDER_WIDE){while(feedState==FEED_RUNNING)pulse();}
  testB.levels&=~PEEL_SWITCH_PIN;delay_ms(PEEL_RESTART_MS+PEEL_DEBOUNCE_MS);
  assert(peelRunning);
  // Settings always stop idle peeling and opening the switch cannot restart it.
  press(MENU_BUTTON_PIN,3*BUTTON_HOLD_MS+50);assert(mode==MODE_ADDR&&!peelRunning);
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
  delay_ms(FEED_TIMEOUT_MS);assert(feedState==FEED_FAULT&&requestResult==REQUEST_FAULT&&faultReason==FAULT_INDEX);
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
  manualRequest();assert(feedState==FEED_RUNNING&&starts==2);
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
   assert((testA.levels&MOTOR_ALL_PINS)==MOTOR_ALL_PINS);manualRequest();assert(!starts);
  }else{
   assert(resetCalls==1&&strstr(response,"RESET"));manualRequest();assert(!starts);
   assert(memory[0]==7&&memory[1]==3);
  }
 }else if(!strcmp(argv[1],"race")){
  injectAck=1;command(7,9);assert(starts==1&&motorCount==9&&feedState==FEED_RUNNING);
  command(7,2);assert(!strcmp(response,"Busy\\n")&&motorCount==9&&starts==1);
  for(int n=0;n<8;n++)pulse();assert(feedState==FEED_RUNNING);pulse();assert(feedState==FEED_IDLE);idle();
 }else if(!strcmp(argv[1],"startup")){
  assert(starts==0);
  command(7,2);assert(!strcmp(response,"OK\\n")&&feedState==FEED_RUNNING);
 }else if(!strcmp(argv[1],"zero")){
  assert(currentCount==(FEEDER_WIDE?1:2)&&memory[1]==currentCount);command(7,0);assert(motorCount==currentCount);while(feedState==FEED_RUNNING)pulse();assert(feedState==FEED_IDLE);idle();
  mode=MODE_COUNT;editValue=99;press(MENU_BUTTON_PIN,10);assert(editValue==1&&currentCount==(FEEDER_WIDE?1:2));mode=MODE_NORMAL;
  currentCount=0;assert(!Motor_Reserve(0));assert(feedState==FEED_IDLE);
 }else if(!strcmp(argv[1],"early")){
  injectPulse=1;command(7,1);assert(starts==1&&feedState==FEED_IDLE);idle();
 }else if(!strcmp(argv[1],"display")){
  command(7,1);int before=displayCalls;injectRender=1;RefreshDisplay();
  assert(feedState==FEED_IDLE&&displayDirty);assert(displayCalls==before+1);
  Feeder_Run();assert(!displayDirty);idle();
  before=displayCalls;manualRequest();assert(displayCalls==before&&feedState==FEED_RUNNING);
 }else if(!strcmp(argv[1],"timeout")||!strcmp(argv[1],"wrap")){
  if(!strcmp(argv[1],"wrap"))now=UINT32_MAX-5U;
  assert(Motor_Reserve(2));Motor_Start();int before=displayCalls;
  delay_ms(FEED_TIMEOUT_MS-1);assert(feedState==FEED_RUNNING);
  delay_ms(1);assert(feedState==FEED_FAULT&&displayCalls==before);
  assert((testA.levels&MOTOR_ALL_PINS)==MOTOR_ALL_PINS);
  manualRequest();assert(feedState==FEED_FAULT&&starts==1);
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
def main():
 with tempfile.TemporaryDirectory(prefix='v485-fix-check-') as d:
  q=Path(d);(q/'stm32f1xx_hal.h').write_text(hal);(q/'app.c').write_text(app);(q/'rx.c').write_text(rx)
  for wide in [0,1]:
   for module in ['app','rx']:
    exe=q/(module+str(wide));subprocess.run(['gcc','-std=c11','-Wall','-Wextra','-Wno-misleading-indentation','-Werror','-fsanitize=undefined,address','-g','-I',d,'-I',str(p/'src'),'-DFEEDER_WIDE='+str(wide),str(q/(module+'.c')),'-o',str(exe)],check=True)
    if module=='app':
     for case in ['bootpeel','clearfault','peelidle','inputtest','peelafter','defaults','longjog','longjoglimit','longjogwrap','longjogstall','longjogdeadline','longjogstop','jog','remotecount','options','optionsrecords','optionscorrupt','optionsreadfail','race','startup','zero','early','display','timeout','wrap','feedback','readfail','countreadfail','blank','unassigned','unassignedremote','unassignedboot','bootblank','bootblankfail','invalidid','savefail','readbackfail','diagnostics','buttons','twobuttons','untyped','typereadfail','type','locate','heldstartup','menuboot','menutiming','menubootfail','menufault','assignheld','menubusy','assign','assignexpired','assignfail','peel','peelwrap','peeltimeout','savesuccess','slowack','framed','badframed','completion','completionearly','completionfault','completioneeprom','bootidle','bootbusy','bootreserved','bootwrong','bootcrc','bootfault','booteeprom']:subprocess.run([str(exe),case],check=True)
    else:subprocess.run([str(exe)],check=True)
 print('All actual-source checks passed. Temporary files only; no project tests folder created.')

if __name__ == "__main__":
 main()
