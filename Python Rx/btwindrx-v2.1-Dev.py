'''

Bluetooth Wind Receiver v2.1 (Kivy GUI)
Created on 3/14/21 by Chad Brown

Receives wind speed data via bluetooth from
an arduino with bluetooth shield running custom transmit code.

Written for Python 3+ and Kivy
Requires Kivy Module ($ pip3 install kivy)

IMPORTANT LINUX NOTE: (Confirmed on Ubuntu 20.04)
There is a problem with bluez default settings in ubuntu/debian
To allow re-connection without re-pairing, the BT config must be altered
To fix edit /etc/bluetooth/main.conf and add: DisablePlugins = pnat
It will work to some degree without the fix but it needs to pair every time

TODO: Finish detailed commenting
TODO: Backlight slider?
TODO: Early warning about connection problems via message timing
TODO: Daily High / Low temp?
TODO: Wind Chill
TODO: 
TODO: 

Version History:
v2.0 - GUI Base
v2.1 - Moved listener from separate thread into connection thread
     - Added settings page and reconfigured input buttons
     - Changed watcher to a stoppable a subclass and eliminated loop delay
       
'''
import bluetooth
import select
from queue import Queue
import json
import os
import telnetlib
import socket
import threading
import time

from kivy.lang import Builder
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.stacklayout import StackLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.checkbox import CheckBox
from kivy.uix.textinput import TextInput
from kivy.uix.dropdown import DropDown
from kivy.uix.slider import Slider
from kivy.app import App
from kivy.config import Config
from kivy.config import ConfigParser
from kivy.clock import Clock, mainthread
from kivy.storage.dictstore import DictStore
from kivy.uix.settings import SettingsWithSidebar
from json_settings import json_settings
from kivy.uix.progressbar import ProgressBar
from kivy.core.window import Window
Window.size = (400, 275)

DEBUGLVL = 3

# kivy lang code to build the settings button ... while part of the functioning
# code this is basically here for example so I can learn to do ui with kv lang
Builder.load_string('''
<Interface>:
    orientation: 'vertical'
    Button:
        size_hint_y: None
        height: 35
        text: 'Settings'
        on_release: app.open_settings()
    Widget:
''')

class Interface(BoxLayout): # this is the settings base layout
    pass

##########################################################################################################
#######   Begin MainView Class   #########################################################################
##########################################################################################################

# This class is the main application layout, below we build the initial GUI with Kivy
class MainView(BoxLayout):
    def __init__(self, **kwargs):
        super(MainView, self).__init__(**kwargs)
        self.stop = threading.Event()
        self.windMain()
        
## Builds the main control view
    def windMain(self):       
        self.settings = Interface()
        self.containerStack = StackLayout(padding=10, spacing=5, size_hint=(1, 1))

        # create a stack layout for info display
        self.info = StackLayout(padding=10, spacing=5, size_hint=(1, None))

        # info display widgets
        self.windStatusLbl = Label(text='-- mph', height=50, font_size=50, size_hint=(1, None), color=[77,77,77,1])
        self.gustStatusLbl = Label(text='Highest Gust: -- mph', height=20, font_size=20, size_hint=(1, None))
        self.tempStatusLbl = Label(text='Temperature: ---', height=20, font_size=20, size_hint=(1, None))
        self.connStatusLbl = Label(text='BT: Disconnected', height=20, font_size=16, size_hint=(1, None), color=[6,100,81,8])
        self.space2StatusLbl = Label(text='', height=20, font_size=20, size_hint=(1, None))
        self.gustRstBtn = Button(text='Reset High Gust', size_hint=(1, None), height=35)
        self.dispLightsBtn = Button(text='Toggle Display Lights', size_hint=(1, None), height=35)
        self.gustRstBtn.bind(on_release=self.resetGust)
        self.dispLightsBtn.bind(on_release=self.toggleDispLights)
        self.info.add_widget(self.windStatusLbl)
        self.info.add_widget(self.gustStatusLbl)
        self.info.add_widget(self.tempStatusLbl)
        #self.info.add_widget(self.space1StatusLbl)
        self.info.add_widget(self.connStatusLbl)
        self.info.add_widget(self.space2StatusLbl)
        self.info.add_widget(self.gustRstBtn)
        #self.info.add_widget(self.dispLightsBtn)
        self.info.add_widget(self.settings)

        # add the login base layout to the main layout
        self.containerStack.add_widget(self.info)
        self.add_widget(self.containerStack)
        self.comErr = False

        # initialize data queues used to pass data between threads
        # these queue names may seem non intuitive but they refer to the flow of data into or out of the connection thread
        self.qIn = Queue() # this is the queue that we'll input messages to be sent to the remote host
        self.qOut = Queue() # this is the queue that we'll recieve messages from the remote host

        # start watcher thread, this thread's purpose is to start the connection on first run and restart whenever connection is lost
        self.watcher = watcherThread(self) # initialize watcher thread
        self.watcher.start() # start the watcher thread

    # This queues up an outgoing command to toggle the display lights in the box
    def toggleDispLights(self, touch):
        self.qIn.put("@L@") # add a command to the listener thread input queue

    # This queues up an outgoing command to reset the high gust in the box
    def resetGust(self, touch):
        self.qIn.put("@R@") # add a command to the listener thread input queue 

    # Do this UI stuff whenever the connection is lost
    @mainthread
    def connLost(self):
        self.windStatusLbl.text = "-- mph"
        self.gustStatusLbl.text = "Highest Gust: -- mph"
        self.tempStatusLbl.text = "Temperature: ---"
        self.connStatusLbl.text = "BT: Disconnected"
        self.connStatusLbl.color = [6,100,81,8]

    # This is run whenever a complete datagram arrives, it updates UI components
    @mainthread 
    def onDataUpdate(self):
        m = self.qOut.get()
        self.windStatusLbl.text = f'{m["mph"]} mph' # update wind speed display
        self.gustStatusLbl.text = f'Highest Gust: {m["gust"]} mph' # update high gust display
        self.tempStatusLbl.text = f'Temperature: {m["temp"]}' # update temperature display


##########################################################################################################
#######   Begin Watcher Class   ##########################################################################
##########################################################################################################

# This is always running, it restarts the connection when
# the conection thread exits due to failed connection or host down. 
class watcherThread(threading.Thread):
    def __init__(self, p):
        super(watcherThread, self).__init__()
        self.daemon = False
        self._stop_event = threading.Event()
        self.p = p

    def run(self):
        self.watcher()

    def watcher(self):
        while 1:
            if self.stopped():
                break
            if not hasattr(self, "connection") or not self.connection.is_alive():
                self.connection = connectionThread(self.p.qIn, self.p.qOut, self)
                self.connection.start()
        msg("Watcher thread is exiting", 3)
        

    def stop(self):
        self._stop_event.set()

    def stopped(self):
        return self._stop_event.is_set()

##########################################################################################################
######### Begin Connection Class #########################################################################
##########################################################################################################

# This is always run in a separate non-daemon thread, it connects and stays alive
# as long as the connection within it stays alive. When an established connection dies,
# or a connect fails the thread dies The watcher will re-start it indefinitely to establish
# a new connection.      
class connectionThread(threading.Thread):
    def __init__(self, qIn, qOut, p, args=()):
        super(connectionThread, self).__init__()
        self._stop_event = threading.Event()
        self.daemon = False
        self.p = p
        self.qIn = qIn
        self.qOut = qOut

    def run(self):
        self.connectBT()

    def connectBT(self):
        devAddr = storage.get('General', 'address') # address of the bluetooth rfcomm device from settings
        port = 1 # communication channel
        sock = bluetooth.BluetoothSocket(bluetooth.RFCOMM) # init the socket
        msg(f"Attempting BT RFCOMM connection with {devAddr}", 3)
        try:
            sock.connect((devAddr, port)) # try to connect
            sock.settimeout(1) # not sure if this is needed, sts the socket timeout to blocking
        except bluetooth.btcommon.BluetoothError as e:
            msg(f"Failed to establish connection with {devAddr}: {e}")
            return # no connection, jump on outta this thread and watcher will start a new one soon to try again
        msg(f"Successfully connected with {devAddr}", 3)
        self.p.p.connStatusLbl.text = "BT: Connected" # update UI
        self.p.p.connStatusLbl.color = [86,70,10,1]
        sock.settimeout(0) # this is necessary, it allows non-blocking access to the coms
        while 1:
            self.clear() # this is absolutely necessary, the stop flag remains set even though the thread was restarted listen would then return stop in stage 1
            if self.listen(sock) == 'stop': # check for some data, if stop is returned, close out this connection
                msg("Connection thread is exiting, stop was returned from listener", 3)
                break # jump out of loop causing thread to exit
            if len(self.qIn.queue) > 0: # this unassuming bit of code is very important, if there's anything in the input queue ...
                sock.send(self.qIn.get()) # send it over the wire
            
    def listen(self, sock):
        if self.stopped(): # if the stop signal has been set
            msg("Listener is exiting, stop call detected in listener.listen() stage 1", 3)
            return 'stop' # return stop to close the socket and exit the threads cleanly
        data = self.com(sock)
        if self.stopped(): # if the stop signal has been set
            msg("Listener is exiting, stop call detected in listener.listen() stage 2", 3)
            return 'stop' # return stop to close the socket and exit the threads cleanly  
        if data == "{":
            message = data
            while 1:
                if self.stopped(): # if the stop signal has been set
                    msg("Listener is exiting, stop call detected in listener.listen() stage 3", 3)
                    return 'stop' # return stop to close the socket and exit the threads cleanly 
                while 1 :
                    if self.stopped(): # if the stop signal has been set
                        msg("Listener is exiting, stop call detected in listener.listen() stage 4", 3)
                        return 'stop' # return stop to close the socket and exit the threads cleanly 
                    data = self.com(sock)
                    if data:
                        break
                message += data
                if data == "}":
                    dataDict = json.loads(message)
                    self.qOut.put(dataDict) # add message to queue for reading in the main thread
                    self.p.p.onDataUpdate() # trigger update of UI
                    break

    def com(self, sock):
        try:
            data = sock.recv(1)
        except bluetooth.btcommon.BluetoothError as e:
            if str(e).find("temporarily") >= 0: # this is no data on the pipe, situation normal, just return
                return
            if str(e).find("busy") >= 0: # this is just no data on the pipe, situation normal, just return
                return
            else: # this is a loss of connection
                self.p.p.connLost()
                msg(f"The connection was lost: {e}")
                msg("Stop will now be called in listener.com()", 2)
                self.stop()
                return
        if data:
            return data.decode("utf-8")
            
    def stop(self):
        self._stop_event.set()

    def clear(self):
        self._stop_event.clear()

    def stopped(self):
        return self._stop_event.is_set()

##########################################################################################################
#######   Begin App class   ##############################################################################
##########################################################################################################

# This class builds and starts our app       
class btwindrx(App):
    
    def on_stop(self):
        # The Kivy event loop is about to stop, so set a stop signal;
        # otherwise the app window will close, but the Python process will
        # keep running until all secondary threads exit.
        msg("User initiated shutdown, sending non-daemon threads a stop signal", 3)
        if hasattr(self.mv, 'watcher'):
            self.mv.watcher.stop()
        if hasattr(self.mv.watcher, 'connection'):
            self.mv.watcher.connection.stop()
        self.root.stop.set()
    
    def build(self):
        #self.settings_cls = SettingsWithSidebar # Optional alternative settings layout
        self.use_kivy_settings = False
        self.mv = MainView()
        return self.mv

    def build_config(self, config):
        config.setdefaults("General", {"address": "00:18:E4:0C:68:00", "update": "1", "connection":"1", "lights":"1"})

    def build_settings(self, settings):
        settings.add_json_panel("General", self.config, data=json_settings)

    def on_config_change(self, config, section, key, value):
        if key == "address":
            storage.set('General', 'address', value)
        elif key == "update":
            storage.set('General', 'interval', value)
        elif key == "connection":
            storage.set('General', 'connection', value)
        elif key == "lights":
            storage.set('General', 'lights', value)
            self.mv.qIn.put("@L@") # add a command to the listener thread input queue

##########################################################################################################
#######   Begin Main Line Code   #########################################################################
##########################################################################################################

# error/msg/log handling 
def msg(msg, lvl=1):
    debugLvl = 3
    if debugLvl > 0 and lvl <= debugLvl:
        if lvl == 1: print(f'ERROR - {msg}\n')
        if lvl == 2: print(f'WARN - {msg}\n')
        if lvl == 3: print(f'INFO - {msg}\n')

# this starts our kivy app and is the only main line code other than imports.
if __name__ == '__main__':
    storage = ConfigParser()
    storage.read("btwindrx.ini")
    btwindrx().run()
