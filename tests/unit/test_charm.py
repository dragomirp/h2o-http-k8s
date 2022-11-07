# Copyright 2022 Dragomir Penev
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import unittest
from unittest.mock import Mock, patch

import ops.testing
import yaml
from ops.model import ActiveStatus, WaitingStatus
from ops.testing import Harness

from charm import H2OHttpK8SCharm


class TestCharm(unittest.TestCase):
    def setUp(self):
        # Enable more accurate simulation of container networking.
        # For more information, see https://juju.is/docs/sdk/testing#heading--simulate-can-connect
        ops.testing.SIMULATE_CAN_CONNECT = True
        self.addCleanup(setattr, ops.testing, "SIMULATE_CAN_CONNECT", False)

        self.harness = Harness(H2OHttpK8SCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    def test_h2o_http_pebble_ready(self):
        expected_plan = {
            "services": {
                "h2o-http": {
                    "override": "replace",
                    "summary": "h2o",
                    "command": "h2o --conf h2o.conf",
                    "startup": "enabled",
                }
            }
        }
        self.harness.container_pebble_ready("h2o-http")
        updated_plan = self.harness.get_container_pebble_plan("h2o-http").to_dict()
        self.assertEqual(expected_plan, updated_plan)
        service = self.harness.model.unit.get_container("h2o-http").get_service("h2o-http")
        self.assertTrue(service.is_running())
        self.assertEqual(self.harness.model.unit.status, ActiveStatus())

    def test_config_changed_initial_config(self):
        expected_config = {
            "hosts": {
                "default": {
                    "listen": {"port": 8080},
                    "paths": {
                        "/": {
                            "file.dir": "/var/www/html",
                            "file.dirlisting": "OFF",
                        }
                    },
                }
            },
            "access-log": "/dev/stdout",
            "error-log": "/dev/stderr",
        }
        self.harness.set_can_connect("h2o-http", True)
        self.harness.container_pebble_ready("h2o-http")

        self.harness.update_config()
        config = self.harness.model.unit.get_container("h2o-http").pull("/home/h2o/h2o.conf")
        self.assertEqual(expected_config, yaml.safe_load(config))
        self.assertEqual(self.harness.model.unit.status, ActiveStatus())

    def test_config_changed_valid_can_connect(self):
        expected_config = {
            "hosts": {
                "default": {
                    "listen": {"port": 8080},
                    "paths": {
                        "/": {
                            "file.dir": "/var/www/html",
                            "file.dirlisting": "ON",
                        }
                    },
                }
            },
            "access-log": "/dev/stdout",
            "error-log": "/dev/stderr",
        }
        self.harness.set_can_connect("h2o-http", True)
        self.harness.container_pebble_ready("h2o-http")

        self.harness.update_config({"dirlisting": True})
        config = self.harness.model.unit.get_container("h2o-http").pull("/home/h2o/h2o.conf")
        self.assertEqual(expected_config, yaml.safe_load(config))
        self.assertEqual(self.harness.model.unit.status, ActiveStatus())

    def test_config_changed_valid_cannot_connect(self):
        self.harness.update_config({"dirlisting": True})
        self.assertIsInstance(self.harness.model.unit.status, WaitingStatus)

    @patch("charm.IngressRequires.update_config")
    def test_config_changed_external_hostname_not_leader(self, ingress):
        self.harness.set_can_connect("h2o-http", True)
        self.harness.container_pebble_ready("h2o-http")
        self.harness.update_config({"external_hostname": "test.com"})
        self.assertFalse(ingress.return_value.update_config.called)

    @patch("charm.IngressRequires.update_config")
    def test_config_changed_external_hostname_leader_no_relation(self, ingress):
        self.harness.set_can_connect("h2o-http", True)
        self.harness.set_leader(True)
        self.harness.container_pebble_ready("h2o-http")
        self.harness.update_config({"external_hostname": "test.com"})
        self.assertFalse(ingress.return_value.update_config.called)

    @patch("charm.IngressRequires.update_config")
    def test_config_changed_external_hostname_success(self, ingress):
        self.harness.set_can_connect("h2o-http", True)
        self.harness.set_leader(True)
        relation_id = self.harness.add_relation("ingress", "nginx-ingress")
        self.harness.update_relation_data(
            relation_id, "nginx-ingress", {"service-hostname": "example.com"}
        )
        self.harness.container_pebble_ready("h2o-http")
        self.harness.update_config({"external_hostname": "test.com"})
        ingress.assert_called_once_with({"service-hostname": "test.com"})

    @patch("charm.urllib.request.urlretrieve")
    def test_pull_example_site_action(self, urlretrieve):
        mock_event = Mock()
        self.harness.charm._pull_example_site_action(mock_event)
        urlretrieve.assert_called_once()
        mock_event.set_results.assert_called_once_with({"result": "site pulled"})
