# Keep callbacks independent of OpenPnP resetting its shared script bindings.
def _microsmt_load():
    # Powered-feeder creation and part assignment only. Motion, cameras and pickup teaching stay in OpenPnP.
    # MicroSMT original designs retain credit. Local integration by Gab.
    import json
    from contextlib import contextmanager
    import math
    import re
    from java.io import OutputStream, StringWriter, StringReader
    from java.util.concurrent import Executors
    from java.lang import Class, Runnable, String, System, Exception as JavaException
    from java.net import InetSocketAddress
    from java.util.concurrent.locks import ReentrantLock
    from javax.swing import SwingUtilities
    from com.sun.net.httpserver import HttpServer, HttpHandler, HttpExchange, Headers
    from org.apache.commons.io import IOUtils
    from org.openpnp.model import Length, LengthUnit, Part, Package, Configuration
    from org.openpnp.spi import Actuator
    from org.openpnp.machine.reference import ReferenceActuator
    from org.openpnp.machine.reference.feeder import ReferenceAutoFeeder
    from org.openpnp.machine.reference.driver import GcodeDriver, AbstractReferenceDriver



    def finite(value, low, high, label):
        if isinstance(value, bool):
            raise ValueError(label + ' must be a number')
        value = float(value)
        if math.isnan(value) or math.isinf(value) or not low <= value <= high:
            raise ValueError(label + ' must be between ' + str(low) + ' and ' + str(high))
        return value


    def integer(value, low, high, label):
        number = finite(value, low, high, label)
        if number != int(number): raise ValueError(label + ' must be a whole number')
        return int(number)


    class UI(Runnable):
        def __init__(self, function): self.function, self.value, self.error = function, None, None
        def run(self):
            try: self.value = self.function()
            except (Exception, JavaException) as error: self.error = error


    def on_ui(function):
        if SwingUtilities.isEventDispatchThread(): return function()
        task = UI(function)
        SwingUtilities.invokeAndWait(task)
        if task.error is not None: raise task.error
        return task.value


    class WebControl(object):
        def __init__(self, config, machine, gui):
            self.config, self.machine, self.gui = config, machine, gui
            self.operation = ReentrantLock()
            self.last_error = ''

        @contextmanager
        def saving(self, undo):
            try:
                yield
                self.config.save()
            except (Exception,JavaException) as error:
                try:
                    undo()
                    self.config.save()
                except (Exception,JavaException):
                    raise ValueError('Save failed; rollback needs checking: '+str(error))
                raise

        def job_state(self):
            # OpenPnP 2.6 exposes actions but no public JobPanel state getter.
            panel = self.gui.getJobTab()
            field = panel.getClass().getDeclaredField('state')
            field.setAccessible(True)
            return str(field.get(panel))

        def idle(self):
            if self.job_state() != 'Stopped': raise ValueError('Stop the OpenPnP job before changing feeder configuration')
            if self.machine.isBusy(): raise ValueError('OpenPnP is busy; command was not queued')

        def powered_feeders(self):
            # Only expose feeders wired to this integration's own driver.
            result = []
            for feeder in self.machine.getFeeders():
                if not isinstance(feeder, ReferenceAutoFeeder): continue
                actuator = self.machine.getActuatorByName(feeder.getActuatorName())
                if actuator is not None and actuator.getDriver() is not None and str(actuator.getDriver().getName()) == 'MicroSMT feeders':
                    result.append(feeder)
            return result

        def describe(self, feeder):
            part = feeder.getPart()
            return dict(id=str(feeder.getId()), name=str(feeder.getName()),
                        bus_id=feeder.getActuatorValue(), part_id=str(part.getId()) if part else '')

        def describe_part(self, part):
            package=part.getPackage()
            height=part.getHeight()
            return dict(id=str(part.getId()),name=unicode(part.getName() or ''),
                        package_id=str(package.getId()) if package else '',
                        height_mm=float(height.convertToUnits(LengthUnit.Millimeters).getValue()) if height else 0)

        def describe_package(self, package):
            footprint=package.getFootprint()
            units=(footprint.getUnits() or LengthUnit.Millimeters) if footprint else LengthUnit.Millimeters
            def mm(value):return float(Length(value,units).convertToUnits(LengthUnit.Millimeters).getValue())
            return dict(id=str(package.getId()),description=unicode(package.getDescription() or ''),
                        pad_count=len(footprint.getPads()) if footprint else 0,
                        body_width_mm=mm(footprint.getBodyWidth()) if footprint else 0,
                        body_length_mm=mm(footprint.getBodyHeight()) if footprint else 0,
                        pads=[dict(name=unicode(p.getName() or ''),x=mm(p.getX()),y=mm(p.getY()),
                                   width=mm(p.getWidth()),height=mm(p.getHeight()),rotation=float(p.getRotation()),
                                   roundness=float(p.getRoundness()),mark=bool(p.getMark())) for p in footprint.getPads()] if footprint else [],
                        nozzle_tip_ids=sorted(str(t.getId()) for t in package.getCompatibleNozzleTips()))

        def describe_nozzles(self):
            result=[]
            for head in self.machine.getHeads():
                for nozzle in head.getNozzles():
                    loaded=nozzle.getNozzleTip()
                    result.append(dict(id=str(nozzle.getId()),name=unicode(nozzle.getName() or nozzle.getId()),
                                       head_id=str(head.getId()),head_name=unicode(head.getName() or head.getId()),
                                       nozzle_tip_ids=sorted(str(t.getId()) for t in nozzle.getCompatibleNozzleTips()),
                                       loaded_tip_id=str(loaded.getId()) if loaded else ''))
            return result

        def job_requirements(self):
            # Read-only view of the current job; execution stays in OpenPnP.
            job=self.gui.getJobTab().getJob()
            if job is None:return dict(name='',boards=0,total=0,remaining=0,parts=[],feeders=[],state=self.job_state())
            counts={};boards=0
            for board in job.getBoardLocations():
                branch=board;enabled=True
                while branch is not None:
                    if not branch.isEnabled() or not job.retrieveEnabledState(branch,None):enabled=False;break
                    branch=branch.getParent()
                if not enabled or board.getBoard() is None:continue
                boards+=1
                for placement in board.getBoard().getPlacements():
                    if str(placement.getType())!='Placement' or placement.getSide()!=board.getGlobalSide() or not job.retrieveEnabledState(board,placement):continue
                    part=placement.getPart();identifier=str(part.getId()) if part else ''
                    entry=counts.setdefault(identifier,dict(part_id=identifier,name=unicode(part.getName() or '') if part else 'Missing part',total=0,remaining=0))
                    entry['total']+=1
                    if not job.retrievePlacedStatus(board,placement.getId()):entry['remaining']+=1
            powered=set(str(f.getId()) for f in self.powered_feeders())
            feeders=[]
            for feeder in self.machine.getFeeders():
                part=feeder.getPart()
                feeders.append(dict(id=str(feeder.getId()),name=unicode(feeder.getName() or feeder.getId()),part_id=str(part.getId()) if part else '',enabled=bool(feeder.isEnabled()),powered=str(feeder.getId()) in powered,bus_id=feeder.getActuatorValue() if str(feeder.getId()) in powered else None))
            return dict(name=unicode(job.getFile().getName()) if job.getFile() else 'Unsaved job',boards=boards,
                        total=sum(p['total'] for p in counts.values()),remaining=sum(p['remaining'] for p in counts.values()),
                        parts=sorted(counts.values(),key=lambda p:p['part_id']),feeders=feeders,state=self.job_state())

        def snapshot(self):
            return dict(online=True, enabled=bool(self.machine.isEnabled()),api_version=1,
                        nozzles=self.describe_nozzles(),
                        nozzle_tips=[dict(id=str(t.getId()),name=unicode(t.getName() or t.getId())) for t in self.machine.getNozzleTips()],
                        error=self.last_error,
                        feeders=[self.describe(f) for f in self.powered_feeders()],
                        parts=[self.describe_part(p) for p in self.config.getParts()],
                        packages=[self.describe_package(p) for p in self.config.getPackages()])

        def add_feeder(self, args):
            self.idle()
            if self.machine.isEnabled(): raise ValueError('Disable OpenPnP before adding a feeder driver')
            bus = integer(args.get('bus_id'),1,99,'Bus ID')
            name = str(args.get('name','')).strip()
            if not name or len(name)>128: raise ValueError('Enter a feeder name')
            if any(float(f.getActuatorValue()) == bus for f in self.powered_feeders()):
                raise ValueError('This bus ID is already in OpenPnP')
            part_id = args.get('part_id', '')
            part = self.config.getPart(part_id) if part_id else None
            if part_id and part is None: raise ValueError('Unknown OpenPnP part')
            driver = next((d for d in self.machine.getDrivers() if str(d.getName())=='MicroSMT feeders'),None)
            if driver is not None and (str(Class.getName(driver.getClass())) != 'org.openpnp.machine.reference.driver.GcodeDriver' or str(driver.getCommunicationsType()) != 'tcp' or driver.getTcp().getIpAddress() != '127.0.0.1' or driver.getTcp().getPort() != 5001):
                raise ValueError('Existing MicroSMT feeders driver has unexpected settings; inspect it in OpenPnP')
            added_driver = driver is None
            if driver is None:
                driver = GcodeDriver()
                driver.setName('MicroSMT feeders')
                driver.setCommunicationsType(AbstractReferenceDriver.CommunicationsType.tcp)
                driver.getTcp().setIpAddress('127.0.0.1')
                driver.getTcp().setPort(5001)
                driver.setTimeoutMilliseconds(20000)
                driver.setConnectWaitTimeMilliseconds(0)
                driver.setCommand(None,GcodeDriver.CommandType.COMMAND_CONFIRM_REGEX,r'^ok(?:\s.*)?$')
                driver.setCommand(None,GcodeDriver.CommandType.COMMAND_ERROR_REGEX,r'(?i)^error:.*$')
            actuator = ReferenceActuator()
            actuator.setName('MicroSMT feeder '+str(bus)+' '+str(actuator.getId()))
            actuator.setDriver(driver)
            actuator.setValueType(Actuator.ActuatorValueType.Double)
            driver.setCommand(actuator,GcodeDriver.CommandType.ACTUATE_DOUBLE_COMMAND,'M600 N{IntegerValue} F0')
            feeder = ReferenceAutoFeeder()
            feeder.setName(name)
            feeder.setEnabled(False)
            feeder.setPart(part)
            feeder.setActuatorName(actuator.getName())
            feeder.setActuatorValue(bus)
            def undo():
                self.machine.removeFeeder(feeder)
                self.machine.removeActuator(actuator)
                if added_driver:self.machine.removeDriver(driver)
            with self.saving(undo):
                if added_driver:self.machine.addDriver(driver)
                self.machine.addActuator(actuator)
                self.machine.addFeeder(feeder)
            self.gui.getFeedersTab().refresh(feeder)
            return dict(saved=True, feeder=self.describe(feeder))

        def set_feeder_part(self, args):
            self.idle()
            bus=integer(args.get('bus_id'),1,99,'Bus ID')
            matches=[f for f in self.powered_feeders() if float(f.getActuatorValue())==bus]
            if len(matches)!=1:raise ValueError('Expected exactly one powered feeder for this bus ID')
            feeder=matches[0]
            if str(feeder.getId())!=args.get('feeder_id'):raise ValueError('Matching OpenPnP feeder changed; refresh before saving')
            part_id=args.get('part_id','')
            part=self.config.getPart(part_id) if part_id else None
            if part_id and part is None:raise ValueError('Unknown OpenPnP part')
            before=feeder.getPart()
            with self.saving(lambda: feeder.setPart(before)):
                feeder.setPart(part)
            self.gui.getFeedersTab().refresh(feeder)
            return dict(saved=True,feeder=self.describe(feeder))

        def edit_part(self, args):
            self.idle()
            part=self.config.getPart(args.get('part_id',''))
            if part is None:raise ValueError('Unknown OpenPnP part')
            if args.get('expected')!=self.describe_part(part):raise ValueError('Part changed in OpenPnP; reopen the editor before saving')
            name=args.get('name','')
            if not isinstance(name,basestring) or len(name)>256:raise ValueError('Part name must be at most 256 characters')
            package_id=args.get('package_id','')
            package=self.config.getPackage(package_id) if package_id else None
            if package_id and package is None:raise ValueError('Unknown OpenPnP package')
            height=finite(args.get('height_mm'),0,1000,'Height in mm')
            before=(part.getName(),part.getPackage(),part.getHeight())
            def undo():
                part.setName(before[0])
                part.setPackage(before[1])
                part.setHeight(before[2])
            with self.saving(undo):
                part.setName(name)
                part.setPackage(package)
                part.setHeight(Length(height, LengthUnit.Millimeters))
            self.gui.getPartsTab().repaint()
            return dict(saved=True,part=self.describe_part(part))

        def edit_package(self, args):
            self.idle()
            package=self.config.getPackage(args.get('package_id',''))
            if package is None:raise ValueError('Unknown OpenPnP package')
            if args.get('expected')!=self.describe_package(package):raise ValueError('Package changed in OpenPnP; reopen the editor before saving')
            description=args.get('description','')
            if not isinstance(description,basestring) or len(description)>1024:raise ValueError('Description must be at most 1024 characters')
            identifiers=args.get('nozzle_tip_ids')
            if not isinstance(identifiers,list) or any(not isinstance(i,basestring) for i in identifiers) or len(set(identifiers))!=len(identifiers):
                raise ValueError('Select valid nozzle tips')
            tips={str(t.getId()):t for t in self.machine.getNozzleTips()}
            if any(i not in tips for i in identifiers):raise ValueError('A nozzle tip no longer exists; reopen the editor')
            before=(package.getDescription(),list(package.getCompatibleNozzleTips()))
            def assign(description, selected):
                package.setDescription(description)
                for tip in list(package.getCompatibleNozzleTips()):package.removeCompatibleNozzleTip(tip)
                for tip in selected:package.addCompatibleNozzleTip(tip)
            with self.saving(lambda: assign(*before)):
                assign(description, [tips[i] for i in identifiers])
            self.gui.getPackagesTab().repaint()
            return dict(saved=True,package=self.describe_package(package))

        def new_id(self, args, key):
            value=args.get(key,'')
            if not isinstance(value,basestring) or not value.strip() or len(value)>128 or any(ord(c)<32 for c in value):
                raise ValueError('Enter a non-empty ID of at most 128 characters')
            return value.strip()

        def create_part(self, args):
            self.idle()
            identifier=self.new_id(args,'part_id')
            if self.config.getPart(identifier) is not None:raise ValueError('Part ID already exists')
            name=args.get('name','')
            if not isinstance(name,basestring) or len(name)>256:raise ValueError('Part name must be at most 256 characters')
            package=self.config.getPackage(args.get('package_id',''))
            if package is None:raise ValueError('Select an existing package or create one first')
            height=finite(args.get('height_mm'),0,1000,'Height in mm')
            part=Part(identifier);part.setName(name);part.setPackage(package);part.setHeight(Length(height,LengthUnit.Millimeters))
            def undo():
                if self.config.getPart(identifier) == part:
                    self.config.removePart(part)
            with self.saving(undo):
                self.config.addPart(part)
            self.gui.getPartsTab().repaint()
            return dict(saved=True,part=self.describe_part(part))

        def create_package(self, args):
            self.idle()
            identifier=self.new_id(args,'package_id')
            if self.config.getPackage(identifier) is not None:raise ValueError('Package ID already exists')
            description=args.get('description','')
            if not isinstance(description,basestring) or len(description)>1024:raise ValueError('Description must be at most 1024 characters')
            copy_from=args.get('copy_from','')
            if copy_from:
                source=self.config.getPackage(copy_from)
                if source is None:raise ValueError('Source package no longer exists')
                serializer=Configuration.createSerializer();writer=StringWriter()
                serializer.write(source,writer)
                package=serializer.read(Package,StringReader(writer.toString()))
                package.setId(identifier)
            else:package=Package(identifier)
            package.setDescription(description)
            def undo():
                if self.config.getPackage(identifier) == package:
                    self.config.removePackage(package)
            with self.saving(undo):
                self.config.addPackage(package)
            self.gui.getPackagesTab().repaint()
            return dict(saved=True,package=self.describe_package(package))

        def action(self, args):
            actions={'add_feeder':self.add_feeder,'set_feeder_part':self.set_feeder_part,'edit_part':self.edit_part,'edit_package':self.edit_package,'create_part':self.create_part,'create_package':self.create_package}
            if args.get('action') not in actions:raise ValueError('Unsupported powered-feeder action')
            if not self.operation.tryLock(): raise ValueError('A feeder operation is already running')
            try: return on_ui(lambda:actions[args['action']](args))
            finally: self.operation.unlock()


    class Handler(HttpHandler):
        def __init__(self, control): self.control=control
        def handle(self, exchange):
            try:
                if str(HttpExchange.getRequestURI(exchange).getPath())=='/state' and str(HttpExchange.getRequestMethod(exchange))=='GET':
                    result=on_ui(self.control.snapshot)
                elif str(HttpExchange.getRequestURI(exchange).getPath())=='/job' and str(HttpExchange.getRequestMethod(exchange))=='GET':
                    result=on_ui(self.control.job_requirements)
                elif str(HttpExchange.getRequestURI(exchange).getPath())=='/action' and str(HttpExchange.getRequestMethod(exchange))=='POST':
                    length=Headers.getFirst(HttpExchange.getRequestHeaders(exchange),'Content-Length')
                    if length is None or int(length)>65536: raise ValueError('Invalid request size')
                    args=json.loads(str(IOUtils.toString(HttpExchange.getRequestBody(exchange),'UTF-8')))
                    result=self.control.action(args)
                    if result is None: result=dict(completed=True)
                    self.control.last_error=''
                else: raise ValueError('Unknown OpenPnP endpoint')
                code=200
            except (Exception, JavaException) as error:
                self.control.last_error=str(error)
                result,code=dict(error=str(error)),409
            data=String(json.dumps(result)).getBytes('UTF-8')
            Headers.set(HttpExchange.getResponseHeaders(exchange),'Content-Type','application/json')
            Headers.set(HttpExchange.getResponseHeaders(exchange),'Cache-Control','no-store')
            try:
                HttpExchange.sendResponseHeaders(exchange,code,len(data))
                OutputStream.write(HttpExchange.getResponseBody(exchange),data)
            finally: HttpExchange.close(exchange)


    class Companion(object):
        def __init__(self, control, port=5004):
            self.control=control
            self.server=HttpServer.create(InetSocketAddress('127.0.0.1',port),0)
            self.executor=Executors.newFixedThreadPool(3)
            HttpServer.setExecutor(self.server,self.executor)
            HttpServer.createContext(self.server,'/',Handler(control))
            HttpServer.start(self.server)
        def stop(self):
            HttpServer.stop(self.server,0)
            self.executor.shutdownNow()


    if 'machine' in globals() and 'gui' in globals():
        registry=System.getProperties()
        previous=registry.remove('microsmt.webControl')
        if previous is not None:
            # Repair imports for the previously installed shared-context version.
            previous.stop.im_func.func_globals['HttpServer']=HttpServer
            previous.stop()
        companion=Companion(WebControl(config,machine,gui))
        registry.put('microsmt.webControl',companion)
        print('MicroSMT OpenPnP web control ready')

    return locals()

_microsmt = _microsmt_load()
