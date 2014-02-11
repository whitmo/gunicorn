#!/usr/bin/env python
# vim: et ai ts=4 sw=4:

import os
import sys
from multiprocessing import cpu_count

from charmhelpers.core import hookenv
from charmhelpers.core import host
from charmhelpers import fetch

hooks = hookenv.Hooks()


CHARM_PACKAGES = ["gunicorn", "python-jinja2"]

###############################################################################
# Supporting functions
###############################################################################


def sanitize(s):
    s = s.replace(':', '_')
    s = s.replace('-', '_')
    s = s.replace('/', '_')
    s = s.replace('"', '_')
    s = s.replace("'", '_')
    return s


def sanitized_service_name():
    return sanitize(hookenv.remote_unit().split('/')[0])


def upstart_conf_path(name):
    return '/etc/init/%s.conf' % name


def process_template(template_name, template_vars, destination):
    # deferred import so install hook can run to install jinja2
    from jinja2 import Environment, FileSystemLoader
    path = os.path.join(os.environ['CHARM_DIR'], 'templates')
    template_env = Environment(loader=FileSystemLoader(path))

    template = \
        template_env.get_template(template_name).render(template_vars)

    with open(destination, 'w') as inject_file:
        inject_file.write(str(template))
    hookenv.log('written gunicorn upstart config to %s' % destination)


###############################################################################
# Hook functions
###############################################################################


@hooks.hook('install', 'upgrade-charm')
def install():
    fetch.apt_update()
    fetch.apt_install(CHARM_PACKAGES)


@hooks.hook("wsgi-file-relation-joined", "wsgi-file-relation-changed")
def configure_gunicorn():
    wsgi_config = hookenv.config()

    service_name = sanitized_service_name()
    wsgi_config['unit_name'] = service_name

    project_conf = upstart_conf_path(service_name)

    working_dir = hookenv.relation_get('working_dir')
    if not working_dir:
        return

    wsgi_config['working_dir'] = working_dir
    wsgi_config['project_name'] = service_name

    # any valid config item can be overidden by a relation item
    relation_data = hookenv.relation_get()
    for key, relation_value in relation_data.items():
        if key in wsgi_config:
            wsgi_config[key] = relation_value

    if wsgi_config['wsgi_worker_class'] == 'eventlet':
        fetch.apt_install('python-eventlet')
    elif wsgi_config['wsgi_worker_class'] == 'gevent':
        fetch.apt_install('python-gevent')
    elif wsgi_config['wsgi_worker_class'] == 'tornado':
        fetch.apt_install('python-tornado')

    if wsgi_config['wsgi_workers'] == 0:
        wsgi_config['wsgi_workers'] = cpu_count() + 1

    # only specify access log details if the access configs are set
    if wsgi_config['wsgi_access_logfile']:
        wsgi_config['wsgi_extra'] = " ".join([
            wsgi_config['wsgi_extra'],
            '--access-logfile=%s' % wsgi_config['wsgi_access_logfile'],
            '--access-logformat="%s"' % wsgi_config['wsgi_access_logformat']
        ])

    process_template('upstart.tmpl', wsgi_config, project_conf)

    # We need this because when the contained charm configuration or code
    # changed Gunicorn needs to restart to run the new code.
    host.service_reload(service_name, restart_on_failure=True)


@hooks.hook("wsgi_file_relation_broken")
def wsgi_file_relation_broken():
    service_name = sanitized_service_name()
    host.service_stop(service_name)
    try:
        os.remove(upstart_conf_path(service_name))
    except OSError as exc:
        if exc.errno != 2:
            raise
    hookenv.log("removed gunicorn upstart config")


if __name__ == "__main__":
    hooks.execute(sys.argv)
