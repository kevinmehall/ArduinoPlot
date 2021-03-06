"""
Listen to serial, return most recent numeric values
Lots of help from here:
http://stackoverflow.com/questions/1093598/pyserial-how-to-read-last-line-sent-from-serial-device
"""
import time
import serial
import math

class SerialData(object):
    def __init__(self, port='/dev/ttyUSB0', columns=(0,), file=None):
        self.unfinished_line = None
        self.columns = columns
        try:
            self.ser = ser = serial.Serial(
                port=port,
                baudrate=9600,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.1,
                xonxoff=0,
                rtscts=0,
            )
        except serial.serialutil.SerialException as e:
            print e
            #no serial connection
            self.ser = None
        else:
            self.ser.setTimeout(0)
        if file:
        	self.file = open(file, 'at')
        else:
        	self.file = None
            
    def sendLine(self, s):
        self.ser.write(s + '\n');
        
    def next(self):
        out = [[] for i in self.columns]
        
        if not self.ser:
            return [[100]] #return anything so we can test when Arduino isn't connected
        
        for line in self.ser.readlines():
            if self.unfinished_line:
                line=self.unfinished_line + line
                self.unfinished_line = False
            if not line.endswith('\n'):
                self.unfinished_line = line
                return out
            if self.file:
            	self.file.write(line)
            try:
                cols = line.strip().split()
                for column, lst in zip(self.columns, out):
                    lst.append(float(cols[column]))
            except ValueError:
                print 'Invalid float: ', line
            except IndexError:
                print 'Wrong number of cols: ', line
        return out
        return 0.
    def __del__(self):
        if self.ser:
            self.ser.close()

if __name__=='__main__':
    s = SerialData()
    for i in range(500):
        time.sleep(.015)
        print s.next()
        
