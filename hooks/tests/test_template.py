import os
from unittest import TestCase
from mock import patch, MagicMock

import hooks

EXPECTED = """
#--------------------------------------------------------------
# This file is managed by Juju; ANY CHANGES WILL BE OVERWRITTEN
#--------------------------------------------------------------

description "Gunicorn daemon for the PROJECT_NAME project"

start on (local-filesystems and net-device-up IFACE=eth0)
stop on runlevel [!12345]

# If the process quits unexpectadly trigger a respawn
respawn

setuid WSGI_USER
setgid WSGI_GROUP
chdir WORKING_DIR

# This line can be removed and replace with the --pythonpath PYTHON_PATH \\
# option with Gunicorn>1.17
env PYTHONPATH=PYTHON_PATH
env A="1"
env B="1 2"


exec gunicorn \\
    --name=PROJECT_NAME \\
    --workers=WSGI_WORKERS \\
    --worker-class=WSGI_WORKER_CLASS \\
    --worker-connections=WSGI_WORKER_CONNECTIONS \\
    --max-requests=WSGI_MAX_REQUESTS \\
    --backlog=WSGI_BACKLOG \\
    --timeout=WSGI_TIMEOUT \\
    --keep-alive=WSGI_KEEP_ALIVE \\
    --umask=WSGI_UMASK \\
    --bind=LISTEN_IP:PORT \\
    --log-file=WSGI_LOG_FILE \\
    --log-level=WSGI_LOG_LEVEL \\
    WSGI_EXTRA \\
    WSGI_WSGI_FILE
""".strip()


class TemplateTestCase(TestCase):
    maxDiff = None

    def setUp(self):
        super(TemplateTestCase, self).setUp()
        patch_open = patch('hooks.open', create=True)
        self.open = patch_open.start()
        self.addCleanup(patch_open.stop)

        self.open.return_value = MagicMock(spec=file)
        self.file = self.open.return_value.__enter__.return_value

        patch_environ = patch.dict(os.environ, CHARM_DIR='.')
        patch_environ.start()
        self.addCleanup(patch_environ.stop)

        patch_hookenv = patch('hooks.hookenv')
        patch_hookenv.start()
        self.addCleanup(patch_hookenv.stop)

    def test_template(self):
        keys = [
            'project_name',
            'wsgi_user',
            'wsgi_group',
            'working_dir',
            'python_path',
            'wsgi_workers',
            'wsgi_worker_class',
            'wsgi_worker_connections',
            'wsgi_max_requests',
            'wsgi_backlog',
            'wsgi_timeout',
            'wsgi_keep_alive',
            'wsgi_umask',
            'wsgi_log_file',
            'wsgi_log_level',
            'wsgi_access_logfile',
            'wsgi_access_logformat',
            'listen_ip',
            'port',
            'wsgi_extra',
            'wsgi_wsgi_file',
        ]
        ctx = dict((k, k.upper()) for k in keys)
        ctx['env_extra'] = dict(A="1", B="1 2").items()

        hooks.process_template('upstart.tmpl', ctx, 'path')
        output = self.file.write.call_args[0][0]

        self.assertMultiLineEqual(EXPECTED, output)
