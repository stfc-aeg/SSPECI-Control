import enum
import logging

import ctypes, os, time
import platform
import json

from odin.adapters.adapter import (ApiAdapter, ApiAdapterRequest,
                                   ApiAdapterResponse, request_types, response_types)
from odin.adapters.parameter_tree import ParameterTree, ParameterTreeError
from odin.util import decode_request_body

from tornado.ioloop import PeriodicCallback

logging.basicConfig(level=logging.DEBUG)

class StageAdapter(ApiAdapter):

    def __init__(self, **kwargs):
        super(StageAdapter, self).__init__(**kwargs)
        # because there doesn't appear to be a way to read the target info from the stages, we need
        # to set the defaults when we start so that the values are the same in the adapter as they
        # are in the actual attocube
        default_targets = self.options.get("targets", [0.0, 0.0, 0.0])
        default_tgt_range = self.options.get("target_ranges", [1e-6, 1e-6, 1e-6])
        
        self.saved_position_directory = self.options.get("position_dir", "positions")
        library_addr = self.options.get("library", "anc/libanc350v4.so")

        self.controller = StageController(library_addr)

        for i, target in enumerate(default_targets):
            self.controller.setTargetPosition(i, target)

        for i, range in enumerate(default_tgt_range):
            self.controller.setTargetRange(i, range)

        self.param_tree = ParameterTree({
            "is_connected": (None, None),
            "axis_0": self.create_axis_tree(0),
            "axis_1": self.create_axis_tree(1),
            "axis_2": self.create_axis_tree(2),
            "load_position": (None, self.load_position),
            "save_position": (None, self.save_position)
            
        })



    def create_axis_tree(self, axis_num):
        tree = {
            "axis_name": (lambda: self.controller.names[axis_num], None),
            "type": (lambda: self.controller.types[axis_num], None),
            "position": (lambda: self.controller.positions[axis_num], None),
            "connected": (lambda: self.controller.statuses[axis_num].get("connected", False), None),
            "enabled": (lambda: self.controller.statuses[axis_num].get("enabled", False), lambda en: self.controller.setAxisOutput(axis_num, en, 0)),
            "moving": (lambda: self.controller.statuses[axis_num].get("moving", False), None),
            "at_target":(lambda: self.controller.statuses[axis_num].get("target_reached", False), None),
            "end_of_travel":{
                "forward": (lambda: self.controller.statuses[axis_num].get("EoTF"), None),
                "backward": (lambda: self.controller.statuses[axis_num].get("EoTB"), None),
            },
            "target_pos": (lambda: self.controller.target_pos[axis_num], lambda pos: self.controller.setTargetPosition(axis_num, pos)),
            "target_range": (lambda: self.controller.target_range[axis_num], lambda range: self.controller.setTargetRange(axis_num, range)),
            "single_step": {
                "forward": (None, lambda val: self.controller.startSingleStep(axis_num, 0)),
                "backward": (None, lambda val: self.controller.startSingleStep(axis_num, 1))
            },
            "auto_move": (None, lambda enable:self.controller.startAutoMove(axis_num, enable, 0)),
            # "voltage": (lambda: self.controller.voltage[axis_num], None),
            "amplitude": (self.controller.getAmplitude(axis_num), None),
            "frequency": (self.controller.getFrequency(axis_num), None)
        }
        return tree

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
            response = {'response': 'Cryostat PUT error: {}'.format(param_error)}
            content_type = 'application/json'
            status = 400

        return ApiAdapterResponse(response, content_type=content_type, status_code=status)

    def __del__(self):
        logging.debug("Disconnect from adapter")
        self.controller.disconnect()

    def load_position(self, position_file):
        try:
            with open(os.path.join(self.saved_position_directory, position_file)) as file:
                file_dict = json.load(file)
                position_dict = file_dict.get("position", None)
                if position_dict:
                    for (axis, position) in position_dict.items():
                        self.controller.setTargetPosition(int(axis), position)
                range_dict = file_dict.get("range", None)
                if range_dict:
                    for (axis, range) in range_dict.items():
                        self.controller.setTargetRange(int(axis), range)

        except FileNotFoundError:
            logging.error("Position file %s does not exist", position_file)

    def save_position(self, position_file):
        try:
            with open(os.path.join(self.saved_position_directory, position_file), "w+") as file:
                data_dict = {
                    "position": {axis: target_pos for axis, target_pos in enumerate(self.controller.target_pos)},
                    "range": {axis: target_range for axis, target_range in enumerate(self.controller.target_range)}
                }
                json.dump(data_dict, file)
                # file.write(json_dict)
        except FileNotFoundError:
            logging.error("Position File %s cannot be saved: Directory may not exist")



class AttocubeException(Exception):
        pass

class StageController:

    def __init__(self, lib_addr):
        logging.debug("Stage Controller INIT")
        self.ANC = ctypes.CDLL(lib_addr)
        logging.debug("SHARED OBJECT LOADED")

        self.discover()
        self.device = self.connect()

        self.positions = [0,0,0]
        self.statuses = [{}, {}, {}]
        self.target_pos = [0.0,0.0,0.0]
        self.target_range = [0.0, 0.0, 0.0]
        self.voltage = [0.0, 0.0, 0.0]

        self.names = [self.getActuatorName(0), self.getActuatorName(1), self.getActuatorName(2)]
        self.types = [self.getActuatorType(0), self.getActuatorType(1), self.getActuatorType(2)]

        prop_loop = PeriodicCallback(self.get_all_properties, 500)
        prop_loop.start()

    def get_all_properties(self):
        # logging.debug("Loop")
        self.positions = [self.getPosition(0), self.getPosition(1), self.getPosition(2)]
        self.statuses = [self.getAxisStatus(0), self.getAxisStatus(1), self.getAxisStatus(2)]
        # self.voltage = [self.getDcVoltage(0), self.getDcVoltage(1), self.getDcVoltage(2)]
        
    def configureAQuadBIn(self, axisNo, enable, resolution):
        '''
        Enables and configures the A-Quad-B (quadrature) input for the target position.
        Parameters
            axisNo	Axis number (0 ... 2)
            enable	Enable (1) or disable (0) A-Quad-B input
            resolution	A-Quad-B step width in m. Internal resolution is 1 nm.
        Returns
            None
        '''
        code = getattr(self.ANC, "ANC_configureAQuadBIn")(self.device, axisNo, enable, ctypes.c_double(resolution))
        self.checkErrorCode(code)
        
        
    def configureAQuadBOut(self, axisNo, enable, resolution, clock):
        '''
        Enables and configures the A-Quad-B output of the current position.
        Parameters
            axisNo	Axis number (0 ... 2)
            enable	Enable (1) or disable (0) A-Quad-B output
            resolution	A-Quad-B step width in m; internal resolution is 1 nm
            clock	Clock of the A-Quad-B output [s]. Allowed range is 40ns ... 1.3ms; internal resulution is 20ns.
        Returns/
            None
        '''
        code = getattr(self.ANC, "ANC_configureAQuadBOut")(self.device, axisNo, enable, ctypes.c_double(resolution), ctypes.c_double(clock))
        self.checkErrorCode(code)

    def connect(self, devNo=0):
        '''
        Initializes and connects the selected device. This has to be done before any access to control variables or measured data.
        Parameters
            devNo	Sequence number of the device. Must be smaller than the devCount from the last ANC_discover call. Default: 0
        Returns
            device	Handle to the opened device, NULL on error
        '''
        device = ctypes.c_void_p()
        code = getattr(self.ANC, "ANC_connect")(devNo, ctypes.byref(device))
        self.checkErrorCode(code)
        return device
        
        
    def disconnect(self):
        '''
        Closes the connection to the device. The device handle becomes invalid.
        Parameters
            None
        Returns
            None
        '''
        code = getattr(self.ANC, "ANC_disconnect")(self.device)
        self.checkErrorCode(code)
       
    
    def discover(self, ifaces=3):
        '''
        The function searches for connected ANC350RES devices on USB and LAN and initializes internal data structures per device. Devices that are in use by another application or PC are not found. The function must be called before connecting to a device and must not be called as long as any devices are connected.
        The number of devices found is returned. In subsequent functions, devices are identified by a sequence number that must be less than the number returned.
        Parameters
            ifaces	Interfaces where devices are to be searched. {None: 0, USB: 1, ethernet: 2, all:3} Default: 3
        Returns
            devCount	number of devices found
        '''
        devCount = ctypes.c_int()
        code = getattr(self.ANC, "ANC_discover")(ifaces, ctypes.byref(devCount))
        self.checkErrorCode(code)
        return devCount.value
    
    
    def getActuatorName(self, axisNo):
        '''
        Get the name of the currently selected actuator
        Parameters
            axisNo	Axis number (0 ... 2)
        Returns
            name	Name of the actuator
        '''
        name = ctypes.create_string_buffer(20)
        code = getattr(self.ANC, "ANC_getActuatorName")(self.device, axisNo, ctypes.byref(name))
        self.checkErrorCode(code)
        return name.value.decode('utf-8').strip(" ")
        
        
    def getActuatorType(self, axisNo):
        '''
        Get the type of the currently selected actuator
        Parameters
            axisNo	Axis number (0 ... 2)
        Returns
            type_	Type of the actuator {0: linear, 1: goniometer, 2: rotator}
        '''
        types = ["linear", "goniometer", "rotator"]
        type_ = ctypes.c_int()
        code = getattr(self.ANC, "ANC_getActuatorType")(self.device, axisNo, ctypes.byref(type_))
        self.checkErrorCode(code)
        return types[type_.value]
       
        
    def getAmplitude(self, axisNo):
        '''
        Reads back the amplitude parameter of an axis.
        
        Parameters
            axisNo	Axis number (0 ... 2)
        Returns
            amplitude	Amplitude V
        '''
        amplitude = ctypes.c_double()
        code = getattr(self.ANC, "ANC_getAmplitude")(self.device, axisNo, ctypes.byref(amplitude))
        self.checkErrorCode(code)
        return amplitude.value
    
    
    def getAxisStatus(self, axisNo):
        '''
        Reads status information about an axis of the device.
        Parameters
            axisNo	Axis number (0 ... 2)
        Returns
            connected	Output: If the axis is connected to a sensor.
            enabled	Output: If the axis voltage output is enabled.
            moving	Output: If the axis is moving.
            target	Output: If the target is reached in automatic positioning
            eotFwd	Output: If end of travel detected in forward direction.
            eotBwd	Output: If end of travel detected in backward direction.
            error	Output: If the axis' sensor is in error state.
        '''
        connected = ctypes.c_int()
        enabled = ctypes.c_int()
        moving = ctypes.c_int()
        target = ctypes.c_int()
        eotFwd = ctypes.c_int()
        eotBwd = ctypes.c_int()
        error = ctypes.c_int()

        code = getattr(self.ANC, "ANC_getAxisStatus")(self.device, axisNo, ctypes.byref(connected), ctypes.byref(enabled), ctypes.byref(moving), ctypes.byref(target), ctypes.byref(eotFwd), ctypes.byref(eotBwd), ctypes.byref(error))
        self.checkErrorCode(code)
        return {
            "connected": connected.value == 1, 
            "enabled": enabled.value == 1,
            "moving": moving.value == 1,
            "target_reached": target.value == 1,
            "EoTF": eotFwd.value == 1,
            "EoTB": eotBwd.value == 1,
            "error": error.value == 1}
    
    
    def getDeviceConfig(self):
        '''
        Reads static device configuration data
        Parameters
            None
        Returns
            featureSync	"Sync": Ethernet enabled (1) or disabled (0)
            featureLockin	"Lockin": Low power loss measurement enabled (1) or disabled (0)
            featureDuty	"Duty": Duty cycle enabled (1) or disabled (0)
            featureApp	"App": Control by IOS app enabled (1) or disabled (0)
        '''
        features = ctypes.c_int()
        code = getattr(self.ANC, "ANC_getDeviceConfig")(self.device, features)
        self.checkErrorCode(code)
        
        featureSync = 0x01&features.value
        featureLockin = (0x02&features.value)/2
        featureDuty = (0x04&features.value)/4
        featureApp = (0x08&features.value)/8
        
        return featureSync, featureLockin, featureDuty, featureApp

    
    def getDeviceInfo(self, devNo=0):
        '''
        Returns available information about a device. The function can not be called before ANC_discover but the devices don't have to be connected . All Pointers to output parameters may be zero to ignore the respective value.
        Parameters
            devNo	Sequence number of the device. Must be smaller than the devCount from the last ANC_discover call. Default: 0
        Returns
            devType	Output: Type of the ANC350 device. {0: Anc350Res, 1:Anc350Num, 2:Anc350Fps, 3:Anc350None}
            id	Output: programmed hardware ID of the device
            serialNo	Output: The device's serial number. The string buffer should be NULL or at least 16 bytes long.
            address	Output: The device's interface address if applicable. Returns the IP address in dotted-decimal notation or the string "USB", respectively. The string buffer should be NULL or at least 16 bytes long.
            connected	Output: If the device is already connected
        '''
        devType = ctypes.c_int()
        id_ = ctypes.c_int()
        serialNo = ctypes.create_string_buffer(16) 
        address = ctypes.create_string_buffer(16) 
        connected = ctypes.c_int()

        code = getattr(self.ANC, "ANC_getDeviceInfo")(devNo, ctypes.byref(devType), ctypes.byref(id_), ctypes.byref(serialNo), ctypes.byref(address), ctypes.byref(connected))
        self.checkErrorCode(code)
        return devType.value, id_.value, serialNo.value.decode('utf-8'), address.value.decode('utf-8'), connected.value
    
    
    def getFirmwareVersion(self):
        '''
        Retrieves the version of currently loaded firmware.
        Parameters
            None
        Returns
            version	Output: Version number
        '''
        version = ctypes.c_int()
        code = getattr(self.ANC, "ANC_getFirmwareVersion")(self.device, ctypes.byref(version))
        self.checkErrorCode(code)
        return version.value
    
    
    def getFrequency(self, axisNo):
        '''
        Reads back the frequency parameter of an axis.
        Parameters
            axisNo	Axis number (0 ... 2)
        Returns
            frequency	Output: Frequency in Hz
        '''
        frequency = ctypes.c_double()
        code = getattr(self.ANC, "ANC_getFrequency")(self.device, axisNo, ctypes.byref(frequency))
        self.checkErrorCode(code)
        return frequency.value
    
    def getDcVoltage(self, axisNo):

        voltage = ctypes.c_double()
        code = getattr(self.ANC, "ANC_getDcVoltage")(self.device, axisNo, ctypes.byref(voltage))
        self.checkErrorCode(code)
        return voltage.value

    def getPosition(self, axisNo):
        '''
        Retrieves the current actuator position. For linear type actuators the position unit is m; for goniometers and rotators it is degree.
        Parameters
            axisNo	Axis number (0 ... 2)
        Returns
            position	Output: Current position [m] or [°]
        '''
        position = ctypes.c_double()
        code = getattr(self.ANC, "ANC_getPosition")(self.device, axisNo, ctypes.byref(position))
        self.checkErrorCode(code)
        return position.value
    
    
    def measureCapacitance(self, axisNo):
        '''
        Performs a measurement of the capacitance of the piezo motor and returns the result. If no motor is connected, the result will be 0. The function doesn't return before the measurement is complete; this will take a few seconds of time.
        Parameters
            axisNo	Axis number (0 ... 2)
        Returns
            cap	Output: Capacitance [F]
        '''
        cap = ctypes.c_double()
        code = getattr(self.ANC, "ANC_measureCapacitance")(self.device, axisNo, ctypes.byref(cap))
        self.checkErrorCode(code)
        return cap.value
   

    def saveParams(self):
        '''
        Saves parameters to persistent flash memory in the device. They will be present as defaults after the next power-on. The following parameters are affected: Amplitude, frequency, actuator selections as well as Trigger and quadrature settings.
        Parameters
            None
        Returns
            None
        '''
        code = getattr(self.ANC, "ANC_saveParams")(self.device)
    
    
    # def selectActuator(self, axisNo, actuator):
    #     '''
    #     Selects the actuator to be used for the axis from actuator presets.
    #     Parameters
    #         axisNo	Axis number (0 ... 2)
    #         actuator	Actuator selection (0 ... 255)
    #             0: ANPg101res
    #             1: ANGt101res
    #             2: ANPx51res
    #             3: ANPx101res
    #             4: ANPx121res
    #             5: ANPx122res
    #             6: ANPz51res
    #             7: ANPz101res
    #             8: ANR50res
    #             9: ANR51res
    #             10: ANR101res
    #             11: Test
    #     Returns
    #         None
    #     '''
    #     self.ANC.selectActuator(self.device, axisNo, actuator)
    
    
    def setAmplitude(self, axisNo, amplitude):
        '''
        Sets the amplitude parameter for an axis
        Parameters
            axisNo	Axis number (0 ... 2)
            amplitude	Amplitude in V, internal resolution is 1 mV
        Returns
            None
        '''
        code = getattr(self.ANC, "ANC_setAmplitude")(self.device, axisNo, ctypes.c_double(amplitude))
        self.checkErrorCode(code)
   

    def setAxisOutput(self, axisNo, enable, autoDisable):
        '''
        Enables or disables the voltage output of an axis.
        Parameters
            axisNo	Axis number (0 ... 2)
            enable	Enables (1) or disables (0) the voltage output.
            autoDisable	If the voltage output is to be deactivated automatically when end of travel is detected.
        Returns
            None
        '''
        en_num = 1 if enable else 0
        code = getattr(self.ANC, "ANC_setAxisOutput")(self.device, axisNo, en_num, autoDisable)
   

    # def setDcVoltage(self, axisNo, voltage): # NOT SUPPORTED BY SHARED OBJECT LIBRARY
    #     '''
    #     Sets the DC level on the voltage output when no sawtooth based motion is active.
    #         Parameters
    #         axisNo	Axis number (0 ... 2)
    #         voltage	DC output voltage [V], internal resolution is 1 mV
    #     Returns
    #         None        
    #     '''
    #     code = getattr(self.ANC, "ANC_setDcVoltage")(self.device, axisNo, ctypes.c_double(voltage))
    #     self.checkErrorCode(code)

    def setFrequency(self, axisNo, frequency):
        '''
        Sets the frequency parameter for an axis
        Parameters
            axisNo	Axis number (0 ... 2)
            frequency	Frequency in Hz, internal resolution is 1 Hz
        Returns
            None
        '''
        code = getattr(self.ANC, "ANC_setFrequency")(self.device, axisNo, ctypes.c_double(frequency))
        self.checkErrorCode(code)

    def setTargetPosition(self, axisNo, target):
        '''
        Sets the target position for automatic motion, see ANC_startAutoMove. For linear type actuators the position unit is m, for goniometers and rotators it is degree.
        Parameters
            axisNo	Axis number (0 ... 2)
            target	Target position [m] or [°]. Internal resulution is 1 nm or 1 µ°.
        Returns
            None
        '''
        logging.debug("Setting Target Position to %f", target)
        code = getattr(self.ANC, "ANC_setTargetPosition")(self.device, axisNo, ctypes.c_double(target))
        self.checkErrorCode(code)
        self.target_pos[axisNo] = target
        
        
    def setTargetRange(self, axisNo, targetRg):
        '''
        Defines the range around the target position where the target is considered to be reached.
        Parameters
            axisNo	Axis number (0 ... 2)
            targetRg	Target range [m] or [°]. Internal resulution is 1 nm or 1 µ°.
        Returns
            None
        '''
        code = getattr(self.ANC, "ANC_setTargetRange")(self.device, axisNo, ctypes.c_double(targetRg))
        self.checkErrorCode(code)
        self.target_range[axisNo] = targetRg
        
        
    def startAutoMove(self, axisNo, enable, relative):
        '''
        Switches automatic moving (i.e. following the target position) on or off
        Parameters
            axisNo	Axis number (0 ... 2)
            enable	Enables (1) or disables (0) automatic motion
            relative	If the target position is to be interpreted absolute (0) or relative to the current position (1)
        Returns
            None
        '''
        code = getattr(self.ANC, "ANC_startAutoMove")(self.device, axisNo, enable, relative)
        self.checkErrorCode(code)
        
   
    def startContinuousMove(self, axisNo, start, backward):
        '''
        Starts or stops continous motion in forward direction. Other kinds of motions are stopped.
        Parameters
            axisNo	Axis number (0 ... 2)
            start	Starts (1) or stops (0) the motion
            backward	If the move direction is forward (0) or backward (1)
        Returns
            None
        '''
        code = getattr(self.ANC, "ANC_startContinousMove")(self.device, axisNo, start, backward)
        self.checkErrorCode(code)
        
    def startSingleStep(self, axisNo, backward):
        '''
        Triggers a single step in desired direction.
        Parameters
            axisNo	Axis number (0 ... 2)
            backward	If the step direction is forward (0) or backward (1)
        Returns
            None
        '''
        code = getattr(self.ANC, "ANC_startSingleStep")(self.device, axisNo, backward)
        self.checkErrorCode(code)

    def __del__(self):
        logging.debug("DISCONNECTING")
        self.disconnect()

    def checkErrorCode(self, code):
        ANC_Ok = 0 #                    No error
        ANC_Error = -1 #                Unknown / other error
        ANC_Timeout = 1 #               Timeout during data retrieval
        ANC_NotConnected = 2 #          No contact with the positioner via USB
        ANC_DriverError = 3 #           Error in the driver response
        ANC_DeviceLocked = 7 #          A connection attempt failed because the device is already in use
        ANC_Unknown = 8 #               Unknown error.
        ANC_NoDevice = 9 #              Invalid device number used in call
        ANC_NoAxis = 10 #               Invalid axis number in function call
        ANC_OutOfRange = 11 #           Parameter in call is out of range
        ANC_NotAvailable = 12 #         Function not available for device type

        if code == ANC_Ok:
            return
        elif code == ANC_Error:             
            raise AttocubeException("Error: unspecific Error Occured")
        elif code == ANC_Timeout:           
            raise AttocubeException("Error: comm. timeout")
        elif code == ANC_NotConnected:      
            raise AttocubeException("Error: not connected") 
        elif code == ANC_DriverError:       
            raise AttocubeException("Error: driver error") 
        elif code == ANC_DeviceLocked:      
            raise AttocubeException("Error: device locked")
        elif code == ANC_NoDevice:
            raise AttocubeException("Error: invalid device number")
        elif code == ANC_NoAxis:
            raise AttocubeException("Error: invalid axis number")
        elif code == ANC_OutOfRange:
            raise AttocubeException("Error: parameter out of range")
        elif code == ANC_NotAvailable:
            raise AttocubeException("Error: function not available")
        else:                    
            raise AttocubeException("Error: unknown")
