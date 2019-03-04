# -*- coding: utf-8 -*-

# FOGLAMP_BEGIN
# See: http://foglamp.readthedocs.io/
# FOGLAMP_END

"""Unit test for python.foglamp.plugins.south.roxtec"""

import pytest

from python.foglamp.plugins.south.roxtec import roxtec
from python.foglamp.plugins.south.roxtec.roxtec import _DEFAULT_CONFIG as config

__author__ = "Ashish Jabble"
__copyright__ = "Copyright (c) 2019 Dianomic Systems"
__license__ = "Apache 2.0"
__version__ = "${VERSION}"


_NEW_CONFIG = {
    'plugin': {
        'description': 'Roxtec South Plugin',
        'type': 'string',
        'default': 'roxtec',
        'readonly': 'true'
    },
    'port': {
        'description': 'Port to listen on',
        'type': 'integer',
        'default': '8608',
        'order': '2',
        'displayName': 'Port'
    },
    'httpsPort': {
        'description': 'Port to accept HTTPS connections on',
        'type': 'integer',
        'default': '1608',
        'order': '5',
        'displayName': 'Https Port'
    },
    'enableHttp': {
        'description': 'Enable HTTP connections',
        'type': 'boolean',
        'default': 'false',
        'order': '4',
        'displayName': 'Enable Http'
    },
    'certificateName': {
        'description': 'Certificate file name',
        'type': 'string',
        'default': 'foglamp',
        'order': '6',
        'displayName': 'Certificate Name'
    },
    'host': {
        'description': 'Address to accept data on',
        'type': 'string',
        'default': '0.0.0.0',
        'order': '1',
        'displayName': 'Host'
    },
    'uri': {
        'description': 'URI to accept data on',
        'type': 'string',
        'default': 'transit',
        'order': '3',
        'displayName': 'URI'
    }
}


def test_plugin_contract():
    # Evaluates if the plugin has all the required methods
    assert callable(getattr(roxtec, 'plugin_info'))
    assert callable(getattr(roxtec, 'plugin_init'))
    assert callable(getattr(roxtec, 'plugin_start'))
    assert callable(getattr(roxtec, 'plugin_shutdown'))
    assert callable(getattr(roxtec, 'plugin_reconfigure'))

    assert callable(getattr(roxtec, 'plugin_register_ingest'))


def test_plugin_info():
    assert roxtec.plugin_info() == {
        'name': 'Roxtec Transit',
        'version': '2.0',
        'mode': 'async',
        'type': 'south',
        'interface': '1.0',
        'config': config
    }


def test_plugin_init():
    assert roxtec.plugin_init(config) == config


@pytest.mark.asyncio
@pytest.mark.skip(reason='Not Implemented Yet')
async def test_plugin_start():
    pass


@pytest.mark.asyncio
@pytest.mark.skip(reason='Not Implemented Yet')
async def test_plugin_reconfigure():
    pass


@pytest.mark.asyncio
@pytest.mark.skip(reason='Not Implemented Yet')
async def test_plugin_shutdown():
    pass
