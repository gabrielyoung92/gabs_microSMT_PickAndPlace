# PlatformIO post-build hook; packages the application, never uploads firmware.
# Original MicroSMT designs retain credit. Local integration by Gab.
from pathlib import Path
import subprocess
import sys
Import('env')


def package_dashboard(source, target, env):
    project = Path(env['PROJECT_DIR'])
    subprocess.check_call([sys.executable, str(project.parent / 'USB_host/bundle_firmware.py'),
                           '--image', env.subst('$BUILD_DIR/${PROGNAME}.bin')])


env.AddPostAction('buildprog', package_dashboard)

# Recreate the bundle even when the compiled application is already current.
env.AlwaysBuild('buildprog')
