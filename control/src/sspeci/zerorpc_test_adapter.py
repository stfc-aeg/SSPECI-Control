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
        self.client = zerorpc.Client(heartbeat=20)
        # self.client.debug = True
        self.client.connect(self.endpoint)

        # self.set_start_lightfield(True)

        self.param_tree = ParameterTree({
            "device_found": (self.get_device_found, None),
            "lightfield_running": (self.is_lightfield_running, None),
            "start_lightfield": (None, self.set_start_lightfield),
            "spectrometer":
            {
                    
            },
            "camera":
            {
                "exposure": (self.get_camera_exposure, self.set_camera_exposure)
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

    def is_lightfield_running(self):

        try:
            return self.client.is_lightfield_started()
        except (LostRemote, TimeoutExpired) as remote_err:
            logging.error("Remote Error trying to get Lightfield status: %s", remote_err)

    def get_camera_exposure(self):
        
        try:
            return self.client.get_camera_exposure()
        except (LostRemote, TimeoutExpired) as remote_err:
            logging.error("Remote error trying to get camera exposure: %s", remote_err)
            return None

    def set_camera_exposure(self, value):
        
        try:
            self.client.set_camera_exposure(value)
        except (LostRemote, TimeoutExpired) as remote_err:
            logging.error("Remote error trying to set camera exposure: %s", remote_err)


    def get_spectrometer_grating_selected(self):
        pass

    def get_spectrometer_grating_status(self):
        pass

    def get_spectrometer_center_wavelength(self):
        pass

