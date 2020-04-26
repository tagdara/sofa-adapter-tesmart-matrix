#!/usr/bin/python3

import sys, os
# Add relative paths for the directory where the adapter is located as well as the parent
sys.path.append(os.path.dirname(__file__))
sys.path.append(os.path.join(os.path.dirname(__file__),'../../base'))

from sofabase import sofabase
from sofabase import adapterbase
import devices
import socket
import json
import asyncio
#import struct
#TCP_IP = '192.168.0.29' 
#TCP_PORT = 5000     
#BUFFER_SIZE = 1024
#message = "MT00SWXXYYNT"   # XX = input YY = output
#message = "IP?"            # Query IP
#message = "MT00RD0000NT"   # Returns some weird status
#message = "MT00BZEN01NT"   # This one mutes the buzzer

#commands=[ "MT00BZEN01NT", "MT00SW0101NT", "MT00SW0102NT", "MT00SW0203NT", "MT00SW0204NT", "MT00SW0205NT"]

class Client(asyncio.Protocol):

    def __init__(self, loop=None, log=None, notify=None, dataset=None, **kwargs):
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
                asyncio.ensure_future(self.parse_data(self.buffer))
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
                #self.log.info('.. pulling command from queue: %s' % self.lastcommand)
                self.send(self.lastcommand)

        except:
            self.log.error('Error bumping queue',exc_info=True)
            
    def send(self, data):
        
        try:
            self.log.info('>> matrix  %s' % data.replace('\n', ' ').replace('\r', ''))
            self.transport.write(data.encode())
        except:
            self.log.error('Error on send', exc_info=True)
            
    def get_status(self):
        self.queue_for_send("MT00RD0000NT")
        
    async def parse_data(self, result):
        try:
            self.log.info('<< matrix %s' % result)
            if result.startswith('LINK') and result.endswith('END'):
                data_parts=result[5:-4].split(';')
                data={}
                for part in data_parts:
                    if part[0:2] in self.dataset.config['outputs']:
                        output_name=self.dataset.config['outputs'][part[0:2]]
                        input_name=part[2:4]
                        if input_name in self.dataset.config['inputs']:
                            input_name=self.dataset.config['inputs'][part[2:4]]
                        item={ "name": output_name, "input": part[2:4], "input_name" : input_name }
                        await self.dataset.ingest({ "output": { part[0:2]: item } })
        except:
            print('error getting status: %s' % sys.exc_info())

    def set_output(self, output_id, input_id):
        try:
            input_id=str(input_id)
            output_id=str(output_id)
            if len(input_id)==1:
                input_id="0"+str(input_id)
            if len(output_id)==1:
                output_id="0"+str(output_id)
            print('Setting %s to %s' % (output_id, input_id))
            self.queue_for_send("MT00SW%s%sNT" % (input_id, output_id))
            self.get_status()
        except:
            self.log.error('Error setting Output %s to %s' % (output_id, input_id), exc_info=True)
            print('Error setting output')


class matrix(sofabase):

    class EndpointHealth(devices.EndpointHealth):

        @property            
        def connectivity(self):
            return 'OK'

    class InputController(devices.InputController):

        @property            
        def input(self):
            try:
                # Yamaha returns the name of the input instead of it's id, but the name can be overridden on the device and it will still
                # reply with the original value. For example, an input_sel of "AV4" would typically represent AV_4, even if AV_4's name was
                # changed to "TV".  
                # In order to deal with their cheese, stripping the underscore from the id and comparing with the input_sel will almost always work
                # to get the right id.
                
                # look for it properly

                return self.nativeObject['input_name']
                
            except:
                self.adapter.log.error('Error checking input status', exc_info=True)
                return ""
                    
        async def SelectInput(self, payload, correlationToken=''):
            try:
                response=None
                for inp in self.adapter.dataset.config['inputs']:
                    if payload['input']==self.adapter.dataset.config['inputs'][inp]:
                        self.log.info('Setting Device %s to %s' % (self.device.endpointId[-1:], inp[1:]))
                        self.adapter.matrixClient.set_output(self.device.endpointId[-1:], inp[1:])
                        response=await self.adapter.dataset.generateResponse(self.device.endpointId, correlationToken)
                        # figure out how to set input from here
                        # return await self.adapter.dothething(self.device, newinput, correlationToken)
                if response==None:
                    self.log.info('Could not find %s in %s' % (payload['input'],self.adapter.dataset.config['inputs'] ))
            except:
                self.log.error('!! Error during SelectInput', exc_info=True)
            return response
                
    class adapterProcess(adapterbase):  
        
        def __init__(self, log=None, dataset=None, notify=None, loop=None, **kwargs):
            self.buffer_size=4
            self.dataset=dataset
            self.config=self.dataset.config
            self.log=log
            self.notify=notify
            if not loop:
                self.loop = asyncio.new_event_loop()
            else:
                self.loop=loop
        
        async def connect(self):
            self.log.info('.. Connecting to matrix at %s:%s' % (self.config['address'], self.config['port']))
            self.matrixClient = Client(loop=self.loop, log=self.log, notify=self.notify, dataset=self.dataset)
            await self.loop.create_connection(lambda: self.matrixClient, self.config['address'], self.config['port'])
            
        async def start(self):
            await self.connect()

        async def addSmartDevice(self, path):
            
            try:
                if path.split("/")[1]=="output":
                    return self.addMatrixOutput(path.split("/")[2])
            except:
                self.log.error('Error defining smart device', exc_info=True)

        def addMatrixOutput(self, deviceid, name="Matrix"):
            
            nativeObject=self.dataset.nativeDevices['output'][deviceid]
            name=nativeObject['name']
            if name not in self.dataset.devices:
                device=devices.alexaDevice('matrix/output/%s' % deviceid, name, displayCategories=["MATRIX"], adapter=self)
                device.EndpointHealth=matrix.EndpointHealth(device=device)
                device.InputController=matrix.InputController(device=device, inputs=self.dataset.config['inputs'].values())
                return self.dataset.newaddDevice(device)
            return False

    
    def send_message(self, message, response=False):
        try:
            data=True
            self.matrix_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.matrix_socket.settimeout(self.config['timeout'])    
            self.matrix_socket.connect((self.config['address'], self.config['port']))
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
            pass
            self.matrix_socket.close()
        except:
            print('error closing socket: %s' % sys.exc_info())
            data=False
        
        return data

    async def get_status(self):
        try:
            result=self.send_message("MT00RD0000NT", response=True)
            #print('Status: %s' % result)
            if result.startswith('LINK') and result.endswith('END'):
                data_parts=result[5:-4].split(';')
                data={}
                for part in data_parts:
                    if part[0:2] in self.config['outputs']:
                        output_name=self.config['outputs'][part[0:2]]
                        input_name=part[2:4]
                        if input_name in self.config['inputs']:
                            input_name=self.config['inputs'][part[2:4]]
                        data[part[0:2]]={ "name": output_name, "input": part[2:4], "input_name" : input_name }
                        await self.dataset.ingest({ "output": {item: result[item]} })
        except:
            print('error getting status: %s' % sys.exc_info())
        

    def set_beep(self, beep_on):
        try:
            if beep_on:
                result=self.send_message("MT00BZEN00NT")   
            else:
                result=self.send_message("MT00BZEN01NT")   
        except:
            print('error setting beep')
        
    def set_output(self, output_id, input_id):
        try:
            input_id=str(input_id)
            output_id=str(output_id)
            if len(input_id)==1:
                input_id="0"+str(input_id)
            if len(output_id)==1:
                output_id="0"+str(output_id)
            print('Setting %s to %s' % (output_id, input_id))
            result=self.send_message("MT00SW%s%sNT" % (input_id, output_id))
            return result
        except:
            print('Error setting output')

if __name__ == '__main__':
    adapter=matrix(name="matrix")
    adapter.start()
        
        
