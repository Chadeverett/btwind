// Bluetooth Anemometer v2.0
// Created on 3/14/21 by Chad Brown

// Uses a hall sensor (44e?) to sense revolutions of anemometer
// Arduino tracks each revolution and calculates RPM and wind speed
// ModernDevice LCD117 tty serial LCD displays wind speed and BT status
// Seeed Bluetooth Shield v1 transmits JSON data via BT serial connection 

// TODO: Send display light status to remote host
// TODO: Set PIN IO0 to High on reset to ensure BT disconnect? 
// TODO: 
// TODO:



#include <TimerEvent.h>
#include <math.h>

// LCD Setup
#include <SoftwareSerial.h>
SoftwareSerial lcd(49, 50); // RX, TX For LCD Screen
int dispLights = 1;

// Temp Sensor Setup
#include "Wire.h"
#include <LibTempTMP421.h>
int I2Caddress = 0x2A;  // set this to 0x2A before uploading to Github
/* this low-current sensor can be powered from Arduino pins (optional) */
const int GNDpin = 18;  // A2 for UNO / 18 for Arduino Mega
const int PWRpin = 19;  // A3 for UNO / 19 for Arduino Mega
LibTempTMP421 temp = LibTempTMP421(0, I2Caddress);

// Configuration Vars
String btDevName = "Seed";
String btDevPin = "0000";

// button setup pin #s
int b[4] = {0,32,33,34};

// bluetooth setup
int btInit = 1;     // Bluetooth shield init state tracking
char btState = '0'; // bluetooth connection status
String pMessage = ""; // last program message
String sMessage = ""; // last seed message

// wind setup
int pin = 30;           // hall sensor output pin
int det = 0;            // 0 = last check no magnet detected 1 = last check magnet detected
int count = 0;          // this is an unnecessary count of revolutions
unsigned long last = 0; // this holds the last no-mag to magnet transition time in ms
int mph = 0;            // this holds the last mph reading
int moving = 0;         // this tracks if the anemometer is rotating or not
int gust = 0;           // this tracks the highest gust
int mphLast = 1;
int gustLast = 1;
String tempLast = "";

// Timed Events
const int dataUpdateInterval = 1000; // ms
TimerEvent dataUpdateTimer; 

// Run once on startup
void setup()
{
    // Temp
    pinMode(GNDpin, OUTPUT);        // GND pin
    pinMode(PWRpin, OUTPUT);        // VCC pin
    digitalWrite(PWRpin, HIGH);
    
    // USB Serial
    Serial.begin(38400); // Start USB serial connection
    // LCD
    lcd.begin(9600);     // Start lcd serial connection
    lcd.print("?BFF");   // backlight intensity in hex from 00 (0) to FF (255)
    delay(100);          // delay for backlight command0
    lcd.print("?c0");    // hide lcd cursor
    lcd.print("?f");    // clear lcd screen
  
    delay(1000);
    temp.Init();
    // Bluetooth
    setupBlueToothConnection(); // start the bluetooth shield
    dataUpdateTimer.set(dataUpdateInterval, updateData);
}

// Main Loop
void loop() 
{ 
  listenForMsg(0);
}

void updateData() {
  String t = getTemp();
  if (mphLast != mph) {
    lcd.print("?a?lWind Speed: " + String(mph));
  }
  if (gustLast != gust) {
    lcd.print("?a?j?lHighest Gust: " + String(gust));
  }
  if (tempLast != t) {
    lcd.print("?a?j?j?lTemp: " + t);
  }
  if (btState == '4') {
    Serial3.print("{\"mph\":\"" + String(mph) + "\", \"gust\":\"" + String(gust) + "\", \"temp\":\"" + t + "\"}"); // json formatted output for BT com
  }
  mphLast = mph;
  gustLast = gust;
  tempLast = t;
}

// Listen for start of an incoming message
void listenForMsg(int numMsgs)
{
  int i = 1;
  while(i <= numMsgs || numMsgs == 0) {
    char c = com();
    if (c == '\n') { // seed admin message
      if (numMsgs > 0) {
        i = i + 1;
      } 
      rcvSeedMsg();
    } else if (c == char('@')) { // program message
      rcvProgMsg();
    }
  }
}

// Check for incoming data
char com()
{
  while(1) {
    dataUpdateTimer.update();
    wind(); // this updates wind info
    if (digitalRead(b[1]) && dispLights == 0) { // Lights On
      dispLights = 1;
      lcd.print("?BFF");
    } else if (digitalRead(b[3]) && dispLights == 1) { // Lights Off
      dispLights = 0;
      lcd.print("?B00");
    } else if (digitalRead(b[2]) && gust > 0) {
      gust = 0;
      //lcd.print("?a?j?lHighest Gust: " + String(gust));
      //btDataUpdate();
    }
    char recvChar;
    if(Serial3.available()){// check if there's any data sent from the remote bluetooth shield
      recvChar = Serial3.read();
      //Serial.print(recvChar);
      return recvChar;
    }
    if(Serial.available()){// check if there's any data sent from the local serial terminal, you can add the other applications here
      recvChar  = Serial.read();
      //Serial3.print(recvChar);
      return recvChar;
    }
  }
}

// Receives program messages from remote code
// messages must start and end with @ character
void rcvProgMsg()
{
  pMessage = "";
  while(1) {
    char c = com();
    if (c == char('@')) {
      if (pMessage == "R") {
        gust = 0;
        //lcd.print("?a?j?lHighest Gust: " + String(gust));
        //btDataUpdate();
      } else if (pMessage == "L") {
        if (dispLights == 1) {
          dispLights = 0;
          lcd.print("?B00");
        } else {
          dispLights = 1;
          lcd.print("?BFF");
        }
      }
      break; // go back to listen for message
    } else {
      pMessage += c;
    }
  }
}
 
// Recieves Seed BT status messages
// messages must start and end with \r\n
void rcvSeedMsg() 
{
  sMessage = "";
  while(1) {
    char c = com();
    if (c == '\n') { // end of message start
      Serial.println(sMessage); // print the message to serial monitor
      break; // jump out of loop
    }
    else if ((c == ':') && (sMessage.indexOf('+') >= 0)) { // Status message, status of seed is next rcvd char
        sMessage += c;
        btState = com(); // collect next char (status)
        sMessage += btState; // add status to sMessage
        if (btInit == 0) {
          processSeedState(); // process the status update
        }
    }
    else { // this is part of the message
      sMessage += c; // add this character to the message string
    }
  }
} 
 
void processSeedState() {
  // LCD Display of Bluetooth Status
  if (btState == '0') { // Initializing
      lcd.print("?a?j?j?j?lBT: Initializing");
  } 
  else if (btState == '1') { // Ready for connection
      lcd.print("?a?j?j?j?lBT: Ready");
  }
  else if (btState == '2') { // Inquiring
      lcd.print("?a?j?j?j?lBT: Discoverable");
  }
  else if (btState == '3') { // Connecting
      lcd.print("?a?j?j?j?lBT: Connecting");
  }
  else if (btState == '4') { // Connected
      lcd.print("?a?j?j?j?lBT: Connected");
  }
}

// Wind speed detection should be run every loop
void wind() {
  if (digitalRead(pin) == 1 && det == 1) { // first detect no magnet - High
    det = 0;
  }
  else if (digitalRead(pin) == 0 && det == 0) {
    det = 1;    
    if (moving == 0) { // first rotation, no print
      moving = 1;
      last = millis();
    } 
    else {
      count = count+1;
      unsigned long now = millis();
      unsigned long time = now - last; 
      last = now;
      int rpm = 60000 / time;
      int lastMph = mph;
      mph = rpm/6;
      if (mph > gust) {
        gust = mph;
        //lcd.print("?a?j?lHighest Gust: " + String(gust));
      }
    }
  } 
  else if ((moving == 1) && ((millis() - last) > 10000)) {
    moving = 0;
    mph = 0;
    //lcd.print("?a?lWind Speed: " + String(mph));
    //btDataUpdate();
  }  
}

String getTemp() {
  // gets a truncated String from a float
  // TODO: Round to 4 digit int, then String 
  float F = temp.GetTemperature()*9/5+32;
  int rounded = round(F*10);
  String strT = String(rounded);
  int i = strT.length()-1;
  String postDec = strT.substring(i);
  String preDec = strT.substring(0,i);
  String strTemp = preDec + "." + postDec;
  return strTemp;
}

// Start bluetooth shield
void setupBlueToothConnection()
{
    processSeedState();
    Serial3.begin(38400);                               // Set BluetoothBee BaudRate to default baud rate 38400
    Serial.println("Setting Slave Mode");
    Serial3.print("\r\n+STWMOD=0\r\n");                 // set the bluetooth work in slave mode
    listenForMsg(5); // listen for response
    Serial.println("\nSetting Name");
    Serial3.print("\r\n+STNA=" + btDevName + "\r\n");   // set the bluetooth name
    listenForMsg(5); // listen for response
    Serial.println("\nSetting Pair Allowed");
    Serial3.print("\r\n+STOAUT=1\r\n");                 // Permit pairing
    listenForMsg(5); // listen for response
    Serial.println("\nSetting auto-connect off");
    Serial3.print("\r\n+STAUTO=0\r\n");                 // Auto-connection should be forbidden here
    listenForMsg(5); // listen for response
    Serial.println("\nSetting device inquirable");
    Serial3.print("\r\n+INQ=1\r\n");                    // make the slave bluetooth inquirable   
    listenForMsg(3); // listen for response
    Serial3.flush();                                    // flush the buffer
    btInit = 0;
    processSeedState();   
}
