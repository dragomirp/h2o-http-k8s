#!/usr/bin/env python3
# Copyright 2022 Dragomir Penev
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""Simple h2o server charm."""

import logging
import urllib
from io import StringIO

import yaml
from charms.nginx_ingress_integrator.v0.ingress import IngressRequires
from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, MaintenanceStatus, WaitingStatus

logger = logging.getLogger(__name__)

BASE_CONFIG = {
    "hosts": {
        "default": {
            "listen": {"port": 8080},
            "paths": {
                "/": {
                    "file.dir": "/var/www/html",
                }
            },
        }
    },
    "access-log": "/dev/stdout",
    "error-log": "/dev/stderr",
}


class H2OHttpK8SCharm(CharmBase):
    """Charm the service."""

    def __init__(self, *args):
        super().__init__(*args)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.h2o_http_pebble_ready, self._on_h2o_http_pebble_ready)
        self.framework.observe(self.on.pull_example_site_action, self._pull_example_site_action)

        self.ingress = IngressRequires(
            self,
            {
                "service-hostname": self.config["external_hostname"],
                "service-name": self.app.name,
                "service-port": 8080,
            },
        )

    def _on_config_changed(self, event):
        container = self.unit.get_container("h2o-http")
        if container.can_connect() and container.get_services():
            if self.model.unit.is_leader():
                relation = self.model.get_relation("ingress")
                if (
                    relation
                    and relation.data[self.model.app]["service-hostname"]
                    != self.config["external_hostname"]
                ):
                    self.ingress.update_config(
                        {"service-hostname": self.config["external_hostname"]}
                    )

            if self.config["dirlisting"]:
                BASE_CONFIG["hosts"]["default"]["paths"]["/"]["file.dirlisting"] = "ON"
            else:
                BASE_CONFIG["hosts"]["default"]["paths"]["/"]["file.dirlisting"] = "OFF"
            h2o_config = StringIO(yaml.dump(BASE_CONFIG))
            container.push("/home/h2o/h2o.conf", h2o_config, make_dirs=True)

            container.restart("h2o-http")

            self.unit.status = ActiveStatus()
        else:
            event.defer()
            self.unit.status = WaitingStatus("waiting for Pebble API")

    def _on_h2o_http_pebble_ready(self, event):
        container = event.workload
        container.add_layer("h2o-http", self._h2o_layer, combine=True)
        container.replan()
        self.unit.status = ActiveStatus()

    @property
    def _h2o_layer(self):
        return {
            "summary": "h2o-http layer",
            "description": "pebble config layer for h2o-http",
            "services": {
                "h2o-http": {
                    "override": "replace",
                    "summary": "h2o",
                    "command": "h2o --conf h2o.conf",
                    "startup": "enabled",
                }
            },
        }

    def _pull_example_site_action(self, event):
        """Action handler that pulls an example site."""
        self.unit.status = MaintenanceStatus("Fetching web site")
        urllib.request.urlretrieve("http://example.com", "/srv/index.html")
        self.unit.status = ActiveStatus()
        event.set_results({"result": "site pulled"})


if __name__ == "__main__":  # pragma: nocover
    main(H2OHttpK8SCharm)
