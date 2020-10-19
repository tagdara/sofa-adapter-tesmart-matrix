#!/usr/bin/python3

import sys, os
# Add relative paths for the directory where the adapter is located as well as the parent
sys.path.append(os.path.dirname(__file__))
sys.path.append(os.path.join(os.path.dirname(__file__),'../../base'))

from sofabase import sofabase, adapterbase, configbase
import devices
import socket
import json
import asyncio
import time
#import struct
#TCP_IP = '192.168.0.29' 
#TCP_PORT = 5000     
#BUFFER_SIZE = 1024
#message = "MT00SWXXYYNT"   # XX = input YY = output
#message = "IP?"            # Query IP
#message = "MT00RD0000NT"   # Returns some weird status
#message = "MT00BZEN01NT"   # This one mutes the buzzer
#beep_on = "MT00BZEN00NT"  
#beep_off = "MT00BZEN01NT"  

#commands=[ "MT00BZEN01NT", "MT00SW0101NT", "MT00SW0102NT", "MT00SW0203NT", "MT00SW0204NT", "MT00SW0205NT"]

class Client(asyncio.Protocol):

    def __init__(self, loop=None, log=None, notify=None, dataset=None, config=None, **kwargs):
        self.config=config
        self.is_open = False
        self.loop = loop
        self.log=log
        self.last_message = ""
        self.sendQueue=[]
        self.notify=notify
        self.dataset=dataset
        self.lastcommand=""
        self.controllerMap=dict()
        self.buffer=""
        self.waiting_for_status=False
        self.waiting_requests=[]
        
        # populate base dataset to eliminate oddly formatted adds
        self.dataset.nativeDevices={"output": {}}
        
    def connection_made(self, transport):
        
        try:
            self.log.info('.. connected to matrix')
            self.sockname = transport.get_extra_info("sockname")
            self.transport = transport
            self.is_open = True
        except:
            self.log.error('Connection made but something went wrong.', exc_info=True)
            
        try:
            self.programmingMode=False
            #self.log.info('Sending initial request')
            self.get_status()
        except:
            self.log.error('Error sending request', exc_info=True)
        
    def connection_lost(self, exc):
        self.is_open = False
        self.log.info('.. disconnected from matrix')
        self.loop.stop()

    def data_received(self, data):
        
        try:
            if data.decode().startswith('LINK'):
                self.buffer=data.decode()
            else:
                self.buffer=self.buffer+data.decode()
            if self.buffer.startswith('LINK') and self.buffer.endswith(';END'):
                self.loop.create_task(self.parse_data(self.buffer))
                self.buffer=""
            #else:
                #self.log.info('Buffer currently: [%s]' % self.buffer)
                
            self.checkSendQueue()
        except:
            self.log.error('Error processing received data: %s' % data, exc_info=True)

    def queue_for_send(self, data):
        self.log.info('.. adding command to queue: %s' % data)
        self.sendQueue.append(data)
        self.checkSendQueue()
            
    def checkSendQueue(self):
        
        try:
            if (len(self.sendQueue)>0):
                if self.programmingMode==False:
                    self.lastcommand=self.sendQueue.pop(0)
                self.log.info('.. pulling command from queue: %s' % self.lastcommand)
                self.send(self.lastcommand)
                time.sleep(.2)

        except:
            self.log.error('Error bumping queue',exc_info=True)
            
    def send(self, data):
        
        try:
            self.log.info('-> matrix %s' % data.replace('\n', ' ').replace('\r', ''))
            self.transport.write(data.encode())
        except:
            self.log.error('Error on send', exc_info=True)
            
    def get_status(self):
        self.waiting_for_status=True
        self.queue_for_send("MT00RD0000NT")
        
    async def parse_data(self, result):
        try:
            self.log.info('<- matrix %s' % result)
            if result.startswith('LINK') and result.endswith('END'):
                data_parts=result[5:-4].split(';')
                data={}
                for part in data_parts:
                    if part[0:2] in self.config.outputs:
                        output_name=self.config.outputs[part[0:2]]
                        input_name=part[2:4]
                        if input_name in self.config.inputs:
                            input_name=self.config.inputs[part[2:4]]
                        item={ "name": output_name, "input": part[2:4], "input_name" : input_name }
                        await self.dataset.ingest({ "output": { part[0:2]: item } })
                waiting_request=""
                if len(self.waiting_requests)>0:
                    waiting_request=self.waiting_requests.pop(0)
                self.log.info('<< matrix (applied update from status data) %s' % waiting_request)
        except:
            print('!! error getting status: %s' % sys.exc_info())

    def set_output(self, output_id, input_id, tracking_id=""):
        try:
            input_id=str(input_id)
            output_id=str(output_id)
            if len(input_id)==1:
                input_id="0"+str(input_id)
            if len(output_id)==1:
                output_id="0"+str(output_id)
            self.waiting_requests.append(tracking_id)
            self.queue_for_send("MT00SW%s%sNT" % (input_id, output_id))
            self.get_status()
        except:
            self.log.error('Error setting Output %s to %s' % (output_id, input_id), exc_info=True)
            print('Error setting output')


class matrix(sofabase):
    
    class adapter_config(configbase):
    
        def adapter_fields(self):
            self.inputs=self.set_or_default('inputs', default={})
            self.outputs=self.set_or_default('outputs', default={})
            self.output_count=self.set_or_default('output_count', default=8)
            self.matrix_address=self.set_or_default('matrix_address', mandatory=True)
            self.matrix_port=self.set_or_default('matrix_port', default=5000)
            self.matrix_timeout=self.set_or_default('matrix_timeout', default=0.5)
            
    class EndpointHealth(devices.EndpointHealth):

        @property            
        def connectivity(self):
            return 'OK'

    class InputController(devices.InputController):

        @property            
        def input(self):
            try:
                return self.nativeObject['input_name']
            except:
                self.adapter.log.error('Error checking input status', exc_info=True)
                return ""
                    
        async def SelectInput(self, payload, correlationToken=''):
            try:
                response=None
                for inp in self.device.adapter.config.inputs:
                    if payload['input']==self.device.adapter.config.inputs[inp]:
                        self.adapter.matrixClient.set_output(self.device.endpointId[-1:], inp[1:], correlationToken)
                        while correlationToken in self.adapter.matrixClient.waiting_requests:
                        #while self.adapter.matrixClient.waiting_for_status:
                            await asyncio.sleep(.1)
                        response=await self.adapter.dataset.generateResponse(self.device.endpointId, correlationToken)
                if response==None:
                    self.log.info('Could not find %s in %s' % (payload['input'],self.config.inputs ))
            except:
                self.log.error('!! Error during SelectInput', exc_info=True)
            return response
                
    class adapterProcess(adapterbase):  
        
        def __init__(self, log=None, dataset=None, notify=None, loop=None, config=None, **kwargs):
            self.config=config
            self.buffer_size=4
            self.dataset=dataset
            self.log=log
            self.log.info('config: %s' % self.config)
            self.notify=notify
            self.waiting_for_status=False

            if not loop:
                self.loop = asyncio.new_event_loop()
            else:
                self.loop=loop
        
        async def connect(self):
            self.log.info('.. Connecting to matrix at %s:%s' % (self.config.matrix_address, self.config.matrix_port))
            self.matrixClient = Client(loop=self.loop, log=self.log, notify=self.notify, dataset=self.dataset, config=self.config)
            await self.loop.create_connection(lambda: self.matrixClient, self.config.matrix_address, self.config.matrix_port)
            
        async def pre_activate(self):
            await self.connect()
            
        async def start(self):
            pass

        async def addSmartDevice(self, path):
            
            try:
                device_type=path.split("/")[1]
                device_id=path.split("/")[2]
                endpointId="%s:%s:%s" % ("matrix", device_type, device_id)
                if endpointId not in self.dataset.localDevices:
                    nativeObject=self.dataset.nativeDevices['output'][device_id]
                    if device_type=="output":
                        return self.addMatrixOutput(device_id, nativeObject)
            except:
                self.log.error('Error defining smart device', exc_info=True)

        def addMatrixOutput(self, deviceid, nativeObject):
            device=devices.alexaDevice('matrix/output/%s' % deviceid, nativeObject['name'], displayCategories=["MATRIX"], adapter=self)
            device.EndpointHealth=matrix.EndpointHealth(device=device)
            device.InputController=matrix.InputController(device=device, inputs=self.config.inputs.values())
            return self.dataset.add_device(device)
    
    def xxx_send_message(self, message, response=False):
        try:
            data=True
            self.matrix_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.matrix_socket.settimeout(self.config.matrix_timeout)    
            self.matrix_socket.connect((self.config.matrix_address, self.config.matrix_port))
        except:
            print('error setting up connection')
            
        try:
            data = self.matrix_socket.recv(1024)
            print('leftovers: %s' % data)
        except:
            pass
        
        try:
            message_bytes=message.encode()
            self.matrix_socket.send(message_bytes)
        except:
            print('Error sending message: %s %s' % (message, sys.exc_info()))
            data=False
            
        if response:
            try:
                data=""
                while 1:
                    newdata=self.matrix_socket.recv(self.buffer_size)
                    if not newdata:
                        break
                    data=data+newdata.decode()
                
                #data = self.matrix_socket.recv(64)
            except:
                pass
        try:
            self.matrix_socket.close()
        except:
            print('error closing socket: %s' % sys.exc_info())
            data=False
        
        return data



if __name__ == '__main__':
    adapter=matrix(name="matrix")
    adapter.start()
        
        
