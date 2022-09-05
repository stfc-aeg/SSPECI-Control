from pickle import FALSE
from typing import ByteString
from numpy.core.fromnumeric import shape
from numpy.core.multiarray import array
import zerorpc
import logging

import clr
import sys
import os
import psutil
import threading
import signal
import time
import argparse
# import numpy as np
from array import array
# from System.IO import *

sys.path.append(os.environ['LIGHTFIELD_ROOT'])
sys.path.append(os.environ['LIGHTFIELD_ROOT']+"\\AddInViews")
clr.AddReference('PrincetonInstruments.LightFieldViewV5')
clr.AddReference('PrincetonInstruments.LightField.AutomationV5')
clr.AddReference('PrincetonInstruments.LightFieldAddInSupportServices')

from System import String, Array
from System.Runtime.Remoting import RemotingException
clr.AddReference('System.Collections')
from System.Collections.Generic import List

# PI imports
from PrincetonInstruments.LightField.Automation import Automation
from PrincetonInstruments.LightField.AddIns import SpectrometerSettings, ExperimentSettings, CameraSettings
from PrincetonInstruments.LightField.AddIns import DeviceType, ImageDataFormat




class APIController:

    # background process name(s) if needed to cleanup
    LIGHTFIELD_PROCESS_NAME = ["AddInProcess.exe"]


    
    def __init__(self):
        logging.debug("HEY WERE USING THE THREAD FOR DATA COLLECTION NOW")

        self.application = None
        self.experiment = None
        self.file_handler = None

        self.export_settings = None

        # flags
        self.lightfield_running = False
        self.experiment_running = False
        self.ready_to_run = False
        self.getting_data = False

        self.current_working_file = None
        self.working_file_frame_num = 0

    def start_lightfield(self, visible):
        logging.info("Starting Lightfield Software")
        if self.lightfield_running:
            logging.debug("Lightfield Already Running")
            return
        
        for process in psutil.process_iter():
            if process.name() in self.LIGHTFIELD_PROCESS_NAME:
                logging.debug("Lingering Process found, ending before starting new process")
                process.kill()
        
        self._start_in_thread(visible)
        # t = threading.Thread(target=self._start_in_thread, args=[visible])
        # t.start()
        logging.debug("Lightfield starting in thread")

    def _start_in_thread(self, visible):
        logging.debug("Starting Lightfield Application")
        # c# compatable list for command-line arguments
        command_list = List[String]()
        # ensures it does not automatically load an experiment
        command_list.Add("/empty")
        logging.debug("STARTING AUTOMATION")
        self.application = Automation(visible, List[String]())
        logging.debug("Lightfield Started")

        self.experiment = self.application.LightFieldApplication.Experiment
        self.file_handler = self.application.LightFieldApplication.FileManager

        logging.debug("Adding Event Listeners")

        self.experiment.IsReadyToRunChanged += self.event_experiment_ready_to_run
        self.experiment.ExperimentStarted += self.event_experiment_started
        self.experiment.ExperimentCompleted += self.event_experiment_completed

        self.experiment.ExperimentUpdating += self.event_experiment_updating
        self.experiment.ExperimentUpdated += self.event_experiment_updated

        self.application.LightFieldClosing += self.event_lightfield_closing

        logging.debug("Setting Running Flag")
        self.lightfield_running = True

        logging.debug("Thread Terminated")


    def close_lightfield(self):
        logging.info("Closing Lightfield Application")
        if self.application:
            self.application.Dispose()
            self.application = None
    
    def get_experiment_value(self, setting):
        if self.lightfield_running and self.experiment.Exists(setting):
            logging.debug(setting)
            val = self.experiment.GetValue(setting)
        else:
            logging.debug("Cannot get %s: Either Lightfield is not running, or that setting does not exist", setting)
            val = None
        return val

    def set_experiment_value(self, setting, value):
        if self.lightfield_running and self.experiment.Exists(setting):
            self.experiment.SetValue(setting, value)
        else:
            logging.debug("Cannot set %s: Either Lightfield is not running, or that setting does not exist", setting)

    def save_experiment(self, experiment_name=None):
        if self.lightfield_running:
            logging.debug("Saving Experiment")
            if experiment_name:
                self.experiment.SaveAs(experiment_name)
            else:
                self.experiment.Save()

    def load_experiment(self, experiment_name):
        if self.lightfield_running:
            return self.experiment.Load(experiment_name)
        else:
            return False

    def get_experiments(self):
        if self.lightfield_running:
            # have to turn it into a pythin list, instead of a C style list
            return [x for x in self.experiment.GetSavedExperiments()]
        else:
            return []

    def check_ready_for_acquire(self):
        # check to see if experiment is available, ready to run, and not already running
        ready_to_run = self.lightfield_running and \
                       self.experiment.IsReadyToRun and \
                       not self.experiment.IsRunning

        return ready_to_run

    def acquire_data(self, num_frames=0):
        # modify to get data via thread so it does not block down the line
        if self.check_ready_for_acquire():
            
            logging.debug("Beginning acquisition of %d frames", num_frames)
            data_thread = threading.Thread(target=self._thread_get_frame)
            self.getting_data = True
            data_thread.start()
            
            # data = self.experiment.Capture(num_frames) # returns IImageDataSetContractToViewHostAdapter?
            # extracted_data = self.get_file_data(data)
            # return extracted_data

    def _thread_get_frame(self):
        logging.info("Data Collection thread started")
        data = self.experiment.Capture(1)
        self.data = self.get_file_data(data)
        self.getting_data = False
        logging.info("Data acquired, stopping thread")

    def is_getting_data(self):
        return self.getting_data

    def get_frame(self):
        if not self.getting_data:
            return self.data
        else:
            return None

    def preview(self):
        if self.check_ready_for_acquire():
            self.experiment.Preview()
        

    def stop_acquire(self):
        if self.lightfield_running:
            self.experiment.Stop()

    # file Handling Methods

    def create_acquisition_file(self, num_frames):
        if self.lightfield_running:
            logging.debug("Creating Temp File for acquisition Saving")
            if self.current_working_file:
                try:
                    self.file_handler.CloseFile(self.current_working_file)
                except RemotingException as err:
                    pass
            self.current_working_file = self.file_handler.CreateFile("temp.spe", self.experiment.SelectedRegions, num_frames, ImageDataFormat.MonochromeUnsigned16)
            self.working_file_frame_num = 0

    def get_recent_files(self):
        if self.lightfield_running:
            return [x for x in self.file_handler.GetRecentlyAcquiredFileNames()]

    def open_file(self, file_name):
        if self.lightfield_running:
            file = self.file_handler.OpenFile(file_name, 1) # 1 = fileAccess: Read
            # file is class based on the IImageDataSet from pg 53 of the programming manual
            data = self.get_file_data(file)
            return data

    def get_file_data(self, file):
         # just getting first frame for now, TODO: option to select frame?
        image_data = file.GetFrame(0,0)
        # metadata = file.GetFrameMetadata(0)
        data_format = image_data.Format # some sort of enum value for the data format
        img_height = image_data.Height
        img_width = image_data.Width

        logging.debug("Returning image of dimensions: (%d, %d)", img_width, img_height)

        raw_data = image_data.GetData()  # returns a System.Array, which does not seem to iterate in a way numpy likes
        
        if self.current_working_file: # add data to current working file, so the total acquisiton data can be saved
            logging.debug(self.current_working_file)
            frame = self.current_working_file.GetFrame(0, self.working_file_frame_num)
            frame.SetData(raw_data)
            self.working_file_frame_num += 1

        # data = array('I')
        data = list(raw_data)
        # data.extend(raw_data)
        # create some sort of struct to hold data + info about data?
        logging.debug("Num Data Points: %d", len(data))
        # data = np.fromiter(raw_data, np.uint16)
        # data = data.reshape((img_height, img_width))  # should be shaped the same as the orignal image
        return {
            "data": data,
            "height": img_height,
            "width": img_width,
            "dtype": data_format,
            # "metadata": metadata
        }
        # return raw_data

    def save_current_file(self, file_name):
        if self.lightfield_running:
            self.file_handler.SaveFile(self.current_working_file, file_name)

    def create_export_settings(self, file_type):
        if self.lightfield_running:
            self.export_settings = self.file_handler.CreateExportSettings(file_type)

    def export_file(self, file_name):
        if self.lightfield_running:
            self.file_handler.Export(self.export_settings, file_name)

    def get_system_column_calibration(self):
        if self.lightfield_running:
            return self.experiment.SystemColumnCalibration

    # event handlers (not all will be needed maybe?)

    def event_experiment_started(self, sender, event_args):
        logging.debug("Experiment Started")
        self.experiment_running = True

    def event_experiment_completed(self, sender, event_args):
        logging.debug("Experiment Completed")
        self.experiment_running = False

    def event_experiment_updating(self, sender, event_args):
        logging.debug("Experiment Updating")

    def event_experiment_updated(self, sender, event_args):
        logging.debug("Experiment Updated")

    def event_experiment_ready_to_run(self, sender, event_args):
        logging.debug("Experiment Ready To Run Changed: %s", self.experiment.IsReadyToRun)

    def event_available_device_changed(self, sender, event_args):
        logging.debug("Experiment Available Devices Changed")

    def event_lightfield_closing(self, sender, event_args):
        logging.debug("Lightfield Closing")
        logging.debug("Removing Event Handlers")
        self.experiment.IsReadyToRunChanged -= self.event_experiment_ready_to_run
        self.experiment.ExperimentStarted -= self.event_experiment_started
        self.experiment.ExperimentCompleted -= self.event_experiment_completed

        self.experiment.ExperimentUpdating -= self.event_experiment_updating
        self.experiment.ExperimentUpdated -= self.event_experiment_updated

        self.application.LightFieldClosing -= self.event_lightfield_closing
        
        # self.close_lightfield()

        self.experiment = None
        self.file_handler = None
        # self.application = None

        self.lightfield_running = False

    def is_lightfield_running(self):
        return self.lightfield_running
    

class RPCServer:

    def __init__(self):
        self.api = APIController()

        # handle ctrl-c closing properly
        # signal.signal(signal.SIGINT, self._signal_handler)

    # def _signal_handler(self, sig, frame):
    #     logging.debug("Shutting Down")
    #     self.api.close_lightfield()
    #     sys.exit(0)

    def __del__(self):
        self.api.close_lightfield()

    def close_server(self):
        self.api.close_lightfield()

    def start_lightfield(self, visible):
        """ 
        Start the Lightfield Software
        Arguments:
        visible -- whether the software UI should be visible or not
        """
        self.api.start_lightfield(visible)

    def is_lightfield_running(self):
        return self.api.is_lightfield_running()

    def get_camera_exposure(self):
        """Get the current exposure of the camera"""
        return self.api.get_experiment_value(
            CameraSettings.ShutterTimingExposureTime
        )
    
    def set_camera_exposure(self, value):
        """Set the current exposure of the camera"""
        return self.api.set_experiment_value(
            CameraSettings.ShutterTimingExposureTime,
            value
        )

    def get_grating(self):
        """Get the currently selected grating"""
        return self.api.get_experiment_value(
            SpectrometerSettings.GratingSelected
        )

    def get_centre_wavelength(self):
        """Get the Centre Wavelength of the current grating, in nm"""
        return self.api.get_experiment_value(
            SpectrometerSettings.GratingCenterWavelength
        )

    def set_centre_wavelength(self, value):
        """Set the Centre Wavelength of the current grating, in nm"""
        return self.api.set_experiment_value(
            SpectrometerSettings.GratingCenterWavelength,
            value
        )

    def get_calibration_x_axis(self):
        """Get the X Axis Calibration of the grating"""
        return self.api.get_experiment_value(
            ExperimentSettings.AcquisitionCalibrationsXAxes
        )

    def get_region_of_interest(self):
        """Get the currently selected form of binning and/or the region of interest selected"""
        region_enum = ["FullSensor", "BinnedSensor", "LineSensor", "CustomRegions"]
        region = self.api.get_experiment_value(
            CameraSettings.ReadoutControlRegionsOfInterestSelection
        )
        if region:
            return region_enum[region-1] # -1 cause the enum starts at 1, but the list is 0 indexed
        else:
            return None

    def set_region_of_interest(self, value):
        """Set the method of binning"""
        region_enum = ["FullSensor", "BinnedSensor", "LineSensor", "CustomRegions"]
        if value in region_enum:
            value_num = region_enum.index(value)

            self.api.set_experiment_value(
                CameraSettings.ReadoutControlRegionsOfInterestSelection,
                value_num + 1
            )
        else:
            logging.error("Error in setting region of interest: %s not a region type", value)
            logging.error("Available types are: %s", region_enum)

    def get_num_columns_binned(self):
        """Get the number of columns set to bin together, if the method of binning is 'BinnedSensor'"""
        return self.api.get_experiment_value(
            CameraSettings.ReadoutControlRegionsOfInterestBinnedSensorXBinning
        )

    def set_num_columns_binned(self, value):
        """Set the number of columns to bin together, if the method of binning is 'BinnedSensor'"""
        self.api.set_experiment_value(
            CameraSettings.ReadoutControlRegionsOfInterestBinnedSensorXBinning,
            value
        )

    def get_num_rows_binned(self):
        """Get the number of rows set to bin together, if the method of binning is 'BinnedSensor'"""
        return self.api.get_experiment_value(
            CameraSettings.ReadoutControlRegionsOfInterestBinnedSensorYBinning
        )

    def set_num_rows_binned(self, value):
        """Set the number of rows to bin together, if the method of binning is 'BinnedSensor'"""
        self.api.set_experiment_value(
            CameraSettings.ReadoutControlRegionsOfInterestBinnedSensorYBinning,
            value
        )

    def get_line_bin_row(self):
        """Get the row of the sensor to readout, if the binning method is 'LineSensor'"""
        return self.api.get_experiment_value(
            CameraSettings.ReadoutControlRegionsOfInterestLineSensorRowBinning
        )

    def set_line_bin_row(self, value):
        """Set the row of the sensor to readout, if the binning method is 'LineSensor'"""
        self.api.set_experiment_value(
            CameraSettings.ReadoutControlRegionsOfInterestLineSensorRowBinning,
            value
        )

    # calibration info

    def get_calibration_x_axis(self):
        return self.api.get_experiment_value(
            ExperimentSettings.AcquisitionCalibrationsXAxes
        )

    def get_system_column_calibration(self):
        return self.api.get_system_column_calibration()

    def start_acquire(self, num_frames=0):
        """Start the acquisition. if num_frames is set above 0, this will return the data.
        Otherwise, this will save the data into a local file, with a number of frames set by the
        experiment value. Be aware, this method currently blocks until the acquisition is completed"""
        self.api.acquire_data(num_frames)
        # return data

    def stop_acquire(self):
        self.api.stop_acquire()

    def preview(self):
        self.api.preview()

    def save_file(self, file_name):
        self.api.save_current_file(file_name)

    def create_file(self, num_frames):
        self.api.create_acquisition_file(num_frames)
        return self.api.current_working_file.FilePath

    def get_files(self):
        return self.api.get_recent_files()

    def open_file(self, file_name):
        return self.api.open_file(file_name)

    def get_experiments(self):
        return self.api.get_experiments()

    def load_experiment(self, experiment_name):
        return self.api.load_experiment(experiment_name)

    def save_experiment(self, experiment_name=None):
        return self.api.save_experiment(experiment_name)

    def is_alive(self):
        return True  # tells the client that this service is running

    def is_getting_data(self):
        return self.api.is_getting_data()

    def get_frame(self):
        return self.api.get_frame()

if __name__ == "__main__":

    logging.basicConfig(level=logging.DEBUG)
    parser = argparse.ArgumentParser()
    parser.add_argument("--addr", default="192.168.0.102", help="Enter the RPC server IP address")
    parser.add_argument("--port", default="4242", help="Enter the RPC Server Port")
    args = parser.parse_args()

    server_addr_string = "tcp://{addr}:{port}".format(addr=args.addr, port=args.port)
    logging.debug(server_addr_string)
    server = zerorpc.Server(RPCServer())

    server.bind(server_addr_string)
    server.run()

else:
    logging.basicConfig(
        filename="c:\\Temp\\sspeci-service.log",
        filemode='w',
        level=logging.INFO,
        datefmt='%H:%M:%S',
        format='%(asctime)s %(levelname)-8s %(message)s'
    )