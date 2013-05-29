#!/usr/bin/env python
# vim: et ai ts=4 sw=4:

import json
import os
import re
import subprocess
import sys
import time
from pwd import getpwnam
from grp import getgrnam

CHARM_PACKAGES = ["gunicorn"]

INJECTED_WARNING = """
#------------------------------------------------------------------------------
# The following is the import code for the settings directory injected by Juju
#------------------------------------------------------------------------------
"""


###############################################################################
# Supporting functions
###############################################################################
MSG_CRITICAL = "CRITICAL"
MSG_DEBUG = "DEBUG"
MSG_INFO = "INFO"
MSG_ERROR = "ERROR"
MSG_WARNING = "WARNING"


def juju_log(level, msg):
    subprocess.call(['juju-log', '-l', level, msg])

#------------------------------------------------------------------------------
# run: Run a command, return the output
#------------------------------------------------------------------------------
def run(command, exit_on_error=True, cwd=None):
    try:
        juju_log(MSG_DEBUG, command)
        return subprocess.check_output(
            command, stderr=subprocess.STDOUT, shell=True, cwd=cwd)
    except subprocess.CalledProcessError, e:
        juju_log(MSG_ERROR, "status=%d, output=%s" % (e.returncode, e.output))
        if exit_on_error:
            sys.exit(e.returncode)
        else:
            raise


#------------------------------------------------------------------------------
# install_file: install a file resource. overwites existing files.
#------------------------------------------------------------------------------
def install_file(contents, dest, owner="root", group="root", mode=0600):
    uid = getpwnam(owner)[2]
    gid = getgrnam(group)[2]
    dest_fd = os.open(dest, os.O_WRONLY | os.O_TRUNC | os.O_CREAT, mode)
    os.fchown(dest_fd, uid, gid)
    with os.fdopen(dest_fd, 'w') as destfile:
        destfile.write(str(contents))


#------------------------------------------------------------------------------
# install_dir: create a directory
#------------------------------------------------------------------------------
def install_dir(dirname, owner="root", group="root", mode=0700):
    command = \
    '/usr/bin/install -o {} -g {} -m {} -d {}'.format(owner, group, oct(mode),
        dirname)
    return run(command)

#------------------------------------------------------------------------------
# config_get:  Returns a dictionary containing all of the config information
#              Optional parameter: scope
#              scope: limits the scope of the returned configuration to the
#                     desired config item.
#------------------------------------------------------------------------------
def config_get(scope=None):
    try:
        config_cmd_line = ['config-get']
        if scope is not None:
            config_cmd_line.append(scope)
        config_cmd_line.append('--format=json')
        config_data = json.loads(subprocess.check_output(config_cmd_line))
    except:
        config_data = None
    finally:
        return(config_data)


#------------------------------------------------------------------------------
# relation_json:  Returns json-formatted relation data
#                Optional parameters: scope, relation_id
#                scope:        limits the scope of the returned data to the
#                              desired item.
#                unit_name:    limits the data ( and optionally the scope )
#                              to the specified unit
#                relation_id:  specify relation id for out of context usage.
#------------------------------------------------------------------------------
def relation_json(scope=None, unit_name=None, relation_id=None):
    command = ['relation-get', '--format=json']
    if relation_id is not None:
        command.extend(('-r', relation_id))
    if scope is not None:
        command.append(scope)
    else:
        command.append('-')
    if unit_name is not None:
        command.append(unit_name)
    output = subprocess.check_output(command, stderr=subprocess.STDOUT)
    return output or None


#------------------------------------------------------------------------------
# relation_get:  Returns a dictionary containing the relation information
#                Optional parameters: scope, relation_id
#                scope:        limits the scope of the returned data to the
#                              desired item.
#                unit_name:    limits the data ( and optionally the scope )
#                              to the specified unit
#------------------------------------------------------------------------------
def relation_get(scope=None, unit_name=None, relation_id=None):
    j = relation_json(scope, unit_name, relation_id)
    if j:
        return json.loads(j)
    else:
        return None


def relation_set(keyvalues, relation_id=None):
    args = []
    if relation_id:
        args.extend(['-r', relation_id])
    args.extend(["{}='{}'".format(k, v or '') for k, v in keyvalues.items()])
    run("relation-set {}".format(' '.join(args)))

    ## Posting json to relation-set doesn't seem to work as documented?
    ## Bug #1116179
    ##
    ## cmd = ['relation-set']
    ## if relation_id:
    ##     cmd.extend(['-r', relation_id])
    ## p = Popen(
    ##     cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
    ##     stderr=subprocess.PIPE)
    ## (out, err) = p.communicate(json.dumps(keyvalues))
    ## if p.returncode:
    ##     juju_log(MSG_ERROR, err)
    ##     sys.exit(1)
    ## juju_log(MSG_DEBUG, "relation-set {}".format(repr(keyvalues)))


def relation_list(relation_id=None):
    """Return the list of units participating in the relation."""
    if relation_id is None:
        relation_id = os.environ['JUJU_RELATION_ID']
    cmd = ['relation-list', '--format=json', '-r', relation_id]
    json_units = subprocess.check_output(cmd).strip()
    if json_units:
        return json.loads(subprocess.check_output(cmd))
    return []


#------------------------------------------------------------------------------
# relation_ids:  Returns a list of relation ids
#                optional parameters: relation_type
#                relation_type: return relations only of this type
#------------------------------------------------------------------------------
def relation_ids(relation_types=('db',)):
    # accept strings or iterators
    if isinstance(relation_types, basestring):
        reltypes = [relation_types, ]
    else:
        reltypes = relation_types
    relids = []
    for reltype in reltypes:
        relid_cmd_line = ['relation-ids', '--format=json', reltype]
        json_relids = subprocess.check_output(relid_cmd_line).strip()
        if json_relids:
            relids.extend(json.loads(json_relids))
    return relids


#------------------------------------------------------------------------------
# relation_get_all:  Returns a dictionary containing the relation information
#                optional parameters: relation_type
#                relation_type: limits the scope of the returned data to the
#                               desired item.
#------------------------------------------------------------------------------
def relation_get_all(*args, **kwargs):
    relation_data = []
    relids = relation_ids(*args, **kwargs)
    for relid in relids:
        units_cmd_line = ['relation-list', '--format=json', '-r', relid]
        json_units = subprocess.check_output(units_cmd_line).strip()
        if json_units:
            for unit in json.loads(json_units):
                unit_data = \
                    json.loads(relation_json(relation_id=relid,
                        unit_name=unit))
                for key in unit_data:
                    if key.endswith('-list'):
                        unit_data[key] = unit_data[key].split()
                unit_data['relation-id'] = relid
                unit_data['unit'] = unit
                relation_data.append(unit_data)
    return relation_data

def apt_get_update():
    cmd_line = ['apt-get', 'update']
    return(subprocess.call(cmd_line))


#------------------------------------------------------------------------------
# apt_get_install( packages ):  Installs package(s)
#------------------------------------------------------------------------------
def apt_get_install(packages=None):
    if packages is None:
        return(False)
    cmd_line = ['apt-get', '-y', 'install', '-qq']
    if isinstance(packages, list):
        cmd_line.extend(packages)
    else:
        cmd_line.append(packages)
    return(subprocess.call(cmd_line))


#------------------------------------------------------------------------------
# pip_install( package ):  Installs a python package
#------------------------------------------------------------------------------
def pip_install(packages=None, upgrade=False):
    cmd_line = ['pip', 'install']
    if packages is None:
        return(False)
    if upgrade:
        cmd_line.append('-u')
    if packages.startswith('svn+') or packages.startswith('git+') or \
       packages.startswith('hg+') or packages.startswith('bzr+'):
        cmd_line.append('-e')
    cmd_line.append(packages)
    return run(cmd_line)

#------------------------------------------------------------------------------
# pip_install_req( path ):  Installs a requirements file
#------------------------------------------------------------------------------
def pip_install_req(path=None, upgrade=False):
    cmd_line = ['pip', 'install']
    if path is None:
        return(False)
    if upgrade:
        cmd_line.append('-u')
    cmd_line.append('-r')
    cmd_line.append(path)
    cwd = os.path.dirname(path)
    return run(cmd_line)

#------------------------------------------------------------------------------
# open_port:  Convenience function to open a port in juju to
#             expose a service
#------------------------------------------------------------------------------
def open_port(port=None, protocol="TCP"):
    if port is None:
        return(None)
    return(subprocess.call(['open-port', "%d/%s" %
        (int(port), protocol)]))


#------------------------------------------------------------------------------
# close_port:  Convenience function to close a port in juju to
#              unexpose a service
#------------------------------------------------------------------------------
def close_port(port=None, protocol="TCP"):
    if port is None:
        return(None)
    return(subprocess.call(['close-port', "%d/%s" %
        (int(port), protocol)]))


#------------------------------------------------------------------------------
# update_service_ports:  Convenience function that evaluate the old and new
#                        service ports to decide which ports need to be
#                        opened and which to close
#------------------------------------------------------------------------------
def update_service_port(old_service_port=None, new_service_port=None):
    if old_service_port is None or new_service_port is None:
        return(None)
    if new_service_port != old_service_port:
        close_port(old_service_port)
        open_port(new_service_port)

#
# Utils
#

def install_or_append(contents, dest, owner="root", group="root", mode=0600):
    if os.path.exists(dest):
        uid = getpwnam(owner)[2]
        gid = getgrnam(group)[2]
        dest_fd = os.open(dest, os.O_APPEND, mode)
        os.fchown(dest_fd, uid, gid)
        with os.fdopen(dest_fd, 'a') as destfile:
            destfile.write(str(contents))
    else:
        install_file(contents, dest, owner, group, mode)

def token_sql_safe(value):
    # Only allow alphanumeric + underscore in database identifiers
    if re.search('[^A-Za-z0-9_]', value):
        return False
    return True

def sanitize(s):
    s = s.replace(':', '_')
    s = s.replace('-', '_')
    s = s.replace('/', '_')
    s = s.replace('"', '_')
    s = s.replace("'", '_')
    return s

def user_name(relid, remote_unit, admin=False, schema=False):
    components = [sanitize(relid), sanitize(remote_unit)]
    if admin:
        components.append("admin")
    elif schema:
        components.append("schema")
    return "_".join(components)

def get_relation_host():
    remote_host = run("relation-get ip")
    if not remote_host:
        # remote unit $JUJU_REMOTE_UNIT uses deprecated 'ip=' component of
        # interface.
        remote_host = run("relation-get private-address")
    return remote_host


def get_unit_host():
    this_host = run("unit-get private-address")
    return this_host.strip()

def process_template(template_name, template_vars, destination):
    # --- exported service configuration file
    from jinja2 import Environment, FileSystemLoader
    template_env = Environment(
        loader=FileSystemLoader(os.path.join(os.environ['CHARM_DIR'],
        'templates')))

    template = \
        template_env.get_template(template_name).render(template_vars)

    with open(destination, 'w') as inject_file:
        inject_file.write(str(template))

def append_template(template_name, template_vars, path, try_append=False):

    # --- exported service configuration file
    from jinja2 import Environment, FileSystemLoader
    template_env = Environment(
        loader=FileSystemLoader(os.path.join(os.environ['CHARM_DIR'],
        'templates')))

    template = \
        template_env.get_template(template_name).render(template_vars)

    append = False
    if os.path.exists(path):
        with open(path, 'r') as inject_file:
            if not str(template) in inject_file:
                append = True
    else:       
        append = True
        
    if append == True:
        with open(path, 'a') as inject_file:
            inject_file.write(INJECTED_WARNING)
            inject_file.write(str(template))



###############################################################################
# Hook functions
###############################################################################
def install():

    for retry in xrange(0,24):
        if apt_get_install(CHARM_PACKAGES):
            time.sleep(10)
        else:
            break

def upgrade():

    apt_get_update()
    for retry in xrange(0,24):
        if apt_get_install(CHARM_PACKAGES):
            time.sleep(10)
        else:
            break

def wsgi_file_relation_joined_changed():
    wsgi_config = config_data
    relation_id = os.environ['JUJU_RELATION_ID']
    juju_log(MSG_INFO, "JUJU_RELATION_ID: %s".format(relation_id))

    remote_unit_name = sanitize(os.environ['JUJU_REMOTE_UNIT'].split('/')[0])
    juju_log(MSG_INFO, "JUJU_REMOTE_UNIT: %s".format(remote_unit_name))
    wsgi_config['unit_name'] = remote_unit_name

    project_conf = '/etc/init/%s.conf' % remote_unit_name

    working_dir = relation_get('working_dir')
    if not working_dir:
        return

    wsgi_config['working_dir'] = working_dir
    wsgi_config['project_name'] = remote_unit_name

    for v in wsgi_config.keys():
        if v.startswith('wsgi_') or v in ['python_path', 'listen_ip', 'port']:
            upstream_value = relation_get(v)
            if upstream_value:
                wsgi_config[v] = upstream_value

    if wsgi_config['wsgi_worker_class'] == 'eventlet':
        apt_get_install('python-eventlet')
    elif  wsgi_config['wsgi_worker_class'] == 'gevent':
        apt_get_install('python-gevent')
    elif wsgi_config['wsgi_worker_class'] == 'tornado':
        apt_get_install('python-tornado')

    if wsgi_config['wsgi_workers'] == 0:
        res = run('python -c "import multiprocessing ; print(multiprocessing.cpu_count())"')
        wsgi_config['wsgi_workers'] = int(res) + 1

    if wsgi_config['wsgi_access_logfile']:
        wsgi_config['wsgi_extra'] = " ".join([
            wsgi_config['wsgi_extra'],
            '--access-logformat=%s' % wsgi_config['wsgi_access_logfile'],
            '--access-logformat="%s"' % wsgi_config['wsgi_access_logformat']
            ])

    wsgi_config['wsgi_wsgi_file'] = wsgi_config['wsgi_wsgi_file']

    process_template('upstart.tmpl', wsgi_config, project_conf)


    # We need this because when the contained charm configuration or code changed
    # Gunicorn needs to restart to run the new code.
    run("service %s restart || service %s start" % (remote_unit_name, remote_unit_name))

    open_port(config_data['port'])


def wsgi_file_relation_broken():
    remote_unit_name = sanitize(os.environ['JUJU_REMOTE_UNIT'].split('/')[0])

    run('service %s stop' % remote_unit_name)
    run('rm /etc/init/%s.conf' % remote_unit_name)

    close_port(config_data['port'])


###############################################################################
# Global variables
###############################################################################
config_data = config_get()
juju_log(MSG_DEBUG, "got config: %s" % str(config_data))

unit_name = os.environ['JUJU_UNIT_NAME'].split('/')[0]

hook_name = os.path.basename(sys.argv[0])

###############################################################################
# Main section
###############################################################################
def main():
    juju_log(MSG_INFO, "Running {} hook".format(hook_name))
    if hook_name == "install":
        install()

    elif hook_name == "upgrade-charm":
        upgrade()

    elif hook_name in ["wsgi-file-relation-joined", "wsgi-file-relation-changed"]:
        wsgi_file_relation_joined_changed()

    elif hook_name == "wsgi-file-relation-broken":
        wsgi_file_relation_broken()

    else:
        print "Unknown hook {}".format(hook_name)
        raise SystemExit(1)

if __name__ == '__main__':
    raise SystemExit(main())
