import logging
from lib.model.smartplugin import SmartPlugin

"""
in __init__.py
--------------

    def __init__(self, smarthome, ip='0.0.0.0', port=0):
        if self.is_int(port):
            self.port = int(port)
        else:
            self.port = 0
            self.logger.error("Invalid value '{}' configured for attribute port in plugin.conf, using '{}' instead".format(port, self.port if self.port != None else "random")
        if self.port == 0:
            #TODO: define port automatically
            pass
        
        self.callbackserver = CallbackServer(smarthome, ip, port)

    def run(self):
        self.callbackserver.connect()
    
    def stop(self):
        self.callbackserver.close()
"""

class CallbackServer(lib.connection.Server):

    HEADER_TERMINATOR = b"\r\n\r\n"
    
    def __init__(self, smarthome, ip, port):
        lib.connection.Server.__init__(self, ip, port)
        self.logger = logging.getLogger(__name__)
        self._sh = smarthome

    def handle_connection(self):
# Notify message sample:
"""    
NOTIFY delivery path HTTP/1.1
HOST: delivery host:delivery port
CONTENT-TYPE: text/xml; charset="utf-8"
NT: upnp:event
NTS: upnp:propchange
SID: uuid:subscription-UUID
SEQ: event key
CONTENT-LENGTH: bytes in body

<?xml version="1.0"?>
<e:propertyset xmlns:e="urn:schemas-upnp-org:event-1-0">
    <e:property>
        <variableName>new value</variableName>
    </e:property>
</e:propertyset>
"""

        sock, address = self.accept()
        if sock is None:
            return
        
        headerbytes = bytearray()
        contentbytes = bytearray()
        while True:
            buffer = sock.recv(1024)
            if not buffer:
                break
            if HEADER_TERMINATOR not in buffer:
                headerbytes.extend(buffer)
            else:
                index = buffer.find(HEADER_TERMINATOR)
                headerbytes.extend(buffer[:index])
                contentbytes = buffer[index]
        
        headerstring = headerbytes.decode()
        if not headerstring.startswith('NOTIFY '):
            self.send(b"HTTP/1.1 400 Bad Request\r\n\r\n", close=True)
            return
        else:
            #TODO: Parse UPnP NOTIFY header

            while True:
                buffer = sock.recv(1024)
                if not buffer:
                    break
                contentbytes.extend(buffer)
            
            #TODO: parse UPnP XML in contentbytes
            
            self.send(b"HTTP/1.1 200 OK\r\n\r\n", close=True)
