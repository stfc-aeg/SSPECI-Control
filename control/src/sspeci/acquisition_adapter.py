from enum import Enum
import os
import json
from re import T
from numpy import true_divide
from odin.adapters.adapter import (ApiAdapter, ApiAdapterRequest,
                                   ApiAdapterResponse, request_types, response_types)

from odin.adapters.parameter_tree import ParameterTree, ParameterTreeError
from odin.util import decode_request_body

import time
import logging
import h5py
from tornado.ioloop import PeriodicCallback, IOLoop

class acq_state(Enum):
    ERROR=-1
    READY=0
    WAIT_FRAME=1
    FRAME_READY=2
    WAIT_TEMP=3
    TEMP_READY=4
    WAIT_STABLE_RESET=5
    COMPLETE=6


class AcquisitionAdapter(ApiAdapter):
    # gunna use interadapter communication to control an aqusition
    # from this "central" adapter

    def __init__(self, **kwargs):
        super(AcquisitionAdapter, self).__init__(**kwargs)

        # self.acquisition_running = "no_run"
        self.acq_state = acq_state.READY
        
        self.reading_frame = False
        self.filename = "temp.hdf5"

        self.max_frames = 0
        self.num_frames = 0
        self.acq_frames = 0

        self.photo_lum_mode = False  # are we running in photo_lum_mode?

        self.temp_list_dir = self.options.get("temp_steps_dir", "temp_steps")

        if os.path.exists(self.temp_list_dir):
            self.temperature_files = os.listdir(self.temp_list_dir)

        if "test" in self.temperature_files:
            self.load_temp_list("test")
            
        else:
            self.list_temps = [280, 300, 320]  # TODO: DUMMY VALUES REMOVE BEFORE RELEASE
            self.selected_temp_file = "none"

        self.param_tree = ParameterTree({
            "start_acquisition": (None, self.start_acquisition),
            "stop_acquisition": (None, self.stop_acquisition),
            "state": (lambda: self.acq_state.name, None),
            "filename": (lambda: self.filename, self.set_file_name),
            "getting_data": (lambda: self.reading_frame, None),
            "max_frames": (lambda: self.max_frames, None),
            "current_frames": (lambda: self.num_frames, None),
            "photo_lum_mode": (lambda: self.photo_lum_mode, self.set_photo_mode),
            "photo_mode_temps_avail": (lambda: os.listdir(self.temp_list_dir), None),
            "temp_list_selected": (lambda: self.selected_temp_file, self.load_temp_list),
            "temp_list": (lambda: self.list_temps, None)
        })

        self.acquisition_loop = PeriodicCallback(self.acq_loop, 500) # 500 milliseconds too slow? unsure




    def initialize(self, adapters):
        """Initialize the adapter after it has been loaded.
        Receive a dictionary of all loaded adapters so that they may be accessed by this adapter.
        Remove itself from the dictionary so that it does not reference itself, as doing so
        could end with an endless recursive loop.
        """

        self.adapters = dict((k, v) for k, v in adapters.items() if v is not self)

        logging.debug("Received following dict of Adapters: %s", self.adapters)

    def get(self, path, request):
        try:
            response = self.param_tree.get(path)
            content_type = 'application/json'
            status = 200
        except ParameterTreeError as param_error:
            response = {'response': "Acquisition Adapter GET Error: %s".format(param_error)}
            content_type = 'application/json'
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
            response = {'response': 'Acquisition PUT error: {}'.format(param_error)}
            content_type = 'application/json'
            status = 400

        return ApiAdapterResponse(response, content_type=content_type, status_code=status)

    def set_temp_list(self, temp_list):
        self.list_temps = temp_list

    def load_temp_list(self, filename):
        try:
            with open(os.path.join(self.temp_list_dir, filename)) as file:
                self.list_temps = [int(line) for line in file]
            self.selected_temp_file = filename
        except FileNotFoundError:
            logging.error("File %s does not exist", filename)


    def set_file_name(self, filename):
        self.filename = filename

    def set_photo_mode(self, is_photo_mode):
        self.photo_lum_mode = is_photo_mode

    def acq_loop(self):
        if self.acq_state == acq_state.WAIT_FRAME:
            # waiting for frame to complete before we get data
            self.wait_for_frame()
        elif self.acq_state == acq_state.FRAME_READY:
            # frame exposure complete, data ready to be read
            self.get_data()
        elif self.acq_state == acq_state.WAIT_TEMP:
            # waiting to get to a specific temperature, for photoluninecense mode
            self.wait_for_temperature()
        elif self.acq_state == acq_state.TEMP_READY:
            # reached stable temperature, ready to start data collection
            self.start_frame_get()
        elif self.acq_state == acq_state.READY:
            if self.num_frames < self.max_frames:
                logging.debug("MORE FRAMES TO GET")
                self.start_frame_get()
            elif self.photo_lum_mode and self.list_temps:
                    # photo mode, and we have more temps to do. Repeat temp setup for next round
                self.num_frames = 0
                self.set_temp(self.list_temps.pop(0))
            else:
                self.acq_state = acq_state.COMPLETE
        elif self.acq_state == acq_state.WAIT_STABLE_RESET:
            self.wait_for_stable_reset()
        elif self.acq_state == acq_state.COMPLETE:
            self.stop_acquisition()
            self.acquisition_loop.stop()
        else:
            logging.error("Something gone wrong with the acquisiton")
            return

    def wait_for_frame(self):
        # called when acq_state == WAIT_FRAME
        reading_frame = self.adapters['spectrometer'].client.is_getting_data()
        if not reading_frame:
            self.acq_state = acq_state.FRAME_READY

    def wait_for_temperature(self):
        # called when acq_state == WAIT_TEMP
        is_stable = self.adapters['cryostat'].get("atsm/is_stable", ApiAdapterRequest(None)).data["is_stable"]
        if is_stable:
            self.acq_state = acq_state.TEMP_READY
    
    def wait_for_stable_reset(self):
        is_stable = self.adapters['cryostat'].get("atsm/is_stable", ApiAdapterRequest(None)).data["is_stable"]
        if not is_stable:
            self.acq_state = acq_state.WAIT_TEMP

    def set_temp(self, temp):
        
        request = ApiAdapterRequest({"target_temp": temp})
        self.adapters['cryostat'].put("atsm", request)
        self.acq_state = acq_state.WAIT_STABLE_RESET

    def get_data(self):
        # called when acq_state == FRAME_READY
        try:
            data = self.adapters['spectrometer'].get_frame()
        except AttributeError as err:
            # if finished, it means the Stop Acq button was pressed and cut the acq short.
            # this is fine and expected behaviour. If not finished, then something else went wrong
            if self.acquisition_running != "finished":
                raise err
                
        if data is not None:
            request = ApiAdapterRequest(None)
            end_temp = self.adapters['cryostat'].get("atsm/temperature", request).data['temperature']

            self.dset_data.resize((self.acq_frames+1, data.shape[0], data.shape[1]))
            self.dset_temp_end.resize(self.acq_frames+1, axis=0)

            self.dset_temp_end[self.acq_frames:] = end_temp
            self.dset_data[self.acq_frames:] = data

            self.num_frames = self.num_frames + 1
            self.acq_frames = self.acq_frames + 1

            # if self.num_frames < self.max_frames:
            #     self.start_frame_get()
            # else:
        self.acq_state = acq_state.READY
                
    def start_acquisition(self, num_frames):
        # this method should start the warmup in the cryostat, and then start the loop for getting
        # frames of data
        file_created = self.create_file(self.filename, 1, 1)
        if not file_created:
            return
        self.acquisition_running = "running"
        #reset frame count
        self.num_frames = 0
        self.acq_frames = 0
        self.max_frames = num_frames

        # check cryostat is cooled and low enough pressure?
        # trigger cryostat warmup
        if self.photo_lum_mode:
            data = {"auto_control_enabled": True}
            request = ApiAdapterRequest(data)
            self.adapters['cryostat'].put("atsm", request)
        else:
            data = {"warmup": True}
            request = ApiAdapterRequest(data)
            self.adapters['cryostat'].put("", request)
        request = ApiAdapterRequest({"acquisition_running": True})
        self.adapters['spectrometer'].put("", request) # set running flag for UI
        # IOLoop.current().call_later(0.1, self.start_frame_get)
        # self.acq_state = acq_state.READY
        if self.photo_lum_mode:
            self.set_temp(self.list_temps.pop(0))
            self.acq_state = acq_state.WAIT_TEMP
        else:
            self.acq_state = acq_state.READY
        self.acquisition_loop.start()


    def create_file(self, filename, width, height):
        try:
            # filemode 'x' means create file, fail if it already exists
            self.file = h5py.File(filename, 'x')
            # dt = h5py.string_dtype(encoding='utf-8')
            self.dset_time = self.file.create_dataset('timestamps', (1,), maxshape=(None,))
            self.dset_data = self.file.create_dataset('data', (1, width, height), maxshape=(None, None, None))
            self.dset_temp_start = self.file.create_dataset('temp_start', (1,), maxshape=(None,))
            self.dset_temp_end = self.file.create_dataset('temp_end', (1,), maxshape=(None,))

            request = ApiAdapterRequest(None)
            spec_tree = self.adapters['spectrometer'].get("", request).data
            logging.debug("Create file spec_tree: %s", spec_tree)
            
            self.dset_data.attrs.create("exposure", spec_tree['acquisition']['exposure'])
            self.dset_data.attrs.create("centre_wavelength", spec_tree['acquisition']['centre_wavelength'])
            self.dset_data.attrs.create("bin_mode", spec_tree['binning']['binning_mode'])

            self.dset_time.attrs.create("start_time", time.asctime())

            # self.dset_data.attrs.create("")


            return True
        except (BlockingIOError, FileExistsError) as err:
            logging.error("Error Creating Hdf5 File %s: %s", filename, err)
            self.acq_state = acq_state.ERROR
            return False

        # add temperature ramp table, spectrometer settings as metadata?

    def stop_acquisition(self, _=None):
        # this method should stop the acquisition loop, and ensure all collected data + metadata is
        # create hdf file for acquisition saving
        # saved to a hdf file
        logging.debug("Acquisition Completed. Saved %d frames of data", self.acq_frames)
        self.dset_time.attrs.create("end_time", time.asctime())
        self.file.close()
        self.adapters['spectrometer'].data_client.close()
        self.adapters['spectrometer'].data_client = None

        if self.photo_lum_mode:
            data = {"auto_control_enabled": False}
            request = ApiAdapterRequest(data)
            self.adapters['cryostat'].put("atsm", request)
        else:
            data = {"abort": True}
            request = ApiAdapterRequest(data)
            self.adapters['cryostat'].put("", request)

        request = ApiAdapterRequest({"acquisition_running": False}, content_type="application/json")
        self.adapters['spectrometer'].put("", request)
        self.acq_state = acq_state.COMPLETE
        self.acquisition_loop.stop()

    def is_acquisition_running(self):
        return self.acquisition_running

    def start_frame_get(self):

        # some sort of looping method to get data from spectrometer and cryostat, timestamp, add to hdf

        #get data and other parts from system

        request = ApiAdapterRequest(None)
        timestamp = int(time.time())
        logging.debug("Timestamp: %d", timestamp)
        start_temp = self.adapters['cryostat'].get("atsm/temperature", request).data['temperature']
        logging.debug("START TEMP: %d", start_temp)

        # resize datasets for new data
        self.dset_time.resize(self.acq_frames+1, axis=0)
        self.dset_temp_start.resize(self.acq_frames+1, axis=0)
        
        #append new data
        self.dset_time[self.acq_frames:] = timestamp
        self.dset_temp_start[self.acq_frames:] = start_temp

        self.adapters['spectrometer'].start_get_raw_frame()
        self.reading_frame = True
        self.acq_state = acq_state.WAIT_FRAME
    
    # def get_data_loop(self):
        
    #     if self.reading_frame:
    #         # bypassing get method again. Might not be best idea
    #         self.reading_frame = self.adapters['spectrometer'].client.is_getting_data()
    #         IOLoop.current().call_later(0.1, self.get_data_loop)

    #     else:
    #         # frame read from spectrometer completed, get data
    #         try:
    #             data = self.adapters['spectrometer'].get_frame()
    #         except AttributeError as err:
    #             # if finished, it means the Stop Acq button was pressed and cut the acq short.
    #             # this is fine and expected behaviour. If not finished, then something else went wrong
    #             if self.acquisition_running != "finished":
    #                 raise err
                    
    #         if data is not None:
    #             request = ApiAdapterRequest(None)
    #             end_temp = self.adapters['cryostat'].get("atsm/temperature", request).data['temperature']

    #             self.dset_data.resize((self.dset_data.len()+1, data.shape[0], data.shape[1]))
    #             self.dset_temp_end.resize(self.dset_data.len()+1, axis=0)

    #             self.dset_temp_end[self.dset_data.len():] = end_temp
    #             self.dset_data[self.dset_data.len():] = data

    #             self.num_frames = self.num_frames + 1

    #             if self.num_frames < self.max_frames and self.acquisition_running == "running":
    #                 IOLoop.current().call_later(0.1, self.run_acquisition_loop)
    #             else:
    #                 self.stop_acquisition()

    #         else:
    #             IOLoop.current().call_later(0.1, self.get_data_loop)
