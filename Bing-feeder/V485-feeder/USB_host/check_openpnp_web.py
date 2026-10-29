import tempfile,os
from java.io import File
from java.lang import System
from org.openpnp.model import Configuration, Location, LengthUnit, Part, Package, Length, Footprint
root=tempfile.mkdtemp(prefix='microsmt-control-check-')
System.setProperty('user.home',root)
Configuration.initialize(File(root))
from org.openpnp.machine.reference import ReferenceMachine, ReferenceNozzleTip
field=Configuration.get().getClass().getDeclaredField('machine')
field.setAccessible(True)
field.set(Configuration.get(),ReferenceMachine())
scope={}
execfile(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'OpenPnP-Web.py'),scope)
scope=scope['_microsmt']
MM=LengthUnit.Millimeters
class Cfg(object):
 def __init__(self):self.saved=0;self.parts={'P1':Part('P1'),'P2':Part('P2')};self.fail=False
 def getPackages(self):return self.packages.values()
 def getPackage(self,key):return self.packages.get(key)
 def addPackage(self,p):self.packages[str(p.getId())]=p
 def removePackage(self,p):self.packages.pop(str(p.getId()),None)
 def addPart(self,p):self.parts[str(p.getId())]=p
 def removePart(self,p):self.parts.pop(str(p.getId()),None)
 def getParts(self):return self.parts.values()
 def getPart(self,key):return self.parts.get(key)
 def save(self):
  self.saved+=1
  if self.fail and self.saved%2==0:raise Exception('simulated save failure')
class Tool(object):
 def __init__(self,identifier,location):self.identifier,self.location=identifier,location
 def getId(self):return self.identifier
 def getName(self):return self.identifier
 def getLocation(self):return self.location
 def moveTo(self,target,speed):self.location=target
 def getHead(self):return head
 def getCompatibleNozzleTips(self):return getattr(self,'tips',[])
 def getNozzleTip(self):return getattr(self,'loaded',None)
class Head(object):
 def getId(self):return 'H1'
 def getName(self):return 'Main head'
 def getNozzles(self):return [nozzle]
 def getCameras(self):return [camera]
 def getDefaultNozzle(self):return nozzle
 def getDefaultCamera(self):return camera
class Planner(object):
 def waitForCompletion(self,*args):pass
class Machine(object):
 def __init__(self):self.feeders=[];self.drivers=[];self.actuators=[];self.enabled=False;self.homed=True;self.busy=False
 def getFeeders(self):return self.feeders
 def getFeeder(self,identifier):return next((f for f in self.feeders if str(f.getId())==identifier),None)
 def getDrivers(self):return self.drivers
 def getNozzleTips(self):return list(Configuration.get().getMachine().getNozzleTips())
 def addNozzleTip(self,tip):Configuration.get().getMachine().addNozzleTip(tip)
 def removeNozzleTip(self,tip):Configuration.get().getMachine().removeNozzleTip(tip)
 def getProperty(self,key):return Configuration.get().getMachine().getProperty(key)
 def setProperty(self,key,value):Configuration.get().getMachine().setProperty(key,value)
 def getHeads(self):return [head]
 def getDefaultHead(self):return head
 def getAllCameras(self):raise AssertionError("Camera access is outside feeder dashboard scope")
 def getActuatorByName(self,name):return next((a for a in self.actuators if a.getName()==name),None)
 def addDriver(self,d):self.drivers.append(d)
 def removeDriver(self,d):self.drivers.remove(d)
 def addActuator(self,a):self.actuators.append(a)
 def removeActuator(self,a):self.actuators.remove(a)
 def addFeeder(self,f):self.feeders.append(f)
 def removeFeeder(self,f):self.feeders.remove(f)
 def isEnabled(self):return self.enabled
 def isHomed(self):return self.homed
 def isBusy(self):return self.busy
 def execute(self,call,*args):return call.call()
 def getMotionPlanner(self):return Planner()
class Job(object):
 def getTotalActivePlacements(self,p):return 2
 def getActivePlacements(self,p):return 1
 def getRootPanelLocation(self):return None
 def getFile(self):return None
class Panel(object):
 def refresh(self,feeder):pass
 def repaint(self):pass
 def getJob(self):return Job()
class Gui(object):
 def getPackagesTab(self):return Panel()
 def getPartsTab(self):return Panel()
 def getFeedersTab(self):return Panel()
 def getJobTab(self):return Panel()
camera=Tool('CAM',Location(MM,100,200,9,0));nozzle=Tool('NZ',Location(MM,105,205,-25,90));head=Head()
config=Cfg();config.package=Package('PKG1');config.packages={'PKG1':config.package};machine=Machine();control=scope['WebControl'](config,machine,Gui());control.job_state=lambda:'Stopped'
result=control.action(dict(action='add_feeder',name='powered feeder',bus_id=7,part_id='P1'))
assert len(machine.drivers)==1 and len(machine.actuators)==1 and config.saved==1
assert result['feeder']['bus_id']==7 and result['feeder']['part_id']=='P1'
feeder=machine.feeders[0]
assert not feeder.isEnabled() and feeder.getLocation().getX()==0
assert machine.drivers[0].getTcp().getPort()==5001
from org.openpnp.machine.reference.feeder import ReferenceStripFeeder
strip=ReferenceStripFeeder();machine.feeders.append(strip)
assert len(control.snapshot()['feeders'])==1
assert 'tools' not in control.snapshot() and 'job' not in control.snapshot()
for action in ('teach','save_feeder','move_camera','test_feed','test_pick','home','jog','job_start'):
 try:control.action(dict(action=action));raise AssertionError('Forbidden action accepted: '+action)
 except ValueError:pass
for args in (dict(bus_id=7,part_id='P1'),dict(bus_id=8,part_id='missing')):
 try:control.action(dict(args,action='add_feeder',name='invalid'));raise AssertionError('Invalid feeder accepted')
 except ValueError:pass
assert len(machine.feeders)==2 and len(machine.drivers)==1
machine.enabled=True
try:control.action(dict(action='add_feeder',name='blocked',bus_id=8));raise AssertionError('Enabled machine allowed mutation')
except ValueError:pass
machine.enabled=False;control.job_state=lambda:'Running'
try:control.action(dict(action='add_feeder',name='blocked',bus_id=8));raise AssertionError('Running job allowed mutation')
except ValueError:pass
control.job_state=lambda:'Stopped'
# Assigning a loaded part changes only that field, preserving taught location.
feeder.setLocation(Location(MM,123.4,56.7,-8.9,27))
original_location=feeder.getLocation();original_actuator=feeder.getActuatorName();original_enabled=feeder.isEnabled()
assignment=dict(action='set_feeder_part',bus_id=7,feeder_id=str(feeder.getId()),part_id='P2')
result=control.action(assignment)
assert result['feeder']['part_id']=='P2' and feeder.getPart()==config.parts['P2']
assert feeder.getLocation()==original_location and feeder.getActuatorName()==original_actuator and feeder.isEnabled()==original_enabled
for change in (dict(feeder_id='wrong'),dict(bus_id=8),dict(part_id='missing')):
 try:control.action(dict(assignment,**change));raise AssertionError('Invalid assignment accepted')
 except ValueError:pass
assert feeder.getPart()==config.parts['P2'] and feeder.getLocation()==original_location
machine.busy=True
try:control.action(assignment);raise AssertionError('Busy machine allowed assignment')
except ValueError:pass
machine.busy=False;control.job_state=lambda:'Running'
try:control.action(assignment);raise AssertionError('Running job allowed assignment')
except ValueError:pass
control.job_state=lambda:'Stopped'
real_save=config.save;attempts=[0]
def failed_save():
 attempts[0]+=1
 if attempts[0]==1:raise Exception('Simulated assignment save failure')
config.save=failed_save
try:control.action(dict(assignment,part_id='P1'));raise AssertionError('Save failure ignored')
except Exception as error:assert 'Simulated' in str(error)
finally:config.save=real_save
assert feeder.getPart()==config.parts['P2'] and feeder.getLocation()==original_location
control.action(dict(assignment,part_id=''));assert feeder.getPart() is None
control.action(dict(assignment,part_id='P1'))
# The shared part editor preserves identity, feeder teaching and other settings.
p1=config.parts['P1'];p1.setHeight(Length(0.1,LengthUnit.Inches));speed=p1.getSpeed()
original=control.describe_part(p1)
assert abs(original['height_mm']-2.54)<0.000001
edit=dict(action='edit_part',part_id='P1',name='Resistor',package_id='PKG1',height_mm=1.2,expected=original)
result=control.action(edit)
assert result['part']['name']=='Resistor' and result['part']['height_mm']==1.2
assert p1.getPackage()==config.package and p1.getId()=='P1' and p1.getSpeed()==speed
assert feeder.getLocation()==original_location and feeder.getPart()==p1
for invalid in (edit,dict(edit,expected=result['part'],height_mm=-1),dict(edit,expected=result['part'],package_id='missing')):
 try:control.action(invalid);raise AssertionError('Invalid/stale part edit accepted')
 except ValueError:pass
assert control.describe_part(p1)==result['part']
# Saving failures roll all edited fields back.
real_save=config.save;attempts=[0]
def failed_part_save():
 attempts[0]+=1
 if attempts[0]==1:raise Exception('Simulated part editor save failure')
config.save=failed_part_save
try:control.action(dict(edit,expected=result['part'],name='Wrong',height_mm=9));raise AssertionError('Save failure ignored')
except Exception as error:assert 'Simulated' in str(error)
finally:config.save=real_save
assert control.describe_part(p1)==result['part'] and feeder.getLocation()==original_location
machine.busy=True
try:control.action(dict(edit,expected=result['part']));raise AssertionError('Busy part edit accepted')
except ValueError:pass
machine.busy=False
# Catalogue creation preserves copied package geometry and source identity.
footprint=config.package.getFootprint();footprint.setBodyWidth(2.0);footprint.setBodyHeight(1.0)
pad=Footprint.Pad();pad.setName('1');pad.setWidth(.5);pad.setHeight(1.0);footprint.addPad(pad)
source_package=control.describe_package(config.package)
result=control.action(dict(action='create_package',package_id='PKG2',description='Copied package',copy_from='PKG1'))
clone=config.getPackage('PKG2')
assert clone is not config.package and clone.getFootprint() is not footprint
assert result['package']['pad_count']==1 and result['package']['body_width_mm']==source_package['body_width_mm']
assert len(clone.getFootprint().getPads())==1 and control.describe_package(config.package)==source_package
clone.getFootprint().setBodyWidth(9);assert footprint.getBodyWidth()==2
result=control.action(dict(action='create_package',package_id='BLANK',description='',copy_from=''))
assert result['package']['pad_count']==0
created=control.action(dict(action='create_part',part_id='NEW',name='New resistor',package_id='PKG2',height_mm=.65))
assert created['part']['package_id']=='PKG2' and config.getPart('NEW').getPackage()==clone
assert feeder.getLocation()==original_location and feeder.getPart()==p1
for args in (dict(action='create_part',part_id='NEW',package_id='PKG2',height_mm=1),dict(action='create_part',part_id=' ',package_id='PKG2',height_mm=1),dict(action='create_part',part_id='INVALID',package_id='missing',height_mm=1),dict(action='create_package',package_id='PKG2'),dict(action='create_package',package_id='INVALID',copy_from='missing')):
 try:control.action(args);raise AssertionError('Invalid catalogue creation accepted')
 except ValueError:pass
# Interrupted creates remove only the newly added object, then restore disk.
for action,key in (('create_part','part_id'),('create_package','package_id')):
 real_save=config.save;attempts=[0]
 def failed_create_save():
  attempts[0]+=1
  if attempts[0]==1:raise Exception('Simulated catalogue save failure')
 config.save=failed_create_save
 try:control.action(dict(action=action,**{key:'FAIL','package_id':'FAIL' if action=='create_package' else 'PKG1','height_mm':1}));raise AssertionError('Create failure ignored')
 except Exception as error:assert 'Simulated' in str(error)
 finally:config.save=real_save
 assert config.getPart('FAIL') is None and config.getPackage('FAIL') is None
assert control.describe_package(config.package)==source_package
# Package editing changes only the explicitly selected description and tips.
real_machine=Configuration.get().getMachine()
tip1=ReferenceNozzleTip();tip1.setName('Small');tip2=ReferenceNozzleTip();tip2.setName('Large')
real_machine.addNozzleTip(tip1);real_machine.addNozzleTip(tip2)
config.package.addCompatibleNozzleTip(tip1)
config.package.setPickVacuumLevel(12.3)
footprint.setUnits(LengthUnit.Inches);pad.setX(.1);pad.setY(-.2);pad.setRotation(37);pad.setRoundness(50);pad.setMark(True)
from java.io import StringWriter
def serialized(package):
 writer=StringWriter();Configuration.createSerializer().write(package,writer);return str(writer.toString())
original_description=config.package.getDescription();before_xml=serialized(config.package);saved=config.saved
original=control.describe_package(config.package);snapshot=control.snapshot()
assert serialized(config.package)==before_xml and config.saved==saved
assert snapshot['api_version']==1 and len(snapshot['nozzle_tips'])==2
assert abs(original['pads'][0]['x']-2.54)<.000001 and original['pads'][0]['rotation']==37 and original['pads'][0]['mark']
args=dict(action='edit_package',package_id='PKG1',expected=original,description='Updated description',nozzle_tip_ids=[str(tip2.getId())])
result=control.action(args)
assert result['package']['description']=='Updated description' and result['package']['nozzle_tip_ids']==[str(tip2.getId())]
assert config.package.getFootprint()==footprint and config.package.getPickVacuumLevel()==12.3
for invalid in (args,dict(args,expected=result['package'],nozzle_tip_ids=['missing']),dict(args,expected=result['package'],nozzle_tip_ids=[str(tip2.getId())]*2),dict(args,expected=result['package'],description='x'*1025)):
 try:control.action(invalid);raise AssertionError('Invalid/stale package edit accepted')
 except ValueError:pass
assert control.describe_package(config.package)==result['package']
machine.busy=True
try:control.action(dict(args,expected=result['package']));raise AssertionError('Busy package edit accepted')
except ValueError:pass
machine.busy=False
# Save failure restores every edited field, preserving all other XML settings.
before_failure=serialized(config.package);real_save=config.save;attempts=[0]
def failed_package_save():
 attempts[0]+=1
 if attempts[0]==1:raise Exception('Simulated package save failure')
config.save=failed_package_save
try:control.action(dict(args,expected=result['package'],description='Failed',nozzle_tip_ids=[]));raise AssertionError('Package save failure ignored')
except Exception as error:assert 'Simulated' in str(error)
finally:config.save=real_save
assert serialized(config.package)==before_failure
# Explicitly clearing compatibility is allowed; source geometry remains exact.
cleared=control.action(dict(args,expected=result['package'],description='Updated description',nozzle_tip_ids=[]))
assert cleared['package']['nozzle_tip_ids']==[]
config.package.setDescription(original_description);config.package.addCompatibleNozzleTip(tip1)
assert serialized(config.package)==before_xml
# Nozzle telemetry is read-only, distinguishes loaded from compatible tips.
nozzle.tips=[tip1];nozzle.loaded=tip2
saved=config.saved;before=serialized(config.package)
snapshot=control.snapshot();n=snapshot['nozzles'][0]
assert snapshot['api_version']==1 and n['head_id']=='H1' and n['name']=='NZ'
assert n['nozzle_tip_ids']==[str(tip1.getId())] and n['loaded_tip_id']==str(tip2.getId())
assert config.saved==saved and serialized(config.package)==before
nozzle.loaded=None;nozzle.tips=[]
assert control.snapshot()['nozzles'][0]['loaded_tip_id']=='' and control.snapshot()['nozzles'][0]['nozzle_tip_ids']==[]
# Nozzle settings are read-only; all management and backup actions are gone.
saved=config.saved
for action in ('edit_nozzle','edit_nozzle_tip','configure_tip','create_nozzle_tip','configure_tip_holders','save_for_backup'):
 try:control.action(dict(action=action));raise AssertionError('Removed action accepted')
 except ValueError:pass
assert config.saved==saved
# Read-only job requirements use actual board instances, placement states and sides.
from org.openpnp.model import Job as NativeJob,Board,BoardLocation,Placement,Abstract2DLocatable
job=NativeJob();board=Board();Side=Abstract2DLocatable.Side
for identifier,part,side,enabled,kind in [('A',p1,Side.Top,True,Placement.Type.Placement),('B',config.parts['P2'],Side.Top,True,Placement.Type.Placement),('F',p1,Side.Top,True,Placement.Type.Fiducial),('D',p1,Side.Top,False,Placement.Type.Placement),('Z',p1,Side.Bottom,True,Placement.Type.Placement)]:
 placement=Placement(identifier);placement.setPart(part);placement.setSide(side);placement.setEnabled(enabled);placement.setType(kind);board.addPlacement(placement)
boards=[]
for identifier in ('B1','B2','SKIP'):
 location=BoardLocation(board);location.setId(identifier);location.setLocallyEnabled(identifier!='SKIP');job.addBoardOrPanelLocation(location);boards.append(location)
job.storePlacedStatus(boards[0],'A',True)
placement_b=next(p for p in boards[1].getBoard().getPlacements() if p.getId()=='B');job.storeEnabledState(boards[1],placement_b,False)
class JobPanel(Panel):
 def getJob(self):return job
control.gui.getJobTab=lambda:JobPanel()
saved=config.saved;requirements=control.job_requirements()
assert requirements['boards']==2 and requirements['total']==3 and requirements['remaining']==2,requirements
counts={p['part_id']:p for p in requirements['parts']}
assert counts['P1']['total']==2 and counts['P1']['remaining']==1 and counts['P2']['total']==1
assert config.saved==saved and not any(key in requirements for key in ('start','pause','resume'))
# Actual OpenPnP JSR-223 scope; replace bindings while callbacks remain active.
from javax.script import ScriptEngineManager, ScriptContext
from java.net import URL, URLConnection, HttpURLConnection
from java.io import OutputStream
from java.lang import String
from com.sun.net.httpserver import HttpServer
from org.apache.commons.io import IOUtils
import json
engine=ScriptEngineManager().getEngineByName('python')
engine.eval(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'OpenPnP-Web.py')).read())
loaded=engine.get('_microsmt');server=loaded['Companion'](control,0)
try:
 engine.getBindings(ScriptContext.ENGINE_SCOPE).clear();engine.eval('other_script = True')
 url='http://127.0.0.1:'+str(HttpServer.getAddress(server.server).getPort())
 connection=URL(url+'/state').openConnection()
 state=json.loads(str(IOUtils.toString(URLConnection.getInputStream(connection),'UTF-8')))
 assert state['online'] and len(state['feeders'])==1
 connection=URL(url+'/job').openConnection();requirements=json.loads(str(IOUtils.toString(URLConnection.getInputStream(connection),'UTF-8')));assert requirements['remaining']==2
 body=json.dumps(dict(action='add_feeder',name='second',bus_id=8,part_id='P1'))
 post=URL(url+'/action').openConnection();URLConnection.setDoOutput(post,True)
 URLConnection.setRequestProperty(post,'Content-Type','application/json')
 stream=URLConnection.getOutputStream(post)
 OutputStream.write(stream,String(body).getBytes('UTF-8'));OutputStream.close(stream)
 code=HttpURLConnection.getResponseCode(post)
 stream=URLConnection.getInputStream(post) if code==200 else HttpURLConnection.getErrorStream(post)
 result=json.loads(str(IOUtils.toString(stream,'UTF-8')))
 assert code==200,result
 assert result['saved'] and result['feeder']['bus_id']==8
 assert len(machine.drivers)==1 and len(machine.actuators)==2
finally:server.stop()
assert strip.getLocation().getX()==0 and feeder.getLocation()==original_location
print('Powered-feeder checks passed: part/driver creation, duplicate rejection, strip isolation, job exclusion, forbidden actions and real JSR-223 HTTP/reload lifecycle.')
