# Gunicorn

Author: 

- Patrick Hetu <patrick@koumbit.org>

# How to configure the charm

To deploy a charm with this subordinate it must minimally:

 1. Provide the wsgi interface.
 2. Set the `working_dir` relation variable in the wsgi hook.

The configuration of Gunicorn will use the variable pass by
the relation hook first. If there are not define it will
fallback to the global configuration of the charm.

# Example deployment

 1. Deployment with python-django for example::

        juju bootstrap
        juju deploy python-django
        juju deploy postgresql
        juju deploy gunicorn
        juju add-relation python-django postgresql:db
        juju add-relation gunicorn python-django
        juju expose python-django

 2. Accessing your new django app should be ready at::

        http://<machine-addr>:8080/

   To find out the public address of gunicorn/python-django, look for it in
   the output of the `juju status` command.
   I recommend using a reverse proxy like Nginx in front of Gunicorn. 

# Changelog

4:

Notable changes:

- re-add support for env_extra parameter that was dropped in r3, but with new
  standard shell format.  e.g. env_extra="FOO=BAR BAZ=QUX". Also supports old
  r2 format (env_extra="'foo': 'bar', 'baz': 'qux'") to provide an upgrade
  path.
- if upgrading from r1 or r2, the old gunicorn config is removed, leaving just
  the custom upstart job.

No backwards incompatible changes.

3:

Notable changes:

- Rewrite the charm using python instead of BASH scripts
- add listen_ip configuration variable

Backwards incompatible changes:

- Remove the Django mode since Gunicorn is not recommending it anymore.
- Use Upstart to manage daemons
- no start/stop hook anymore use related charms instead.
- no configuration change directly on the charm anymore, use related charms instead.
- no access logging by default
- exposing a port must now be done in the linked charm instead of this one

