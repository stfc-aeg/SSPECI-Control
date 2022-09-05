import logging
import re
import io
from socket import timeout
import sys
import os
import json

import zerorpc
from zerorpc.exceptions import (LostRemote, TimeoutExpired)

from odin.adapters.adapter import (ApiAdapter, ApiAdapterRequest,
                                   ApiAdapterResponse, request_types, response_types)
from odin.adapters.parameter_tree import ParameterTree, ParameterTreeError
from odin.util import decode_request_body

from tornado.ioloop import PeriodicCallback, IOLoop
from tornado.concurrent import run_on_executor
from concurrent import futures

logging.getLogger('matplotlib').setLevel(logging.WARNING)

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


class SpectrometerAdapter(ApiAdapter):

    executor = futures.ThreadPoolExecutor(max_workers=1)

    def __init__(self, **kwargs):
        super(SpectrometerAdapter, self).__init__(**kwargs)

        self.endpoint = self.options.get("endpoint", "tcp://127.0.0.1:4242")

        # try:
        self.client = zerorpc.Client(timeout=5)
        self.quick_client = zerorpc.Client(timeout=0.5) # quick client to test the service is live
        self.data_client = None # setup later to allow for changes to the 
        # self.client.debug = True
        self.client.connect(self.endpoint)
        self.quick_client.connect(self.endpoint)

        # self.server_running = self.quick_client.is_alive()

        # self.set_start_lightfield(True)
        self.acq_running = False
        self.param_tree = ParameterTree({
            "start_lightfield": (None, self.set_start_lightfield),
            "get_data": (None, self.get_frame),
            # "get_raw_data": (self.get_raw_frame, None),
            "server_live": (self.is_server_alive, None),
            "api_live": (self.is_lightfield_running, None),
            # "is_getting_data": (self.is_getting_data, None),
            "acquisition_running": (lambda: self.acq_running, self.set_acq_running),
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
            },
            "experiments":
            {
                "list_experiments": (self.get_experiments, None),
                "save_experiment": (None, self.save_experiment),
                "load_experiment": (None, self.load_experiment)
            }
        })
        # except (LostRemote, TimeoutExpired) as remote_err:
            # logging.error("Unable to connect to Server: %s", remote_err)
        self.rendered_graph = None
        logging.getLogger("zerorpc.channel").setLevel(logging.WARNING)




    @response_types('application/json', 'image/*', 'image/webp', default='application/json')
    def get(self, path, request):
        try:
            path_elems = re.split('[/?#]', path)
            if path_elems[0] == 'image':
                #return plot image
                if self.rendered_graph:
                    response = self.rendered_graph.getvalue()
                    content_type = 'image/png'
                    status = 200
                else:
                    response = {"response": "SpectrometerAdapter: No Graph Available"}
                    content_type = 'application/json'
                    status = 400
            else:
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

    def is_server_alive(self):
        try:
            return self.quick_client.is_alive()
        except (LostRemote, TimeoutExpired) as remote_err:
            # logging.error("Remote error in is_server_alive: %s", remote_err)
            return False

    def is_getting_data(self):
        try:
            self.throw_if_server_dead()
            return self.client.is_getting_data()
        except (LostRemote, TimeoutExpired) as remote_err:
            logging.error("Remote Error in is_getting_data: %s", remote_err)
            return False

    def set_acq_running(self, value):
        self.acq_running = value

    def throw_if_server_dead(self):
        if not self.is_server_alive():
            raise TimeoutExpired(0.1)

    def get_device_found(self):
        try:
            self.throw_if_server_dead()
            return self.client.device_found()
        except (LostRemote, TimeoutExpired) as remote_err:
            logging.error("Remote error in get_device_found: %s", remote_err)
            return False

    def set_start_lightfield(self, value):
        
        try:
            self.throw_if_server_dead()
            self.client.start_lightfield(value)
        except (LostRemote, TimeoutExpired) as remote_err:
            logging.error("Remote Error in set_start_lightfield: %s", remote_err)

    def is_lightfield_running(self):
        try:
            self.throw_if_server_dead()
            return self.client.is_lightfield_running()
        except (LostRemote, TimeoutExpired) as remote_err:
            logging.error("Remote Error trying to get Lightfield status: %s", remote_err)
    
    def start_get_raw_frame(self):
        try:
            self.throw_if_server_dead()
            if not self.data_client:
                self.data_client = zerorpc.Client(timeout=1 + (self.get_exposure() / 1000))
                self.data_client.connect(self.endpoint)
            self.data_client.start_acquire(1)
            # data = np.array(frame_data['data'])
            # data = data.reshape([frame_data['height'], frame_data['width']])
            # return data

        except (LostRemote, TimeoutExpired) as remote_err:
            logging.error("Error Trying to get Raw Frame: %s", remote_err)

    def get_frame(self, _=None):
        frame_data = self.data_client.get_frame()
        data = np.array(frame_data['data'])
        data = data.reshape([frame_data['height'], frame_data['width']])
        self.create_graph(data, frame_data['height'])
        return data

    # def get_data(self, frames=1):
    #     try:
    #         self.throw_if_server_dead()
    #         self.client.create_file(frames)
    #         logging.debug("CLIENT TIMEOUT: %d", self.get_exposure()/1000)
    #         self.data_client = zerorpc.Client(timeout=1 + (self.get_exposure() / 1000))
    #         self.data_client.connect(self.endpoint)
    #         IOLoop.current().add_callback(self.get_frame_from_spectrometer, frames)
    #     except (LostRemote, TimeoutExpired) as remote_err:
    #         logging.error("Remote Error trying to get Lightfield status: %s", remote_err)
        
    def create_graph(self, data, frame_height):
        fig, ax1 = plt.subplots()
        ax1.set_title("Spectrometer Data")

        if frame_height == 1:
            ax1.plot(data.reshape(-1))
            ax1.set_xlabel("Wavelength(nm)")
            ax1.set_ylabel("Intensity (Counts)")
        else:
            img = ax1.imshow(data)
            fig.colorbar(img)

        self.rendered_graph = io.BytesIO()
        fig.savefig(self.rendered_graph, format='png')
        self.rendered_graph.seek(0)

        plt.close(fig)

    # def get_frame_from_spectrometer(self, frames):
    #     logging.debug("Getting Frame : %d", frames)
    #     try:
    #         self.throw_if_server_dead()
    #         frame_data = self.data_client.start_acquire(1)
    #         data = np.array(frame_data['data'])
    #         data = data.reshape([frame_data['height'], frame_data['width']])
    #         logging.debug("Data shape: %s", data.shape)
    #         logging.debug("Data Type: %s", data.dtype)
    #         # plt.plot(data)

    #         fig, ax1 = plt.subplots()

    #         ax1.set_title("Science!")
    #         if frame_data['height'] == 1:
    #             ax1.plot(data.reshape(-1))
    #             ax1.set_xlabel("Wavelength (nm)")
    #             ax1.set_ylabel("Intensity (Counts)")
    #         else:
    #             img = ax1.imshow(data)
    #             fig.colorbar(img)
            
    #         self.rendered_graph = io.BytesIO()
    #         fig.savefig(self.rendered_graph, format='png')
    #         self.rendered_graph.seek(0)

    #     except (LostRemote, TimeoutExpired) as remote_err:
    #         logging.error("Remote Error in get_data: %s", remote_err)
    #     finally:
    #         if frames != 1:
    #             IOLoop.current().call_later(0.5, self.get_frame_from_spectrometer, frames - 1)

    def get_binning_mode(self):
      
        try:
            self.throw_if_server_dead()
            return self.client.get_region_of_interest()
        except (LostRemote, TimeoutExpired) as remote_err:
            logging.error("Remote Error trying to Get Binning Mode: %s", remote_err)

    def set_binning_mode(self, value):

        try:
            self.throw_if_server_dead()
            self.client.set_region_of_interest(value)
        except (LostRemote, TimeoutExpired) as remote_err:
            logging.error("Remote Error trying to Set Binning Mode: %s", remote_err)

    def get_row_bin_centre(self):
        
        try:
            self.throw_if_server_dead()
            return self.client.get_line_bin_row()
        except (LostRemote, TimeoutExpired) as remote_err:
            logging.error("Remote Error: %s", remote_err)

    def set_row_bin_centre(self, value):
    
        try:
            self.throw_if_server_dead()
            self.client.set_line_bin_row(value)
        except (LostRemote, TimeoutExpired) as remote_err:
            logging.error("Remote Error: %s", remote_err)

    def get_bin_width(self):
        try:
            self.throw_if_server_dead()
            return self.client.get_num_columns_binned()
        except (LostRemote, TimeoutExpired) as remote_err:
            logging.error("Remote Error: %s", remote_err)

    def set_bin_width(self, value):
        try:
            self.throw_if_server_dead()
            self.client.set_num_columns_binned(value)
        except (LostRemote, TimeoutExpired) as remote_err:
            logging.error("Remote Error: %s", remote_err)

    def get_bin_height(self):
        try:
            self.throw_if_server_dead()
            return self.client.get_num_rows_binned()
        except (LostRemote, TimeoutExpired) as remote_err:
            logging.error("Remote Error: %s", remote_err)

    def set_bin_height(self, value):
        try:
            self.throw_if_server_dead()
            self.client.set_num_rows_binned(value)
        except (LostRemote, TimeoutExpired) as remote_err:
            logging.error("Remote Error: %s", remote_err)

    def get_exposure(self):
        try:
            self.throw_if_server_dead()
            return self.client.get_camera_exposure()
        except (LostRemote, TimeoutExpired) as remote_err:
            logging.error("Remote Error: %s", remote_err)

    def set_exposure(self, value):
        try:
            self.throw_if_server_dead()
            self.client.set_camera_exposure(value)
        except (LostRemote, TimeoutExpired) as remote_err:
            logging.error("Remote Error: %s", remote_err)

    def get_centre_wavelength(self):
        try:
            self.throw_if_server_dead()
            return self.client.get_centre_wavelength()
        except (LostRemote, TimeoutExpired) as remote_err:
            logging.error("Remote Error: %s", remote_err)

    def set_centre_wavelength(self, value):
        try:
            self.throw_if_server_dead()
            self.client.set_centre_wavelength(value)
        except (LostRemote, TimeoutExpired) as remote_err:
            logging.error("Remote Error: %s", remote_err)

    def get_experiments(self):
        try:
            self.throw_if_server_dead()
            return self.client.get_experiments()
        except (LostRemote, TimeoutExpired) as remote_err:
            logging.error("Remote Error: %s", remote_err)

    def load_experiment(self, value):
        try:
            self.throw_if_server_dead()
            self.client.load_experiment(value)
        except (LostRemote, TimeoutExpired) as remote_err:
            logging.error("Remote Error: %s", remote_err)

    def save_experiment(self, value):
        try:
            self.throw_if_server_dead()
            self.client.save_experiment(value)
        except (LostRemote, TimeoutExpired) as remote_err:
            logging.error("Remote Error: %s", remote_err)