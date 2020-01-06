#!/usr/bin/python3

import socket
import sys
#import struct
#TCP_IP = '192.168.0.29' 
#TCP_PORT = 5000     
#BUFFER_SIZE = 1024
#message = "MT00SWXXYYNT"   # XX = input YY = output
#message = "IP?"            # Query IP
#message = "MT00RD0000NT"   # Returns some weird status
#message = "MT00BZEN01NT"   # This one mutes the buzzer

#commands=[ "MT00BZEN01NT", "MT00SW0101NT", "MT00SW0102NT", "MT00SW0203NT", "MT00SW0204NT", "MT00SW0205NT"]
 
class tesmart_matrix:
    
    def __init__(self, name="matrix"):
        self.buffer_size=4
        self.config={   "address": "192.168.0.29", "port":5000, "output_count": 8, "timeout":.5,
                        "outputs": { "O1":"Office Monitor 1", "O2": "Downstairs Monitor 1", "O3":"Office Monitor 2", "O4":"Downstairs Monitor 2",
                                     "O5":"Living Room TV", "O8":"Rack Monitor"},
                        "inputs": { "I1":"PC1", "I2": "PC2"}

        }
        self.matrix_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.matrix_socket.settimeout(self.config['timeout'])     
        
    def start(self):
        self.get_status()
        self.set_output(1,1)
        self.set_output(2,1)
        self.get_status()
        #self.set_output(2,1)
        #self.set_output(3,1)
        #self.get_status()
        #self.set_output(4,2)
        #self.set_output(3,2)
        #self.get_status()
        #self.set_output(4,2)

        
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
    
    def get_status(self):
        try:
            result=self.send_message("MT00RD0000NT", response=True)
            #print('Status: %s' % result)
            if result.startswith('LINK') and result.endswith('END'):
                data_parts=result[5:-4].split(';')
                data={}
                for part in data_parts:
                    if part[0:2] in self.config['outputs']:
                        output_name=self.config['outputs'][part[0:2]]
                        if part[2:4] in self.config['inputs']:
                            input_name=self.config['inputs'][part[2:4]]
                        else:
                            input_name=part[2:4]
                        data[output_name]=input_name
                print('State: %s' % data)
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
    adapter=tesmart_matrix(name="matrix")
    adapter.start()
    
        
        
