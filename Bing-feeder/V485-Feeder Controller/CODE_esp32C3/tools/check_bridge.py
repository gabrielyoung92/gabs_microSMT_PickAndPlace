#!/usr/bin/env python3
"""Exercise the real controller source against uploader packets, without hardware.

Run with Python and a native g++ compiler. No serial port is opened.
"""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile

project = Path(__file__).resolve().parents[1]
uploader_path = project.parents[1] / 'V485-feeder/CODE_feeder/tools/rs485_upload.py'
spec = importlib.util.spec_from_file_location('rs485_upload', uploader_path)
uploader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(uploader)

# Packets come from the actual uploader, not a second copy of its wire format.
bodies = ['HELLO', 'INFO', 'BOOT', 'BEGIN 00000001 00000400 12345678',
          'DATA 00000000 ' + bytes(range(uploader.CHUNK)).hex().upper(), 'END 12345678',
          'IDENT 12345678', 'SETID 12345678 11111111 22222222 33333333 00000008']
replies = ['READY 00000001 08002000 0000E000', 'APP 00000001 00000400 12345678',
           'RESET', 'OK 00000000', 'OK 00000020', 'DONE 12345678',
           'IDENT 12345678 11111111 22222222 33333333 00000001', 'ID 12345678 00000008']
packets = [(uploader.packet(address, body).decode(), uploader.packet(address, reply).decode())
           for address in (0, 7, 99) for body, reply in zip(bodies, replies)]
vectors = ',\n'.join('{' + json.dumps(req) + ', ' + json.dumps(reply) + '}' for req, reply in packets)
invalid_requests = ',\n'.join(json.dumps(uploader.packet(7, body).decode())
                              for body in ('N7 F4', 'HELLOX', 'APP 00000001', 'HELLO\rN7 F4',
                                           'FEED 00000001 00000001 00000004',
                                           'STATUS 00000001 00000001'))

arduino = r'''
#pragma once
#include <cassert>
#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <string>
#include <vector>
constexpr int HIGH=1, LOW=0, OUTPUT=1, SERIAL_8N1=0;
inline uint32_t clockMs=0;
inline int direction=LOW;
inline bool acknowledgeFeed=false;
inline bool loseAccept=false, faultFeed=false, unknownFeed=false, stallFeed=false;
inline unsigned lostStatusReplies=0, statusRequests=0;
inline uint32_t feedStarted=0, completionDelay=500;
inline std::string usbAtFeedStart;
inline std::string feedNoise;
inline std::string lateReply;
inline uint32_t lateReplyAt=0;
inline std::vector<std::string> transmissions;
inline uint32_t millis(){ return clockMs; }
void deliverLateReply();
std::string frame(const std::string& body);
inline void delay(uint32_t ms){ clockMs+=ms; deliverLateReply(); }
inline void delayMicroseconds(uint32_t){}
inline void pinMode(int,int){}
inline void digitalWrite(int pin,int value){ if(pin==9) direction=value; }
struct Port {
    std::string rx,tx;
    size_t cursor=0;
    void begin(uint32_t){}
    int available(){ return int(rx.size()-cursor); }
    int read(){ return available() ? static_cast<unsigned char>(rx[cursor++]) : -1; }
    size_t write(const uint8_t* data,size_t size){ tx.append(reinterpret_cast<const char*>(data),size); return size; }
    size_t write(uint8_t ch){ tx+=char(ch); return 1; }
    void println(const char* text){ tx+=text; tx+="\r\n"; }
    void printf(const char* format,...){ char out[512]; va_list args; va_start(args,format); vsnprintf(out,sizeof(out),format,args); va_end(args); tx+=out; }
};
inline Port Serial;
struct HardwareSerial:Port {
    explicit HardwareSerial(uint8_t){}
    void begin(uint32_t,int,uint8_t,uint8_t){}
    void flush(){
        assert(direction==HIGH);
        assert(!tx.empty() && tx.back()=='\n');
        transmissions.push_back(tx);
        unsigned address=0; unsigned long session=0,sequence=0,count=0;
        if(sscanf(tx.c_str(),"B%u FEED %lx %lx %lx",&address,&session,&sequence,&count)==4){
            feedStarted=clockMs;usbAtFeedStart=Serial.tx;
            rx+=feedNoise;
            if(acknowledgeFeed && !loseAccept){
                char body[80];
                snprintf(body,sizeof(body),"B%02u ACCEPT %08lX %08lX",address,session,sequence);
                rx+=frame(body);
            }
        }else if(sscanf(tx.c_str(),"B%u STATUS %lx %lx",&address,&session,&sequence)==3){
            ++statusRequests;
            assert(Serial.tx==usbAtFeedStart); // No USB success before a DONE reply.
            if(lostStatusReplies)--lostStatusReplies;
            else if(acknowledgeFeed){
                const char* status=unknownFeed?"UNKNOWN":faultFeed?"FAULT":
                    (stallFeed||uint32_t(clockMs-feedStarted)<completionDelay)?"RUNNING":"DONE";
                char body[80];snprintf(body,sizeof(body),"B%02u %s %08lX %08lX",address,status,session,sequence);
                rx+=frame(body);
            }
        }
        tx.clear();
    }
};
'''

harness = r'''
#include "main.cpp"
#include <iostream>
#include <utility>
#include <algorithm>
void deliverLateReply(){if(!lateReply.empty() && clockMs>=lateReplyAt){Serial485.rx+=lateReply;lateReply.clear();}}
std::string frame(const std::string& body){
    char crc[16];snprintf(crc,sizeof(crc)," %08lX\n",static_cast<unsigned long>(packetCrc32(body.data(),body.size())));
    return body+crc;
}
void reset(){
    Serial.rx.clear(); Serial.tx.clear(); Serial.cursor=0;
    Serial485.rx.clear(); Serial485.tx.clear(); Serial485.cursor=0;
    commandLength=updateReplyLength=0;
    discardingCommand=discardingUpdateReply=updateTrafficSeen=false;
    clockMs=lastUpdateAt=lastCommandByteAt=0;
    acknowledgeFeed=false; transmissions.clear(); direction=LOW;
    loseAccept=faultFeed=unknownFeed=stallFeed=false;
    lostStatusReplies=statusRequests=0;feedStarted=0;completionDelay=500;usbAtFeedStart.clear();
    feedSession=1;feedSequence=0;feedNoise.clear();lateReply.clear();
}
void pump(){ for(int i=0;i<12;++i) loop(); }
void usb(const std::string& text){ Serial.rx+=text; pump(); }
void bus(const std::string& text){ Serial485.rx+=text; pump(); }
size_t feedFrames(){return std::count_if(transmissions.begin(),transmissions.end(),[](const std::string& s){return s.find(" FEED ")!=std::string::npos;});}
int main(){
    setup(); reset();
    const std::pair<std::string,std::string> packets[]={VECTORS};
    for(const auto& pair:packets){
        reset();
        const auto& request=pair.first; const auto& reply=pair.second;
        // USB and UART can split a packet at any byte; do not forward fragments.
        for(size_t i=0;i<request.size();++i){
            usb(request.substr(i,1));
            assert(transmissions.size()==(i+1==request.size()?1u:0u));
        }
        assert(transmissions[0]==request && direction==LOW && Serial.tx.empty());
        for(size_t i=0;i<reply.size();++i){
            bus(reply.substr(i,1));
            assert(Serial.tx==(i+1==reply.size()?reply:std::string()));
        }
        // No motion is sent during an upload, even after a correct update reply.
        usb("M600 N7 F4\n");
        assert(transmissions.size()==1 && Serial.tx.find("error: update/settings")!=std::string::npos);
        clockMs+=UPDATE_IDLE_TIMEOUT_MS;
        acknowledgeFeed=true; usb("N7 F4\n");
        assert(feedFrames()==1 && transmissions[1]==frame("B07 FEED 00000001 00000001 00000004"));
        assert(statusRequests>1 && clockMs-feedStarted>=completionDelay && Serial.tx.find("ok N7 F4\n")!=std::string::npos);
    }
    const std::string good=packets[0].first;
    // CRLF survives the bridge; CRC is still computed without CR/LF.
    reset(); std::string crlf=good.substr(0,good.size()-1)+"\r\n";
    usb(crlf); assert(transmissions==std::vector<std::string>{crlf});
    bus(crlf); assert(Serial.tx==crlf);
    // Corrupt destination, payload and CRC are silently dropped in both directions.
    for(size_t position: {size_t(1),size_t(4),good.size()-3}){
        reset(); std::string bad=good; bad[position]^=1;
        usb(bad); bus(bad); assert(transmissions.empty() && Serial.tx.empty());
    }
    reset(); usb("B\nB0\nB07\nB07 \n"); assert(transmissions.empty());
    for(const std::string& bad:std::vector<std::string>{INVALID_REQUESTS}){
        reset(); usb(bad); assert(transmissions.empty());
    }
    reset(); usb(std::string("B07 \0N7 F4\n",12)); assert(transmissions.empty());
    reset(); usb("B"+std::string(UPDATE_PACKET_MAX_LENGTH,'x')+"N7 F4\n");
    assert(transmissions.empty()); usb(good); assert(transmissions.size()==1);
    reset(); bus("B"+std::string(UPDATE_PACKET_MAX_LENGTH,'x')+"\n");
    bus(packets[0].second); assert(Serial.tx==packets[0].second);
    // A stalled USB fragment and its command-looking tail are discarded through LF.
    reset(); usb("B07 DATA"); clockMs+=USB_COMMAND_TIMEOUT_MS; pump();
    usb("N7 F4\n"); assert(transmissions.empty());
    usb(good); assert(transmissions.size()==1);
    // Legacy console bounds, grammar, ACKs and single-send timeout behavior remain.
    reset(); acknowledgeFeed=true;
    usb("n07\tf04\r\n"); assert(feedFrames()==1 && transmissions[0]==frame("B07 FEED 00000001 00000001 00000004"));
    usb("N7 F4 EXTRA\n"); usb(std::string(33,' ')+"N7 F4\n");
    assert(feedFrames()==1);
    reset(); usb("N7 F4\n");
    assert(feedFrames()==1 && Serial.tx.find("Not retried")!=std::string::npos && Serial.tx.find("ok ")==std::string::npos);
    // The review's delayed ID-7 OK cannot falsely confirm a command to ID 8.
    reset();usb("N7 F4\n");Serial.tx.clear();
    lateReply="OK\n";lateReplyAt=clockMs+100;usb("N8 F4\n");
    assert(feedFrames()==2 && Serial.tx.find("ok ")==std::string::npos);
    reset();usb("N7 F4\n");Serial.tx.clear();
    lateReply=frame("B07 ACCEPT 00000001 00000001");lateReplyAt=clockMs+100;usb("N7 F4\n");
    assert(feedFrames()==2 && Serial.tx.find("ok ")==std::string::npos);
    // Wrong feeder, old request, old session, bad CRC and unframed OK are ignored.
    for(const std::string& noise:std::vector<std::string>{
        frame("B08 ACCEPT 00000001 00000001"),frame("B07 ACCEPT 00000001 00000000"),
        frame("B07 ACCEPT 00000002 00000001"),"B07 ACCEPT 00000001 00000001 00000000\n","OK\n",
        frame("B08 DONE 00000001 00000001"),frame("B07 DONE 00000002 00000001"),
        frame("B07 DONE 00000001 00000000")}){
        reset();acknowledgeFeed=true;feedNoise=noise;usb("N7 F4\n");
        assert(Serial.tx.find("ok N7 F4\n")!=std::string::npos);
        reset();feedNoise=noise;usb("N7 F4\n");
        assert(Serial.tx.find("ok ")==std::string::npos && feedFrames()==1);
    }
    reset();feedNoise=frame("B07 BUSY 00000001 00000001");usb("N7 F4\n");
    assert(Serial.tx.find("error: feeder busy")!=std::string::npos && feedFrames()==1 && !statusRequests);
    for(const char* status:{"ACCEPT","BUSY","RUNNING","DONE","FAULT","UNKNOWN"}){
        reset();bus(frame(std::string("B07 ")+status+" 00000001 00000001"));
        assert(Serial.tx.empty() && !updateActive());
    }
    // Lost replies only retry STATUS; accepted/running/fault/unknown never return ok.
    reset();acknowledgeFeed=true;loseAccept=true;lostStatusReplies=2;usb("M600 N7 F4\n");
    assert(feedFrames()==1 && statusRequests>=3 && Serial.tx=="ok N7 F4\n");
    reset();acknowledgeFeed=true;completionDelay=0;usb("M600 N7 F0\n");
    assert(feedFrames()==1 && statusRequests==1 && Serial.tx=="ok N7 F0\n");
    reset();acknowledgeFeed=true;faultFeed=true;usb("M600 N7 F4\n");
    assert(feedFrames()==1 && Serial.tx.find("error: feeder fault")!=std::string::npos && Serial.tx.find("ok ")==std::string::npos);
    reset();acknowledgeFeed=true;unknownFeed=true;usb("M600 N7 F4\n");
    assert(feedFrames()==1 && Serial.tx.find("outcome unknown")!=std::string::npos && Serial.tx.find("ok ")==std::string::npos);
    reset();acknowledgeFeed=true;stallFeed=true;usb("M600 N7 F4\n");
    assert(feedFrames()==1 && clockMs>=FEED_COMPLETION_TIMEOUT_MS && Serial.tx.find("completion timeout")!=std::string::npos && Serial.tx.find("ok ")==std::string::npos);
    reset();feedSequence=UINT32_MAX;acknowledgeFeed=true;usb("N7 F4\n");
    assert(feedSequence==1 && feedSession==0x12345678 && Serial.tx.find("ok N7 F4\n")!=std::string::npos);
    reset();clockMs=UINT32_MAX-100;acknowledgeFeed=true;usb("M600 N7 F4\n");
    assert(Serial.tx=="ok N7 F4\n" && feedFrames()==1);
    // Deadline subtraction works across the 32-bit millis() rollover.
    reset(); clockMs=UINT32_MAX-100; usb(good);
    clockMs+=UPDATE_IDLE_TIMEOUT_MS-1; assert(updateActive());
    ++clockMs; assert(!updateActive());
    // Expired traffic cannot relock feeds after another millis() rollover.
    reset(); usb(good); clockMs+=UPDATE_IDLE_TIMEOUT_MS; pump();
    clockMs=0; assert(!updateActive());
    std::cout<<"Controller checks passed: uploader bridge, correlated completion, single advance, lost/stale replies, faults and deadlines\n";
}
'''.replace('VECTORS', vectors).replace('INVALID_REQUESTS', invalid_requests)

with tempfile.TemporaryDirectory(prefix='v485-controller-check-') as folder:
    temp = Path(folder)
    (temp / 'Arduino.h').write_text(arduino)
    (temp / 'esp_system.h').write_text('#pragma once\n#include <stdint.h>\ninline uint32_t esp_random(){return 0x12345678;}\n')
    (temp / 'check.cpp').write_text(harness)
    subprocess.run(['g++', '-std=c++17', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined',
                    '-fno-omit-frame-pointer', '-I', str(temp), '-I', str(project / 'src'),
                    str(temp / 'check.cpp'), '-o', str(temp / 'check')], check=True)
    subprocess.run([str(temp / 'check')], check=True)
