#!/usr/bin/env python
# vim: et ai ts=4 sw=4:

import ast
import os
import sys
from multiprocessing import cpu_count
import shlex
import shutil
import glob
import subprocess

from charmhelpers.core import hookenv
from charmhelpers.core import host
from charmhelpers import fetch

hooks = hookenv.Hooks()


CHARM_PACKAGES = ["gunicorn", "python-jinja2"]
GUNICORN_INITD_SCRIPT = "/etc/init.d/gunicorn"
GUNICORN_INITD_SCRIPT_DISABLED = "/etc/init.d/gunicorn.disabled"

###############################################################################
# Supporting functions
###############################################################################


def sanitize(s):  # pragma: no cover
    s = s.replace(':', '_')
    s = s.replace('-', '_')
    s = s.replace('/', '_')
    s = s.replace('"', '_')
    s = s.replace("'", '_')
    return s


def sanitized_service_name():  # pragma: no cover
    return sanitize(hookenv.local_unit().split('/')[0])


def process_template(template_name, template_vars, destination):
    # deferred import so install hook can run to install jinja2
    from jinja2 import Environment, FileSystemLoader
    path = os.path.join(os.environ['CHARM_DIR'], 'templates')
    template_env = Environment(loader=FileSystemLoader(path))

    template = \
        template_env.get_template(template_name).render(template_vars)

    with open(destination, 'w') as inject_file:
        inject_file.write(str(template))


def ensure_packages():
    fetch.apt_update()
    fetch.apt_install(CHARM_PACKAGES)


def remove_old_services():
    """Clean up older charm config if we are upgrading to new python based charm"""

    if not os.path.exists(GUNICORN_INITD_SCRIPT_DISABLED):
        # ensure the sysv service is disabled
        subprocess.call(["update-rc.d", "-f", "gunicorn", "disable"])

        # ensure the sysv init is stopped
        subprocess.call([GUNICORN_INITD_SCRIPT, 'stop'])

        # ensure any old charm config removed. 
        for conf in glob.glob('/etc/gunicorn.d/*.conf'):
            try:
                hookenv.log('removing old guncorn config: %s' % conf)
                os.remove(conf)
            except:  # pragma: no cover
                pass

        # rename /etc/init.d/gunicorn 
        if os.path.exists("/etc/init.d/gunicorn"):
            shutil.move(GUNICORN_INITD_SCRIPT, GUNICORN_INITD_SCRIPT_DISABLED)


def write_initd_proxy():
    """Some charms/packages may use hardcoded path of /etc/init.d/gunicorn, so 
    add a wrapper there that proxies to the upstart job."""
    with open(GUNICORN_INITD_SCRIPT, 'w') as initd:
        initd.write("#!/bin/sh\nservice gunicorn $*\n")
    os.chmod(GUNICORN_INITD_SCRIPT, 0755)


###############################################################################
# Hook functions
###############################################################################


@hooks.hook('install')
def install():
    ensure_packages()
    write_initd_proxy()


@hooks.hook('upgrade-charm')
def upgrade():
    ensure_packages()
    remove_old_services()  # TODO: remove later
    write_initd_proxy()


@hooks.hook(
    "config-changed",
    "wsgi-file-relation-joined",
    "wsgi-file-relation-changed")
def configure_gunicorn():
    wsgi_config = hookenv.config()

    relations = hookenv.relations_of_type('wsgi-file')
    if not relations:
        hookenv.log("No wsgi-file relation, nothing to do")
        return

    relation_data = relations[0]

    service_name = sanitized_service_name()
    wsgi_config['unit_name'] = service_name

    project_conf = "/etc/init/gunicorn.conf"

    working_dir = relation_data.get('working_dir', None)
    if not working_dir:
        return

    wsgi_config['working_dir'] = working_dir
    wsgi_config['project_name'] = service_name

    # any valid config item can be overidden by a relation item
    for key, relation_value in relation_data.items():
        if key in wsgi_config:
            wsgi_config[key] = relation_value

    if wsgi_config['wsgi_worker_class'] == 'eventlet':
        fetch.apt_install('python-eventlet')
    elif wsgi_config['wsgi_worker_class'] == 'gevent':
        fetch.apt_install('python-gevent')
    elif wsgi_config['wsgi_worker_class'] == 'tornado':
        fetch.apt_install('python-tornado')

    if str(wsgi_config['wsgi_workers']) == '0':
        wsgi_config['wsgi_workers'] = cpu_count() + 1

    env_extra = wsgi_config.get('env_extra', '')

    # support old python dict format for env_extra for upgrade path
    extra = []
    # attempt dict parsing
    try:
        dict_str = '{' + env_extra + '}'
        extra = [[k, str(v)] for k, v in ast.literal_eval(dict_str).items()]
    except (SyntaxError, ValueError):
        pass

    if not extra:
        extra = [
            v.split('=', 1) for v in shlex.split(env_extra) if '=' in v
        ]

    wsgi_config['env_extra'] = extra


    # support old python list format for wsgi_extra
    # it will be a partial tuple of strings
    # e.g. wsgi_extra = "'foo', 'bar',"

    wsgi_extra = wsgi_config.get('wsgi_extra', '')
    # attempt tuple parsing
    try:
        tuple_str = '(' + wsgi_extra + ')'
        wsgi_extra = " ".join(ast.literal_eval(tuple_str))
    except (SyntaxError, ValueError):
        pass

    wsgi_config['wsgi_extra'] = wsgi_extra

    process_template('upstart.tmpl', wsgi_config, project_conf)
    hookenv.log('written gunicorn upstart config to %s' % project_conf)

    # We need this because when the contained charm configuration or code
    # changed Gunicorn needs to restart to run the new code.
    host.service_restart("gunicorn")


@hooks.hook("wsgi_file_relation_broken")
def wsgi_file_relation_broken():
    host.service_stop("gunicorn")
    try:
        os.remove("/etc/init/gunicorn.conf")
    except OSError as exc:  # pragma: no cover
        if exc.errno != 2:
            raise
    hookenv.log("removed gunicorn upstart config")


if __name__ == "__main__":  # pragma: no cover
    hooks.execute(sys.argv)
