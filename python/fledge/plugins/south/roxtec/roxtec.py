# -*- coding: utf-8 -*-

# FLEDGE_BEGIN
# See: http://fledge.readthedocs.io/
# FLEDGE_END

"""HTTP Listener handler for Roxtec transit data"""
import asyncio
import copy
import os
import ssl
import logging
import uuid
import datetime

from threading import Thread
from aiohttp import web

from fledge.common import logger
from fledge.common.web import middleware
from fledge.plugins.common import utils
import async_ingest

__author__ = "Mark Riddoch, Ashish Jabble"
__copyright__ = "Copyright (c) 2018 Dianomic Systems"
__license__ = "Apache 2.0"
__version__ = "${VERSION}"

_LOGGER = logger.setup(__name__, level=logging.INFO)

_FLEDGE_DATA = os.getenv("FLEDGE_DATA", default=None)
_FLEDGE_ROOT = os.getenv("FLEDGE_ROOT", default='/usr/local/fledge')

c_callback = None
c_ingest_ref = None
loop = None
t = None
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
        'default': 'fledge',
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


def plugin_info():
    return {
        'name': 'Roxtec Transit',
        'version': '1.5.0',
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
    handle = copy.deepcopy(config)
    return handle


def plugin_start(data):
    global loop, t

    try:
        host = data['host']['value']
        port = data['port']['value']
        uri = data['uri']['value']

        loop = asyncio.new_event_loop()

        app = web.Application(middlewares=[middleware.error_middleware], loop=loop)
        app.router.add_route('PUT', '/{}'.format(uri), RoxtecTransitIngest.render_put)
        app.router.add_route('POST', '/{}'.format(uri), RoxtecTransitIngest.render_put)
        handler = app.make_handler(loop=loop)

        # SSL context
        ssl_ctx = None

        is_https = True if data['enableHttp']['value'] == 'false' else False
        if is_https:
            port = data['httpsPort']['value']
            cert_name = data['certificateName']['value']
            ssl_ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            cert, key = get_certificate(cert_name)
            _LOGGER.info('Loading TLS certificate %s and key %s', cert, key)
            ssl_ctx.load_cert_chain(cert, key)

        server_coro = loop.create_server(handler, host, port, ssl=ssl_ctx)
        future = asyncio.ensure_future(server_coro, loop=loop)

        data['app'] = app
        data['handler'] = handler
        data['server'] = None

        def f_callback(f):
            # _LOGGER.info(repr(f.result()))
            """ <Server sockets=
            [<socket.socket fd=17, family=AddressFamily.AF_INET, type=2049,proto=6, laddr=('0.0.0.0', 6683)>]>"""
            data['server'] = f.result()

        future.add_done_callback(f_callback)

        def run():
            global loop
            loop.run_forever()

        t = Thread(target=run)
        t.start()
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

    global loop
    plugin_shutdown(handle)
    new_handle = plugin_init(new_config)
    plugin_start(new_handle)

    return new_handle


def plugin_shutdown(handle):
    """ Shutdowns the plugin doing required cleanup, to be called prior to the South service being shut down.

    Args:
        handle: handle returned by the plugin initialisation call
    Returns:
    Raises:
    """
    _LOGGER.info('Roxtec Transit plugin shutting down.')

    global loop
    try:
        app = handle['app']
        handler = handle['handler']
        server = handle['server']

        if server:
            server.close()
            asyncio.ensure_future(server.wait_closed(), loop=loop)
            asyncio.ensure_future(app.shutdown(), loop=loop)
            asyncio.ensure_future(handler.shutdown(60.0), loop=loop)
            asyncio.ensure_future(app.cleanup(), loop=loop)
        loop.stop()
    except Exception as e:
        _LOGGER.exception(str(e))
        raise


def plugin_register_ingest(handle, callback, ingest_ref):
    """Required plugin interface component to communicate to South C server

    Args:
        handle: handle returned by the plugin initialisation call
        callback: C opaque object required to passed back to C->ingest method
        ingest_ref: C opaque object required to passed back to C->ingest method
    """
    global c_callback, c_ingest_ref
    c_callback = callback
    c_ingest_ref = ingest_ref


def get_certificate(cert_name):
    if _FLEDGE_DATA:
        certs_dir = os.path.expanduser(_FLEDGE_DATA + '/etc/certs')
    else:
        certs_dir = os.path.expanduser(_FLEDGE_ROOT + '/data/etc/certs')

    cert = certs_dir + '/{}.cert'.format(cert_name)
    key = certs_dir + '/{}.key'.format(cert_name)

    if not os.path.isfile(cert) or not os.path.isfile(key):
        _LOGGER.warning("%s certificate files are missing. Hence using default certificate.", cert_name)
        cert = certs_dir + '/fledge.cert'
        key = certs_dir + '/fledge.key'
        if not os.path.isfile(cert) or not os.path.isfile(key):
            _LOGGER.error("Certificates are missing")
            raise RuntimeError

    return cert, key


class RoxtecTransitIngest(object):
    """Handles incoming sensor readings from Roxtec Transit Listener"""

    @staticmethod
    async def render_put(request):
        """Store sensor readings from Roxtec to Fledge

        Args:
            request:
                The payload block decodes to JSON similar to the following:

                .. code-block:: python

        {
                    "guard_id": "444DF705F0F8",
                    "gateway_id": "device-0",
                    "state": 70,
                    "transit_id": "t11",
                    "battery": 4,
                    "pressure": 722,
                    "temperature": 0,
                    "last_seen": 1533816739126
                }

        Example:
            curl --insecure -X PUT https://localhost:1608/transit -d '[{ "guard_id": "444DF705F0F8", "gateway_id": "device-0", "state": 70, "transit_id": "t11", "battery": 4, "pressure": 722, "temperature": 0, "last_seen": 1533816739126 }]'
            curl -X PUT http://localhost:8608/transit -d '[{ "guard_id": "444DF705F0F8", "gateway_id": "device-0", "state": 70, "transit_id": "t11", "battery": 4, "pressure": 722, "temperature": 0, "last_seen": 1533816739126 }]'
        """
        try:
            message = {'result': 'success'}
            payload_block = await request.json()
            if type(payload_block) is not list:
                raise ValueError('Payload block must be a valid list')

            for payload in payload_block:
                asset = "Guard " + payload['guard_id']
                epoch_ms = payload['last_seen'] / 1000.0
                timestamp = datetime.datetime.fromtimestamp(epoch_ms).strftime('%Y-%m-%d %H:%M:%S.%f')
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

                data = {
                    'asset': asset,
                    'timestamp': timestamp,
                    'key': key,
                    'readings': readings
                }
                async_ingest.ingest_callback(c_callback, c_ingest_ref, data)
        except (KeyError, ValueError, TypeError) as e:
            _LOGGER.exception("%d: %s", web.HTTPBadRequest.status_code, e)
            raise web.HTTPBadRequest(reason=e)
        except Exception as ex:
            _LOGGER.exception("%d: %s", web.HTTPInternalServerError.status_code, str(ex))
            raise web.HTTPInternalServerError(reason=str(ex))

        return web.json_response(message)
