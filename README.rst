Juju charm gunicorn
===================

:Author: Patrick Hetu <patrick@koumbit.org>

How to configure the charm
--------------------------

To deploy a charm with this subordinate it must minimaly:

  1. Provide the wsgi interface.
  2. Set the `working_dir` relation variable in the wsgi hook.

The configuration of Gunicorn will use the variable pass by
the relation hook first. If there are not define it will
fallback to the global configuration of the charm.

Example deployment
------------------

1. Deployment with python-moinmoin for example::

    juju bootstrap
    juju deploy --config mywiki_with_wsgi_settings.yaml python-moinmoin
    juju deploy gunicorn
    juju add-relation gunicorn python-moinmoin
    juju expose python-moinmoin

2. Accessing your new wiki should be ready at::

       http://<machine-addr>:8080/

   To find out the public address of gunicorn/python-moinmoin, look for it in
   the output of the `juju status` command.
   I recommend using a reverse proxy like Nginx in front of Gunicorn. 

Changelog
---------
3:

  Notable changes:

    * Rewrite the charm using python instead of BASH scripts
    * add listen_ip configuration variable

  Backwards incompatible changes:
    * Remove the Django mode since Gunicorn is not recommending it anymore.
    * Use Upstart to manage daemons
    * no start/stop hook anymore use related charms instead.
    * no configuration change directly on the charm anymore, use related charms instead.
    * no access logging by default
    * exposing a port must now be done in the linked charm instead of this one
