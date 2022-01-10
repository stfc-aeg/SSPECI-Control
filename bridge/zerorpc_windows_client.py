import zerorpc
import logging

import clr
import sys
import os
import psutil
import threading
import signal
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
        signal.signal(signal.SIGINT, self._signal_hander)
    
    def _signal_hander(self, sig, frame):
        logging.debug("Ctrl+C pressed, closing gracefully")
        self.end_lightfield()
        sys.exit(0)

    def _set_experiment_value(self, setting, value):
        if self.experiment and self.experiment.Exists(setting):
            self.experiment.SetValue(setting, value)

    def _get_experiment_value(self, setting):
        if self.experiment and self.experiment.Exists(setting):
            val = self.experiment.GetValue(setting)
        else:
            val = "Error: Lightfield Software not running"

        return val

    def get_devices(self):
        return [device.Model for device in self.experiment.ExperimentDevices]

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
        # some sort of thread to start?
        if self.is_lightfield_started():
            return
        for process in psutil.process_iter():
            if process.name() in LIGHTFIELD_PROCESS_NAME:
                logging.debug("Exisiting process found, killing before starting new process")
                process.kill()

        # c# compatable list
        command_list = List[String]()

        # command line option for an empty experiment
        command_list.Add("/empty")

        self.auto = Automation(visible, List[String](command_list))
        # Get experiment object
        logging.debug("GETTING EXPERIMENT OBJECT")
        self.experiment = self.auto.LightFieldApplication.Experiment
        self.lightfield_started = True

        # Attach methods to events driven by the automation API
        self.experiment.IsReadyToRunChanged += self._experiment_ready_to_run_changed_event
        self.auto.LightFieldClosing += self._lightfield_closing

    def end_lightfield(self):
        # close the lightfield object?
        self.auto.Dispose()

    def is_lightfield_started(self):
        logging.debug("LOOKING FOR LIGHTFIELD")
        running = True if self.experiment else False
        return running

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
        self.experiment = None

    def save_experiment(self, experiment_name=None):
        if self.experiment:
            if experiment_name:
                self.experiment.SaveAs(experiment_name)
            else:
                self.experiment.Save()

    def load_experiment(self, experiment_name):
        if self.experiment:
            return self.experiment.Load(experiment_name)
        else:
            return False

    def get_experiments(self):
        if self.experiment:
            experiments = [x for x in self.experiment.GetSavedExperiments()]
            logging.debug(experiments)
        else:
            experiments  = []
        return experiments




if __name__ == "__main__":

    logging.basicConfig(level=logging.DEBUG)
    server = zerorpc.Server(baz())
    print("BINDING SERVER")
    server.bind("tcp://0.0.0.0:4242")
    server.run()
    logging.debug("SERVER RUNNING")