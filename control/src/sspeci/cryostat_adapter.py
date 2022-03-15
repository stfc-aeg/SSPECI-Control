from builtins import FileNotFoundError
import logging
from multiprocessing import connection
import sys
import os
import json
from urllib import response
from xmlrpc.client import FastMarshaller
import requests
from requests.exceptions import ConnectionError, Timeout

import time


# from odin_data.ipc_channel import IpcChannel, IpcChannelException
# from odin_data.ipc_message import IpcMessage, IpcMessageException

from odin.adapters.adapter import (ApiAdapter, ApiAdapterRequest,
                                   ApiAdapterResponse, request_types, response_types)
from odin.adapters.parameter_tree import ParameterTree, ParameterTreeError
from odin.util import decode_request_body

# from cryostat_libs import cryocore, instrument

from tornado.httpclient import HTTPClient, HTTPRequest, HTTPClientError
from tornado.escape import json_decode
from tornado.ioloop import PeriodicCallback



class CryostatAdapter(ApiAdapter):


    def __init__(self, **kwargs):
        super(CryostatAdapter, self).__init__(**kwargs)

        logging.getLogger('urllib3').setLevel(logging.WARNING)  # stops debug spam from "connectionpool"

        self.cryo_ip = self.options.get("ip", "127.0.0.1")
        # use_tunnel = self.options.get("tunnel", False)
        self.cryo_port = self.options.get("port", 47101)
        self.power_schedule_directory = self.options.get("power_schedule_dir", "power_schedules")
        # self.cryo = cryocore.CryoCore(self.cryo_ip, tunnel=use_tunnel)
        self.cryo = CryoClient(self.cryo_ip, self.cryo_port, self.power_schedule_directory)
        self.param_tree = ParameterTree({
            "cryo_ip_addr": (self.cryo_ip, None),
            "stage1": {
                "temperature": (lambda: self.cryo.stage1_current_temp, None),
                "target_temp": (lambda: self.cryo.stage1_target_temp, None),
                "stability": (lambda: self.cryo.temp_stabilities[1], None),
                "heater_power": (lambda: self.cryo.heater_power[1], None)
            },
            "stage2": {
                "temperature": (lambda: self.cryo.stage2_current_temp, None),
                "target_temp": (lambda: self.cryo.stage2_target_temp, None),
                "stability": (lambda: self.cryo.temp_stabilities[2], None),
                "heater_power": (lambda: self.cryo.heater_power[2], None)
            },
            "atsm": {
                "temperature": (lambda: self.cryo.sample_current_temp, None),
                "target_temp": (lambda: self.cryo.sample_target_temp, self.cryo.set_sample_target_temp),
                "stability": (lambda: self.cryo.temp_stabilities[0], None),
                "heater_power": (lambda: self.cryo.heater_power[0], None),
                "power_limit": (lambda: self.cryo.power_limit, self.cryo.set_power_limit),
                "auto_control_enabled" : (lambda: self.cryo.user_controller_enabled, self.cryo.set_controller_enabled),
                "power_schedule_enabled": (lambda: self.cryo.power_schedule_enabled, self.cryo.set_power_schedule_enabled),
                "power_schedule_selected": (lambda: self.cryo.selected_schedule, self.cryo.load_power_schedule),
                "power_schedules_avail": (lambda: os.listdir(self.power_schedule_directory), None),
                "power_schedule": (lambda: self.cryo.power_lookup, None)
            },
            "system_goal": (lambda: "{}: {}".format(self.cryo.system_goal, self.cryo.system_state), None),
            "vacuum" : (lambda: self.cryo.vacuum_pressure, None),
            "bakeout": {
                "enabled": (lambda: self.cryo.bakeout_enabled, self.cryo.set_bakeout_enable),
                "temperature": (lambda: self.cryo.bakeout_temp, self.cryo.set_bakeout_temp),
                "time": (lambda: self.cryo.bakeout_time, self.cryo.set_bakeout_time)
            },
            "begin_cooldown": (None, self.cryo.begin_cooldown),
            "abort": (None, self.cryo.abort_goal),
            "pull_vacuum": (None, self.cryo.pull_vacuum),
            "vent": (None, self.cryo.vent),
            "warmup": (None, self.cryo.warmup),

            "capabilities": {
                "can_abort": (lambda: self.cryo.can_abort, None),
                "can_cooldown": (lambda: self.cryo.can_cooldown, None),
                "can_pull_vacuum": (lambda: self.cryo.can_pull_vac, None),
                "can_warmup": (lambda: self.cryo.can_warmup, None),
                "can_vent": (lambda: self.cryo.can_vent, None)
            }
        })

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

class CryoClient:

    properties = {
        "system_goal": "/controller/properties/systemGoal",
        "stage1_props": "/cooler/temperatureControllers/stage1",
        "stage2_props": "/cooler/temperatureControllers/stage2",
        "sample_stage": "/sampleChamber/temperatureControllers/user1"
    }

    def __init__(self, ip, port, schedule_dir):
        # self.client = HTTPClient()
        self.addr = "http://{ip}:{port}/{version}".format(ip=ip, port=port, version="v1")

        self.request_headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }
        self.schedule_dir = schedule_dir
        self.timeout = .05
        # store values locally to avoid hammering the cryostat with requests
        self.cryo_connected = False

        self.system_goal = "UNKNOWN"
        self.system_state = "UNKNOWN"

        self.sample_target_temp = -1
        self.stage1_target_temp = -1
        self.stage2_target_temp = -1

        self.sample_current_temp = -1
        self.stage1_current_temp = -1
        self.stage2_current_temp = -1

        self.vacuum_pressure = -1

        self.bakeout_enabled = False
        self.bakeout_temp = -1.0
        self.bakeout_time = -1.0

        self.can_abort = False
        self.can_cooldown = False
        self.can_pull_vac = False
        self.can_vent = False
        self.can_warmup = False

        self.temp_stabilities = [-1, -1, -1]
        self.heater_power = [-1, -1, -1]

        self.power_limit = -1.0
        self.user_controller_enabled = False
        self.power_schedule_enabled = False

        self.schedule_files = []
        logging.debug("Attempting to find Power schedule files in dir %s", schedule_dir)
        if os.path.exists(schedule_dir):
            self.schedule_files = os.listdir(schedule_dir)

        if "default.json" in self.schedule_files:
            self.load_power_schedule("default.json")
        else:
            self.power_lookup = {
                # key = temp, value = power limit at that temp
                3.5: 0.01,
                260: 1.8
                
            }
        self.selected_schedule = "default.json"
        logging.debug("Power Lookup: %s", self.power_lookup )

        prop_loop = PeriodicCallback(self.get_all_properties, 1000)
        prop_loop.start()


    def get_all_properties(self):
        # looping method to refresh all locally stored values
        try:
            start_time = time.time()
            with requests.Session() as s: # using session means it only has to init one HTTP connection each time this is called
                self.system_goal = self._get_prop(self.properties['system_goal'], s)
                self.system_state = self._get_prop("controller/properties/systemState", s)
                
                userstage_sample = self._get_prop("/".join([self.properties['sample_stage'], "thermometer/properties/sample"]), s)
                stage1_sample    = self._get_prop("/".join([self.properties['stage1_props'], "thermometer/properties/sample"]), s)
                stage2_sample    = self._get_prop("/".join([self.properties['stage2_props'], "thermometer/properties/sample"]), s)

                self.sample_current_temp = userstage_sample['temperature']
                self.stage1_current_temp = stage1_sample['temperature']
                self.stage2_current_temp = stage2_sample['temperature']

                self.temp_stabilities = [userstage_sample['temperatureStability'],
                                        stage1_sample['temperatureStability'],
                                        stage2_sample['temperatureStability']]

                user_heater_sample = self._get_prop("/".join([self.properties['sample_stage'], "heater/properties/sample"]), s)
                stage1_heater_sample = self._get_prop("/".join([self.properties['stage1_props'], "heater/properties/sample"]), s)
                stage2_heater_sample = self._get_prop("/".join([self.properties['stage2_props'], "heater/properties/sample"]), s)

                self.heater_power = [user_heater_sample['power'], stage1_heater_sample['power'], stage2_heater_sample['power']]


                self.sample_target_temp = self._get_prop("/".join([self.properties['sample_stage'], "properties/targetTemperature"]), s)
                self.stage1_target_temp = self._get_prop("/".join([self.properties['stage1_props'], "properties/targetTemperature"]), s)
                self.stage2_target_temp = self._get_prop("/".join([self.properties['stage2_props'], "properties/targetTemperature"]), s)

                self.power_limit = self._get_prop("/".join([self.properties['sample_stage'], "properties/userPowerLimit"]))
                self.user_controller_enabled = self._get_prop("/".join([self.properties['sample_stage'], "properties/controllerEnabled"]))



                vacuum_sample = self._get_prop("vacuumSystem/vacuumGauges/sampleChamberPressure/properties/pressureSample", s)
                self.vacuum_pressure = vacuum_sample['pressure']

                self.bakeout_enabled = self._get_prop("controller/properties/platformBakeoutEnabled", s)
                self.bakeout_temp = self._get_prop("controller/properties/platformBakeoutTemperature", s)
                self.bakeout_time = self._get_prop("controller/properties/platformBakeoutTime", s)

                self.can_abort = self._get_prop("controller/properties/canAbortGoal", s)
                self.can_cooldown = self._get_prop("controller/properties/canCooldown", s)
                self.can_pull_vac = self._get_prop("controller/properties/canPullVacuum", s)
                self.can_vent = self._get_prop("controller/properties/canVent", s)
                self.can_warmup = self._get_prop("controller/properties/canWarmup", s)
                if self.power_schedule_enabled:
                    planned_power = self.get_power_from_lookup()
                    logging.debug("Planned Power: %f", planned_power)
                    self.set_power_limit(planned_power)
                    self.power_limit = planned_power

        except (Timeout, ConnectionError):
            self.cryo_connected = False
            logging.error("TIMEOUT OR CONNECTION ERROR OH NO")

        end_time = time.time()


    def _get_prop(self, prop, session=None):
        # logging.debug("GET PROP: %s", prop)
        full_addr = self._url_construct(prop)

        if session:
            response = session.get(full_addr, timeout=self.timeout)
        else:
            response = requests.get(full_addr, timeout=self.timeout)
        
        # get the last part of the address to simplify the reponse dict
        last_addr_part = prop.split("/")[-1] 
        return json_decode(response.text)[last_addr_part]

    def _set_prop(self, prop, value):
        full_addr = self._url_construct(prop)
        last_addr_part = prop.split("/")[-1] 
        # request = HTTPRequest(full_addr, method="PUT", body=value)
        # response = self.client.fetch(request)

        response = requests.put(full_addr, json={last_addr_part: value})

        if 200 <= response.status_code < 300:
            logging.debug("set_prop successful")

        # return json_decode(response.text)

    def _call_method(self, path, param=None):

        full_addr = self._url_construct(path)
        last_addr_part = path.split("/")[-1] 
        # request = HTTPRequest(full_addr, method="POST")
        if param:
            response = requests.post(full_addr, json=param)
        else:
            response = requests.post(full_addr)
        

        return json_decode(response.text)

    def _url_construct(self, path):

        path = path.strip('/')
        path = path.replace('//', '/')  # in case it doubles up from maybe windows?

        return "{}/{}".format(self.addr, path)

    def set_sample_target_temp(self, value):
        try:
            full_addr = "/".join([self.properties['sample_stage'], "properties/targetTemperature"])

            self._set_prop(full_addr, value)

        except (Timeout, ConnectionError):
            logging.debug("Set Target Temp Failed: ")

    #potentially dont use the stage1 & stage2 stuff, leave that on auto?
    def set_stage1_target_temp(self, value):
        logging.warning("Changing the details of the cryostat Stages is not recommended")
        try:
            full_addr = "/".join([self.properties['stage1_props'], "properties/targetTemperature"])

            self._set_prop(full_addr, value)

        except (Timeout, ConnectionError):
            logging.debug("Set Target Temp Failed: ")

    def set_stage2_target_temp(self, value):
        logging.warning("Changing the details of the cryostat Stages is not recommended")
        try:
            full_addr = "/".join([self.properties['stage2_props'], "properties/targetTemperature"])

            self._set_prop(full_addr, value)

        except (Timeout, ConnectionError):
            logging.debug("Set Target Temp Failed: ")

    def set_bakeout_enable(self, value):
        try:
            self._set_prop("controller/properties/platformBakeoutEnabled", value)
        
        except (Timeout, ConnectionError):
            logging.error("Set Bakeout Enabled Failed")

    def set_bakeout_temp(self, value):
        try:
            self._set_prop("controller/properties/platformBakeoutTemperature", value)

        except (Timeout, ConnectionError):
            logging.error("Set Bakeout Enabled Failed")

    def set_bakeout_time(self, value):
        try:
            self._set_prop("controller/properties/platformBakeoutTime", value)
        except (Timeout, ConnectionError):
            logging.error("Set Bakeout Time Failed")

    def set_power_limit(self, value):
        try:
            self._set_prop("/".join([self.properties["sample_stage"], "properties/userPowerLimit"]), value)
        except (Timeout, ConnectionError):
            logging.error("Set Power Limit Failed")

    def set_controller_enabled(self, value):
        try:
            self._set_prop("/".join([self.properties['sample_stage'], "properties/controllerEnabled"]), value)
        except (Timeout, ConnectionError):
            logging.error("Set Controller Enabled Failed")


    # cryostat Methods

    def begin_cooldown(self, _):
        if self.can_cooldown:
            try:
                addr = "controller/methods/cooldown()"
                self._call_method(addr)
            except (Timeout, ConnectionError):
                logging.debug("Cooldown begin Failed")
        else:
            logging.debug("Cannot Begin Cooldown")

    def abort_goal(self, _):
        if self.can_abort:
            try:
                addr = "controller/methods/abortGoal()"
                self._call_method(addr)
            except (Timeout, ConnectionError):
                logging.debug("Abort Goal Failed")
        else:
            logging.debug("Cannot Abort")

    def vent(self, _):
        if self.can_vent:
            try:
                addr = "controller/methods/vent()"
                self._call_method(addr)
            except (Timeout, ConnectionError):
                logging.debug("Vent Failed")
        else:
            logging.debug("Cannot Vent")

    def pull_vacuum(self, _):
        if self.can_pull_vac:
            try:
                addr = "controller/methods/pullVacuum()"
                self._call_method(addr)
            except (Timeout, ConnectionError):
                logging.debug("Vacuum Pull Failed")
        else:
            logging.debug("Cannot Pull Vacuum")

    def warmup(self, _):
        if self.can_warmup:
            try:
                addr = "controller/methods/warmup()"
                self._call_method(addr)
            except (Timeout, ConnectionError):
                logging.debug("warmup begin Failed")
        else:
            logging.debug("Cannot Warmup")

    def load_power_schedule(self, filename):
        try:
            with open(os.path.join(self.schedule_dir, filename)) as file:
                file_dict = json.load(file)
                logging.debug("File: %s", file_dict)
                self.power_lookup = {float(key):value for (key, value) in file_dict.items()}
        except FileNotFoundError:
            logging.error("File %s does not exist", filename)

    # Lookup table stuff for power management
    def set_power_schedule_enabled(self, value):
        self.power_schedule_enabled = value

    def get_power_from_lookup(self):

        # if current temp lower than lowest temp in lookup, go with that
        # and vice versa for higher than highest temp
        #in between temps? average the power value between them? some sort of linear function?
        # the line getting method is probably basic maths lets do that
        # y = {m}x + {c} 

        temp = self.sample_current_temp

        temperature_points = sorted(self.power_lookup.keys())

        for i, point in enumerate(temperature_points):
            if temp < point:
                if i == 0:
                    # temp is lower than minimum value, return minimum
                    return self.power_lookup[point]
                else:
                    # x is the power, y is the temp
                    x1 = self.power_lookup[temperature_points[i-1]]
                    x2 = self.power_lookup[point]

                    y1 = temperature_points[i-1]
                    y2 = temperature_points[i]

                    return self.get_point_from_line_segment((x1, x2), (y1, y2), temp)
        
        # if we get here, temp is more than the max value in the table, so return the max
        return self.power_lookup[temperature_points[-1]]

    def get_point_from_line_segment(self, x_vals, y_vals, y):
        """
        y: current temperature
        x_vals: the x1 and x2 points that make up the line segment
        y_vals: the y1 and y2 points that make up the line segment
        returns: the power output that matches the Y value (temp) so that it can be mapped onto the line segment"""
        m = (y_vals[1]-y_vals[0])/(x_vals[1]-x_vals[0])

        x = ((y - y_vals[0])/m) + x_vals[0]

        logging.debug("M: %f, X: %f", m, x)

        return x
                    














