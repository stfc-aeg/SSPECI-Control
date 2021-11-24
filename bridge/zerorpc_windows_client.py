import zerorpc
import logging

import clr
import sys
import os
import psutil
# from System.IO import *

sys.path.append(os.environ['LIGHTFIELD_ROOT'])
sys.path.append(os.environ['LIGHTFIELD_ROOT']+"\\AddInViews")
clr.AddReference('PrincetonInstruments.LightFieldViewV5')
clr.AddReference('PrincetonInstruments.LightField.AutomationV5')
clr.AddReference('PrincetonInstruments.LightFieldAddInSupportServices')

from System import String
clr.AddReference('System.Collections')
from System.Collections.Generic import List

# PI imports
from PrincetonInstruments.LightField.Automation import Automation
from PrincetonInstruments.LightField.AddIns import SpectrometerSettings, ExperimentSettings, CameraSettings
from PrincetonInstruments.LightField.AddIns import DeviceType

LIGHTFIELD_PROCESS_NAME="AddInProcess.exe"

class baz:

    def __init__(self):
        print("INIT CALLED")

        self.set_text = ""
        self.lightfield_started = False
        self.experiment = None

        # self.start_lightfield(True)

    def do_addition(self, a, b):

        return a+b

    def give_string(self):
        return "Hello! Text is currently '{}'".format(self.set_text)

    def receive_string(self, input):
        logging.debug("SHOUTY DEBUG CAUSE WE GOT GIVEN A STRIIIING")
        self.set_text = input
        return "Thanks for sending {}".format(input)

    def _private_method(self):
        """
        Shouldn't be visible to the client hopefully?
        """
        pass

    def set_experiment_value(self, setting, value):
        if self.experiment.Exists(setting):
            self.experiment.SetValue(setting, value)

    def get_experiment_value(self, value):
        if self.experiment:
            val = self.experiment.GetValue(value)
        else:
            val = "Error: Lightfield Software not running"

        return val

    def device_found(self):
        # Find Connected Device
        if self.is_lightfield_started():
            for device in self.experiment.ExperimentDevices:
                if (device.Type == DeviceType.Camera):
                    return True
                
            # If connected device is not a camera inform the user
            logging.error("Camera not found. Please add a camera and try again.")
        else:
            logging.error("Lightfield software not running!")
        return False

    def start_lightfield(self, visible):
        logging.debug("STARTING LIGHTFIELD SOFTWARE")
        if self.is_lightfield_started():
            return
        self.auto = Automation(visible, List[String]())
        # Get experiment object
        logging.debug("GETTING EXPERIMENT OBJECT")
        self.experiment = self.auto.LightFieldApplication.Experiment
        self.lightfield_started = True

        # Attach methods to events driven by the automation API
        self.experiment.IsReadyToRunChanged += self._experiment_ready_to_run_changed_event
        self.auto.LightFieldClosing += self._lightfield_closing

    def is_lightfield_started(self):
        logging.debug("LOOKING FOR LIGHTFIELD")
        running_processes = [p.name() for p in psutil.process_iter()]
        is_running = LIGHTFIELD_PROCESS_NAME in running_processes
        if is_running:
            self.experiment = self.auto.LightFieldApplication.Experiment
        return is_running

    def get_spectrometer_info(self):
        logging.debug("GETTING SPECTROMETER INFO")

        return_vals = {
            "center_wavelength": self.experiment.GetValue(
                        SpectrometerSettings.GratingCenterWavelength
            ),
            "grating_selected": self.experiment.GetValue(
                        SpectrometerSettings.GratingSelected
            ),
            "grating_status": self.experiment.GetValue(
                        SpectrometerSettings.GratingStatus
            )
        }

        return return_vals
    
    def get_spec_center_wavelength(self):
        return self.get_experiment_value(
                SpectrometerSettings.GratingCenterWavelenth
        )

    def get_spec_grating_selected(self):
        return self.get_experiment_value(
                SpectrometerSettings.GratingSelected
        )

    def get_spec_grating_status(self):
        status = self.experiment.GetValue(
                SpectrometerSettings.GratingStatus
        )
        if status == 1:
            return "functional" 
        else: 
            return "faulted"

    def get_camera_exposure(self):
        return self.get_experiment_value(
            CameraSettings.ShutterTimingExposureTime
        )

    def set_camera_exposure(self, value):
        self.set_experiment_value(
            CameraSettings.ShutterTimingExposureTime,
            value
        )

    def _experiment_ready_to_run_changed_event(self, sender, event_args):
        if self.experiment.IsReadyToRun:
            logging.debug("Lightfield Ready to Run")
        else:
            logging.debug("Lightfield Not Ready to Run")

    def _lightfield_closing(self, sender, event_args):
        logging.debug("Lightfield Closing")
        self.experiment.IsReadyToRunChanged -= self._experiment_ready_to_run_changed_event
        self.auto.LightFieldClosing -= self._lightfield_closing


if __name__ == "__main__":

    logging.basicConfig(level=logging.DEBUG)
    server = zerorpc.Server(baz())
    print("BINDING SERVER")
    server.bind("tcp://0.0.0.0:4242")
    server.run()
    logging.debug("SERVER RUNNING")