from SMWinservice import SMWinservice
import sspeci_bridge_script
# import test_bridge as sspeci_bridge_script

import zerorpc
import time

# import clr
# import sys


class BridgeService(SMWinservice):
    _svc_name_ = "SSPECIBridge"
    _svc_display_name_ = "Spectrometer Intergration Bridge Service"
    _svc_description_ = "Allows RPC control of the Spectrometer API for Odin Control"

    def start(self):
        self.server = zerorpc.Server(sspeci_bridge_script.RPCServer())
        self.isrunning = True
        pass

    def stop(self):
        self.isrunning = False
        self.server.stop()
        self.server.close()
        pass

    def main(self):
        self.server.bind("tcp://192.168.0.102:4242")
        self.server.run()
        # while self.isrunning:
        pass


if __name__ == '__main__':
    BridgeService.parse_command_line()