import logging
import sys
import os
import json
from tempfile import TemporaryFile
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

logging.getLogger('matplotlib').setLevel(logging.WARNING)

import numpy as np
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt


class ZeroRPCTestAdapter(ApiAdapter):


    def __init__(self, **kwargs):
        super(ZeroRPCTestAdapter, self).__init__(**kwargs)

        self.endpoint = self.options.get("endpoint", "tcp://127.0.0.1:4242")

        # try:
        self.client = zerorpc.Client()
        # self.client.debug = True
        self.client.connect(self.endpoint)

        self.param_tree = ParameterTree({
            "start_lightfield": (None, self.set_start_lightfield),
            "get_data": (None, self.get_data),
            "binning":
                {
                    "binning_mode": (self.get_binning_mode, self.set_binning_mode),
                    "row_bin_centre": (self.get_row_bin_centre, self.set_row_bin_centre),
                    "bin_width": (self.get_bin_width, self.set_bin_width),
                    "bin_height": (self.get_bin_height, self.set_bin_height)
                },
            "acquisition":
            {
                "exposure": (self.get_exposure, self.set_exposure),
                "centre_wavelength": (self.get_centre_wavelength, self.set_centre_wavelength)
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

    def get_data(self, frames):

        try:
            frame_data = self.client.start_acquire(frames)
            data = np.array(frame_data['data'])
            data = data.reshape([frame_data['height'], frame_data['width']])
            logging.debug("Data shape: %s", data.shape)
            logging.debug("Data Type: %s", data.dtype)
            # plt.plot(data)
            plt.title("Science!")
            if frame_data['height'] == 1:
                plt.plot(data.reshape(-1))
                plt.xlabel("Wavelength (nm)")
                plt.ylabel("Intensity (Counts)")
            else:
                plt.imshow(data)
                plt.colorbar()
            plt.show()

        except (LostRemote, TimeoutExpired) as remote_err:
            logging.error("Remote Error in get_data: %s", remote_err)

    def get_binning_mode(self):

        try:
            return self.client.get_region_of_interest()
        except (LostRemote, TimeoutExpired) as remote_err:
            logging.error("Remote Error trying to Get Binning Mode: %s", remote_err)

    def set_binning_mode(self, value):

        try:
            self.client.set_region_of_interest(value)
        except (LostRemote, TimeoutExpired) as remote_err:
            logging.error("Remote Error trying to Set Binning Mode: %s", remote_err)

    def get_row_bin_centre(self):
        
        try:
            return self.client.get_line_bin_row()
        except (LostRemote, TimeoutExpired) as remote_err:
            logging.error("Remote Error: %s", remote_err)

    def set_row_bin_centre(self, value):
    
        try:
            self.client.set_line_bin_row(value)
        except (LostRemote, TimeoutExpired) as remote_err:
            logging.error("Remote Error: %s", remote_err)

    def get_bin_width(self):
        try:
            return self.client.get_num_columns_binned()
        except (LostRemote, TimeoutExpired) as remote_err:
            logging.error("Remote Error: %s", remote_err)

    def set_bin_width(self, value):
        try:
            self.client.set_num_columns_binned(value)
        except (LostRemote, TimeoutExpired) as remote_err:
            logging.error("Remote Error: %s", remote_err)

    def get_bin_height(self):
        try:
            return self.client.get_num_rows_binned()
        except (LostRemote, TimeoutExpired) as remote_err:
            logging.error("Remote Error: %s", remote_err)

    def set_bin_height(self, value):
        try:
            self.client.set_num_rows_binned(value)
        except (LostRemote, TimeoutExpired) as remote_err:
            logging.error("Remote Error: %s", remote_err)

    def get_exposure(self):
        try:
            return self.client.get_camera_exposure()
        except (LostRemote, TimeoutExpired) as remote_err:
            logging.error("Remote Error: %s", remote_err)

    def set_exposure(self, value):
        try:
            self.client.set_camera_exposure(value)
        except (LostRemote, TimeoutExpired) as remote_err:
            logging.error("Remote Error: %s", remote_err)

    def get_centre_wavelength(self):
        try:
            return self.client.get_centre_wavelength()
        except (LostRemote, TimeoutExpired) as remote_err:
            logging.error("Remote Error: %s", remote_err)

    def set_centre_wavelength(self, value):
        try:
            self.client.set_centre_wavelength(value)
        except (LostRemote, TimeoutExpired) as remote_err:
            logging.error("Remote Error: %s", remote_err)