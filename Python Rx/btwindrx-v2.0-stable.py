'''

Bluetooth Wind Receiver v2.0 (Kivy GUI)
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

TODO: Settings Page
TODO: Backlight slider
TODO: Backlight status
TODO: Daily High / Low temp?
TODO: Wind Chill
TODO: Finish detailed commenting
TODO: Early warning about connection problems via message timing

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
from kivy.clock import Clock, mainthread
from kivy.storage.dictstore import DictStore
from kivy.uix.settings import SettingsWithSidebar
from json_settings import json_settings
from kivy.uix.progressbar import ProgressBar
from kivy.core.window import Window
Window.size = (400, 275)

DEBUGLVL = 3

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

class Interface(BoxLayout):
    pass

# This class is the main application layout, below we build the initial GUI with Kivy
class MainView(BoxLayout):
    def __init__(self, **kwargs):
        super(MainView, self).__init__(**kwargs)
        self.storage = DictStore('storage.dict')
        self.stop = threading.Event()
        self.windMain()

## Builds the main control view
    def windMain(self):
        self.qIn = Queue()
        self.qOut = Queue()
        self.listener = listenerThread(self.qIn, self.qOut, self) # build listener thread
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
        self.info.add_widget(self.dispLightsBtn)

        # add the login base layout to the main layout
        self.containerStack.add_widget(self.info)
        self.add_widget(self.containerStack)
        self.comErr = False

        # start listener thread
        self.connection = threading.Thread(target=connectBT, args=(self,)) # build connector thread
        self.connection.daemon = False
        self.connection.start()

        self.watcher = threading.Thread(target=self.watcher, args=()) # build connector thread
        self.watcher.daemon = True
        self.watcher.start()

######### Begin in-class functions #########################################################################

    # This queues up an outgoing command to toggle the display lights in the box
    def toggleDispLights(self, touch):
        self.qIn.put("@L@") # add a command to the listener thread input queue

    # This queues up an outgoing command to reset the high gust in the box
    def resetGust(self, touch):
        self.qIn.put("@R@") # add a command to the listener thread input queue 

    # This is always running in a daemon thread, it restarts the connection when
    # connection is lost or fails. This function calls startConnectionThread in the
    # main thread every second which starts a new connection thread only if none exists
    def watcher(self):
        while 1:
            time.sleep(1)
            self.startConnectionThread(None)

    # Do this UI stuff whenever the connection is lost
    @mainthread
    def connLost(self):
        self.windStatusLbl.text = "-- mph"
        self.gustStatusLbl.text = "Highest Gust: -- mph"
        self.tempStatusLbl.text = "Temperature: ---"
        self.connStatusLbl.text = "BT: Disconnected"
        self.connStatusLbl.color = [6,100,81,8]
        
    # This is run every 1 second by the watcher thread, if there's no connection thread, it fires off a new one 
    @mainthread
    def startConnectionThread(self, touch):
        if not self.connection.is_alive(): # if there's no running connection thread
            msg("Starting new connection thread", 3)
            self.connection = threading.Thread(target=connectBT, args=(self,)) # build connection thread
            self.connection.start() # start the new connection thread    

    # This is run whenever a complete datagram arrives, it updates UI components
    @mainthread 
    def onDataUpdate(self, m):
        self.windStatusLbl.text = f'{m["mph"]} mph' # update wind speed display
        self.gustStatusLbl.text = f'Highest Gust: {m["gust"]} mph' # update high gust display
        self.tempStatusLbl.text = f'Temperature: {m["temp"]}' # update temperature display


######### END in-class functions #########################################################################

# error/msg/log handling 
def msg(msg, lvl=1):
    if DEBUGLVL > 0 and lvl <= DEBUGLVL:
        if lvl == 1: print(f'ERROR - {msg}\n')
        if lvl == 2: print(f'WARN - {msg}\n')
        if lvl == 3: print(f'INFO - {msg}\n')

# This is always run in a separate non-daemon thread, it connects and stays alive
# as long as the connection within it stays alive. When an established connection dies,
# or a connect fails the thread dies The watcher will re-start it indefinitely to establish
# a new connection.
def connectBT(p):
    devAddr = "00:18:E4:0C:68:00" # address of the bluetooth rfcomm device
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
    p.connStatusLbl.text = "BT: Connected" # update UI
    p.connStatusLbl.color = [86,70,10,1]
    sock.settimeout(0) # this is necessary, it allows non-blocking access to the coms
    while 1:
        p.listener.clear() # this is absolutely necessary, the stop flag remains set even though the thread was restarted without this listener stage 1 immediately calls stop
        if p.listener.listen(sock) == 'stop': # check for some data, if stop is returned, close out this connection
            msg("Connection thread is exiting, stop was returned from listener", 3)
            break # jump out of loop causing thread to exit
        if len(p.qIn.queue) > 0: # this unassuming bit of code is very important, if there's anything in the input queue ...
            sock.send(p.qIn.get()) # send it over the wire
        
class listenerThread(threading.Thread):
    def __init__(self, qIn, qOut, p, args=()):
        super(listenerThread, self).__init__()
        self._stop_event = threading.Event()
        self.qIn = qIn
        self.qOut = qOut
        self.daemon = False
        self.p = p
        
    def listen(self, sock):
        if self.stopped(): # if the stop signal has been set
            msg("Listener thread is exiting, stop call detected in listener.listen() stage 1", 3)
            return 'stop' # return stop to close the socket and exit the threads cleanly
        data = self.com(sock)
        if self.stopped(): # if the stop signal has been set
            msg("Listener thread is exiting, stop call detected in listener.listen() stage 2", 3)
            return 'stop' # return stop to close the socket and exit the threads cleanly  
        if data == "{":
            message = data
            while 1:
                if self.stopped(): # if the stop signal has been set
                    msg("Listener thread is exiting, stop call detected in listener.listen() stage 3", 3)
                    return 'stop' # return stop to close the socket and exit the threads cleanly 
                while 1 :
                    if self.stopped(): # if the stop signal has been set
                        msg("Listener thread is exiting, stop call detected in listener.listen() stage 4", 3)
                        return 'stop' # return stop to close the socket and exit the threads cleanly 
                    data = self.com(sock)
                    if data:
                        break
                message += data
                if data == "}":
                    dataDict = json.loads(message)
                    self.qOut.put(dataDict)
                    self.p.onDataUpdate(dataDict)
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
                self.p.connLost()
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
    
# This class builds and starts our app       
class btwindrx(App):
    
    def on_stop(self):
        # The Kivy event loop is about to stop, so set a stop signal;
        # otherwise the app window will close, but the Python process will
        # keep running until all secondary threads exit.
        msg("User initiated shutdown, sending non-daemon threads a stop signal", 3)
        if hasattr(self.mv, 'listener'):
            self.mv.listener.stop()
        self.root.stop.set()
    
    def build(self):
        #self.settings_cls = SettingsWithSidebar # Optional alternative settings layout
        #self.use_kivy_settings = False
        self.mv = MainView()
        try:
            DEBUGLVL = self.mv.storage.get('debuglvl')['debuglvl']
        except KeyError:
            msg('KeyError "debugLvl" - Debug level setting not found in storage', 2)
        return self.mv

    def build_config(self, config):
        config.setdefaults("General", {"ip": "127.0.0.1", "port": "6969", "update": ".5", "connection":"1"})

    def build_settings(self, settings):
        settings.add_json_panel("Connection", self.config, data=json_settings)

    def on_config_change(self, config, section, key, value):
        if key == "ip":
            self.mv.storage.put('hostip', ip=value)
        elif key == "port":
            self.mv.storage.put('hostport', port=value)
        elif key == "update":
            self.mv.storage.put('interval', interval=value)
        elif key == "connection":
            self.mv.storage.put('connection', connection=value)
            if bool(value):
                pass
                #self.mv.startStatusUpdateThread(self)

# this starts our kivy app and is the only main line code other than imports.
if __name__ == '__main__':
    app = btwindrx().run()
