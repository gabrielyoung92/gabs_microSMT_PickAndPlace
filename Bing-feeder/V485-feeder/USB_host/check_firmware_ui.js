// Firmware labels compare exact builds, including unknown/error states. No browser/hardware.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const html=fs.readFileSync(__dirname+'/dashboard.html','utf8');
const context={state:{available_firmware:{available:true,version:'0.1.2',crc32:'ABCDEF12',bytes:100}}};
vm.createContext(context);vm.runInContext(html.slice(html.indexOf('function firmwareInfo('),html.indexOf('function loadHardware(')),context);
const f={known:true,firmware_info:{crc32:'ABCDEF12',size:100}};
assert.equal(context.firmwareLabel(f),'v0.1.2 · Current');assert.equal(context.needsFirmware(f),false);
f.firmware_info={crc32:'11111111',size:100,version:'0.1.1'};
assert.equal(context.firmwareLabel(f),'v0.1.1 · Update available');assert(context.needsFirmware(f));
f.firmware_info.error='No INFO reply';assert.equal(context.firmwareLabel(f),'Unknown');assert(context.needsFirmware(f));
f.firmware_info=null;assert.equal(context.firmwareLabel(f),'Unknown');assert(context.needsFirmware(f));
context.state.available_firmware.available=false;assert.equal(context.needsFirmware(f),false);
assert(!html.includes('pendingUpdateAddress'));
new vm.Script(html.match(/<script>([\s\S]*)<\/script>/)[1]);
console.log('Firmware UI checks passed: exact build comparison, current/outdated/unknown labels, error handling, shared queue and script syntax.');
