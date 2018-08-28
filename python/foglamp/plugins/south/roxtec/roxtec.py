# -*- coding: utf-8 -*-

# FOGLAMP_BEGIN
# See: http://foglamp.readthedocs.io/
# FOGLAMP_END

"""HTTP Listener handler for Roxtec transit data"""
import asyncio
import copy
import os
import ssl
import logging
import uuid 
import datetime

from aiohttp import web

from foglamp.common import logger
from foglamp.common.web import middleware
from foglamp.plugins.common import utils
from foglamp.services.south.ingest import Ingest

__author__ = "Mark Riddoch"
__copyright__ = "Copyright (c) 2018 Dianomic Systems"
__license__ = "Apache 2.0"
__version__ = "${VERSION}"

_LOGGER = logger.setup(__name__, level=logging.INFO)

_FOGLAMP_DATA = os.getenv("FOGLAMP_DATA", default=None)
_FOGLAMP_ROOT = os.getenv("FOGLAMP_ROOT", default='/usr/local/foglamp')

_DEFAULT_CONFIG = {
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
        'order': '3'
    },
    'httpsPort': {
        'description': 'Port to accept HTTPS connections on',
        'type': 'integer',
        'default': '1608',
        'order': '4'
    },
    'enableHttp': {
        'description': 'Enable HTTP connections',
        'type': 'boolean',
        'default': 'false',
        'order': '5'
    },
    'certificateName': {
        'description': 'Certificate file name',
        'type': 'string',
        'default': 'foglamp',
        'order': '6'
    },
    'host': {
        'description': 'Address to accept data on',
        'type': 'string',
        'default': '0.0.0.0',
        'order': '1'
    },
    'uri': {
        'description': 'URI to accept data on',
        'type': 'string',
        'default': 'transit',
        'order': '2'
    }
}


def plugin_info():
    return {
            'name': 'Roxtec Trsnsit',
            'version': '1.0',
            'mode': 'async',
            'type': 'south',
            'interface': '1.0',
            'config': _DEFAULT_CONFIG
    }


def plugin_init(config):
    """Initialises the Roxtec Transit south plugin

    Args:
        config: JSON configuration document for the South plugin configuration category
    Returns:
        handle: JSON object to be used in future calls to the plugin
    Raises:
    """
    handle = config
    return handle


def plugin_start(data):
    try:
        host = data['host']['value']
        port = data['port']['value']
        uri = data['uri']['value']

        loop = asyncio.get_event_loop()

        app = web.Application(middlewares=[middleware.error_middleware])
        app.router.add_route('PUT', '/{}'.format(uri), RoxtecTransitIngest.render_put)
        app.router.add_route('POST', '/{}'.format(uri), RoxtecTransitIngest.render_put)
        handler = app.make_handler()

        # SSL context
        ssl_ctx = None

        is_https = True if data['enableHttp']['value'] == 'false' else False
        if is_https:
            port = data['httpsPort']['value']
            cert_name =  data['certificateName']['value']
            ssl_ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            cert, key = get_certificate(cert_name)
            _LOGGER.info('Loading TLS certificate %s and key %s', cert, key)
            ssl_ctx.load_cert_chain(cert, key)

        server_coro = loop.create_server(handler, host, port, ssl=ssl_ctx)
        future = asyncio.ensure_future(server_coro)

        data['app'] = app
        data['handler'] = handler
        data['server'] = None

        def f_callback(f):
            # _LOGGER.info(repr(f.result()))
            """ <Server sockets=
            [<socket.socket fd=17, family=AddressFamily.AF_INET, type=2049,proto=6, laddr=('0.0.0.0', 6683)>]>"""
            data['server'] = f.result()

        future.add_done_callback(f_callback)
    except Exception as e:
        _LOGGER.exception(str(e))


def plugin_reconfigure(handle, new_config):
    """ Reconfigures the plugin

    it should be called when the configuration of the plugin is changed during the operation of the South service;
    The new configuration category should be passed.

    Args:
        handle: handle returned by the plugin initialisation call
        new_config: JSON object representing the new configuration category for the category
    Returns:
        new_handle: new handle to be used in the future calls
    Raises:
    """
    _LOGGER.info("Old config for Roxtec plugin {} \n new config {}".format(handle, new_config))

    # Find diff between old config and new config
    diff = utils.get_diff(handle, new_config)

    # Plugin should re-initialize and restart if key configuration is changed
    if 'port' in diff or 'httpsPort' in diff or 'certificateName' in diff or 'enableHttp' in diff or 'host' in diff:
        plugin_shutdown(handle)
        new_handle = plugin_init(new_config)
        new_handle['restart'] = 'yes'
        _LOGGER.info("Restarting Roxtec plugin due to change in configuration keys [{}]".format(', '.join(diff)))
    else:
        new_handle = copy.deepcopy(new_config)
        new_handle['restart'] = 'no'
    return new_handle


def _plugin_stop(handle):
    _LOGGER.info('Stopping Roxtec Transit plugin.')
    try:
        app = handle['app']
        handler = handle['handler']
        server = handle['server']

        if server:
            server.close()
            asyncio.ensure_future(server.wait_closed())
            asyncio.ensure_future(app.shutdown())
            asyncio.ensure_future(handler.shutdown(60.0))
            asyncio.ensure_future(app.cleanup())
    except Exception as e:
        _LOGGER.exception(str(e))
        raise


def plugin_shutdown(handle):
    """ Shutdowns the plugin doing required cleanup, to be called prior to the South service being shut down.

    Args:
        handle: handle returned by the plugin initialisation call
    Returns:
    Raises:
    """
    _plugin_stop(handle)
    _LOGGER.info('Roxtec Transit plugin shut down.')



def get_certificate(cert_name):

    if _FOGLAMP_DATA:
        certs_dir = os.path.expanduser(_FOGLAMP_DATA + '/etc/certs')
    else:
        certs_dir = os.path.expanduser(_FOGLAMP_ROOT + '/data/etc/certs')

    cert = certs_dir + '/{}.cert'.format(cert_name)
    key = certs_dir + '/{}.key'.format(cert_name)

    if not os.path.isfile(cert) or not os.path.isfile(key):
        _LOGGER.warning("%s certificate files are missing. Hence using default certificate.", cert_name)
        cert = certs_dir + '/foglamp.cert'
        key = certs_dir + '/foglamp.key'
        if not os.path.isfile(cert) or not os.path.isfile(key):
            _LOGGER.error("Certificates are missing")
            raise RuntimeError

    return cert, key

class RoxtecTransitIngest(object):
    """Handles incoming sensor readings from HTTP Listener"""

    @staticmethod
    async def render_put(request):
        """Store sensor readings from Roxtec to FogLAMP

        Args:
            request:
                The payload block decodes to JSON similar to the following:

                .. code-block:: python

		{
                    "guard_id": "444DF705F0F8",
                    "gateway_id": "device-0"
                    "state": 70,
                    "transit_id": "t11",
                    "battery": 4,
                    "pressure": 722,
                    "temperature": 0,
                    "last_seen": 1533816739126
                }

        Example:
            curl -X PUT http://localhost:1608/transit -d '[{ "guard_id": "444DF705F0F8", "gateway_id": "device-0" "state": 70, "transit_id": "t11", "battery": 4, "pressure": 722, "temperature": 0, "last_seen": 1533816739126 }]'
        """
        message = {'result': 'success'}
        try:
            if not Ingest.is_available():
                message = {'busy': True}
                raise web.HTTPServiceUnavailable(reason=message)

            try:
                payload_block = await request.json()
            except Exception:
                raise ValueError('Payload block must be a valid json')

            if type(payload_block) is not list:
                raise ValueError('Payload block must be a valid list')

            for payload in payload_block:
                asset = "Guard " + payload['guard_id']
                epochMs = payload['last_seen'] / 1000.0
                timestamp = datetime.datetime.fromtimestamp(epochMs).strftime('%Y-%m-%d %H:%M:%S.%f')
                key = str(uuid.uuid4())
                readings = {
                    "gateway_id": payload['gateway_id'],
                    "state": payload['state'],
                    "battery": payload['battery'],
                    "pressure": payload['pressure'],
                    "temperature": payload['temperature']
                }
                if 'transit_id' in payload and payload['transit_id'] is not None:
                    readings['transit_id'] = payload['transit_id']

                await Ingest.add_readings(asset=asset, timestamp=timestamp, key=key, readings=readings)
            
        except (KeyError, ValueError, TypeError) as e:
            Ingest.increment_discarded_readings()
            _LOGGER.exception("%d: %s", web.HTTPBadRequest.status_code, e)
            raise web.HTTPBadRequest(reason=e)
        except Exception as ex:
            Ingest.increment_discarded_readings()
            _LOGGER.exception("%d: %s", web.HTTPInternalServerError.status_code, str(ex))
            raise web.HTTPInternalServerError(reason=str(ex))

        return web.json_response(message)
