import logging
import sys
import os
import json
from gevent.timeout import Timeout

import zerorpc
from zerorpc.exceptions import (LostRemote, TimeoutExpired)

from odin_data.ipc_channel import IpcChannel, IpcChannelException
from odin_data.ipc_message import IpcMessage, IpcMessageException

from odin.adapters.adapter import (ApiAdapter, ApiAdapterRequest,
                                   ApiAdapterResponse, request_types, response_types)
from odin.adapters.parameter_tree import ParameterTree, ParameterTreeError
from odin.util import decode_request_body

from tornado.ioloop import PeriodicCallback


class ZeroRPCTestAdapter(ApiAdapter):


    def __init__(self, **kwargs):
        super(ZeroRPCTestAdapter, self).__init__(**kwargs)

        self.endpoint = self.options.get("endpoint", "tcp://127.0.0.1:4242")

        # try:
        self.client = zerorpc.Client()
        # self.client.debug = True
        self.client.connect(self.endpoint)

        self.param_tree = ParameterTree({
            "server_string": (self.get_string, self.set_string),
            "device_found": (self.get_device_found, None),
            "start_lightfield": (None, self.set_start_lightfield),
            "spectrometer":
                {
                    
            }
        })
        # except (LostRemote, TimeoutExpired) as remote_err:
            # logging.error("Unable to connect to Server: %s", remote_err)

        logging.getLogger("zerorpc.channel").setLevel(logging.WARNING)




    @response_types('application/json', default='application/json')
    def get(self, path, request):
        try:
            response = self.param_tree.get(path)
            content_type = 'application/json'
            status = 200
        except ParameterTreeError as param_error:
            response = {'response': 'ZeroRPC GET error: {}'.format(param_error)}
            content_type = 'application/json'
            status = 400
        except (LostRemote, TimeoutExpired) as remote_err:
            response = {'response': "ZeroRPC REMOTE GET Error: {}".format(remote_err)}
            content_type = "application/json"
            status = 400
    
        return ApiAdapterResponse(response, content_type=content_type, status_code=status)

    @response_types('application/json', default='application/json')
    def put(self, path, request):
        try:
            data = decode_request_body(request)
            self.param_tree.set(path, data)

            response = self.param_tree.get(path)
            content_type = 'application/json'
            status = 200

        except ParameterTreeError as param_error:
            response = {'response': 'ZeroRPC PUT error: {}'.format(param_error)}
            content_type = 'application/json'
            status = 400
        except (LostRemote, TimeoutExpired) as remote_err:
            response = {'response': "ZeroRPC REMOTE PUT Error: {}".format(remote_err)}
            content_type = "application/json"
            status = 400

        return ApiAdapterResponse(response, content_type=content_type, status_code=status)

    def get_string(self):

        try:
            val = self.client.give_string()
        
        except (LostRemote, TimeoutExpired) as remote_err:
            val = "Remote Error in get_string: {}".format(remote_err)

        return val

    def set_string(self, value):

        try:
            self.client.receive_string(value)

        except (LostRemote, TimeoutExpired) as remote_err:
            logging.error("Remote Error in set_string: %s", remote_err)

    def get_device_found(self):

        try:
            return self.client.device_found()
        except (LostRemote, TimeoutExpired) as remote_err:
            logging.error("Remote error in get_device_found: %s", remote_err)
            return False

    def set_start_lightfield(self, value):
        
        try:
            self.client.start_lightfield(value)
        except (LostRemote, TimeoutExpired) as remote_err:
            logging.error("Remote Error in set_start_lightfield: %s", remote_err)
        