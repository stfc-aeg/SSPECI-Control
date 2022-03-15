import enum
import logging

import ctypes, os, time
import platform
import json

from odin.adapters.adapter import (ApiAdapter, ApiAdapterRequest,
                                   ApiAdapterResponse, request_types, response_types)
from odin.adapters.parameter_tree import ParameterTree, ParameterTreeError
from odin.util import decode_request_body
from sspeci.attocube_controller import StageController

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
