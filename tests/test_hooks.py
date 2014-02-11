from unittest import TestCase
from mock import patch

import yaml

import hooks


def load_config_defaults():
    with open("config.yaml") as conf:
        config_schema = yaml.safe_load(conf)
    defaults = {}
    for key, value in config_schema['options'].items():
        defaults[key] = value['default']
    return defaults

DEFAULTS = load_config_defaults()


class HookTestCase(TestCase):
    maxDiff = None

    SERVICE_NAME = 'some_juju_service'
    WORKING_DIR = '/some_path'

    _object = object()
    mocks = {}

    def apply_patch(self, name, value=_object, return_value=_object):
        if value is not self._object:
            patcher = patch(name, value)
        else:
            patcher = patch(name)

        mock_obj = patcher.start()
        self.addCleanup(patcher.stop)

        if value is self._object and return_value is not self._object:
            mock_obj.return_value = return_value

        self.mocks[name] = mock_obj
        return mock_obj

    def setUp(self):
        super(HookTestCase, self).setUp()
        # There's quite a bit of mocking here, due to the large amounts of
        # environment context to juju hooks

        self.config = DEFAULTS.copy()
        self.relation_data = {'working_dir': self.WORKING_DIR}

        # intercept all charmsupport usage
        self.hookenv = self.apply_patch('hooks.hookenv')
        self.fetch = self.apply_patch('hooks.fetch')
        self.host = self.apply_patch('hooks.host')

        self.hookenv.config.return_value = self.config
        self.hookenv.relation_get.return_value = self.relation_data

        # mocking utilities that touch the host/environment
        self.process_template = self.apply_patch('hooks.process_template')
        self.apply_patch(
            'hooks.sanitized_service_name', return_value=self.SERVICE_NAME)
        self.apply_patch('hooks.cpu_count', return_value=1)

    def assert_wsgi_config_applied(self, expected):
        tmpl, config, path = self.process_template.call_args[0]
        self.assertEqual(tmpl, 'upstart.tmpl')
        self.assertEqual(path, '/etc/init/%s.conf' % self.SERVICE_NAME)
        self.assertEqual(config, expected)
        self.host.service_reload.assert_called_once_with(
            self.SERVICE_NAME, restart_on_failure=True
        )

    def get_default_context(self):
        expected = DEFAULTS.copy()
        expected['unit_name'] = self.SERVICE_NAME
        expected['working_dir'] = self.WORKING_DIR
        expected['project_name'] = self.SERVICE_NAME
        expected['wsgi_workers'] = 2
        fmt = expected['wsgi_access_logformat'].replace('"', '\\"')
        expected['wsgi_access_logformat'] = fmt
        return expected

    def test_python_install_hook(self):
        hooks.install()
        self.assertTrue(self.fetch.apt_update.called)
        self.fetch.apt_install.assert_called_once_with(
            ['gunicorn', 'python-jinja2'])

    def test_default_configure_gunicorn(self):
        hooks.configure_gunicorn()
        expected = self.get_default_context()
        self.assert_wsgi_config_applied(expected)

    def test_configure_gunicorn_no_working_dir(self):
        del self.relation_data['working_dir']
        hooks.configure_gunicorn()
        self.assertFalse(self.process_template.called)
        self.assertFalse(self.host.service_reload.called)

    def test_configure_gunicorn_relation_data(self):
        self.relation_data['port'] = 9999
        self.relation_data['wsgi_workers'] = 1
        self.relation_data['unknown'] = 'value'

        hooks.configure_gunicorn()

        self.assertFalse(self.fetch.apt_install.called)

        expected = self.get_default_context()
        expected['wsgi_workers'] = 1
        expected['port'] = 9999

        self.assert_wsgi_config_applied(expected)

    def do_worker_class(self, worker_class):
        self.relation_data['wsgi_worker_class'] = worker_class
        hooks.configure_gunicorn()
        self.fetch.apt_install.assert_called_once_with(
            'python-%s' % worker_class)
        expected = self.get_default_context()
        expected['wsgi_worker_class'] = worker_class
        self.assert_wsgi_config_applied(expected)

    def test_configure_worker_class_eventlet(self):
        self.do_worker_class('eventlet')

    def test_configure_worker_class_tornado(self):
        self.do_worker_class('tornado')

    def test_configure_worker_class_gevent(self):
        self.do_worker_class('gevent')

    @patch('hooks.os.remove')
    def test_wsgi_file_relation_broken(self, remove):
        hooks.wsgi_file_relation_broken()
        self.host.service_stop.assert_called_once_with(self.SERVICE_NAME)
        remove.assert_called_once_with(
            '/etc/init/%s.conf' % self.SERVICE_NAME)
