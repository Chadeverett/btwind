// Bluetooth Anemometer v2.0
// Created on 3/14/21 by Chad Brown

// Uses a hall sensor (44e?) to sense revolutions of anemometer
// Arduino tracks each revolution and calculates RPM and wind speed
// ModernDevice LCD117 tty seraial LCD displays wind speed and BT status
// Seeed Bluetooth Shield v1 transmits JSON data via BT serial connection 

// TODO: Highest Gust Reset
// TODO: 
// TODO: 
// TODO: 

#include <SoftwareSerial.h>

SoftwareSerial lcd(49, 50); // RX, TX For LCD Screen

// Configuration Vars
String btDevName = "Seed";
String btDevPin = "0000";

char btStat = '0'; // bluetooth connection status
String pMessage = ""; // last program message

// setup
int pin = 30;           // hall sensor output pin
int det = 0;            // 0 = last check no magnet detected 1 = last check magnet detected
int count = 0;          // this is an unnecessary count of revolutions
unsigned long last = 0; // this holds the last no-mag to magnet transition time in ms
int mph = 0;            // this holds the last mph reading
int moving = 0;         // this tracks if the anemometer is rotating or not
int gust = 0;           // this tracks the highest gust

// Run once on startup
void setup()
{
    Serial.begin(38400); // Start USB serial connection
    lcd.begin(9600);     // Start lcd serial connection
    lcd.print("?B01");   // backlight intensity in hex from 00 (0) to FF (255)
    delay(100);          // delay for backlight command0
    lcd.print("?c0");    // hide lcd cursor
    lcd.print("?f");    // clear lcd screen
    lcd.print("Wind Speed: 0");
    delay(2000);
    setupBlueToothConnection(); // start the bluetooth shield
}

// Main Loop
void loop() 
{ 
  listenForMsg();
}

// Recieves Seed BT status messages
// messages must start and end with \r\n
void rcvSeedMsg() 
{
  while(1) {
    char c = com();
    if (c == ':') {
      btStat = com();
      Serial.print(btStat);
      processSeedMsg();
      break; // go back to listen for message
    }
  }
}

void processSeedMsg() {
  if (btStat == '0') { // Initializing
      Serial.print("\nInitializing\n");
      lcd.print("?a?j?j?j?lBT:Initializing");
  } 
  else if (btStat == '1') { // Ready for connection
      Serial.print("\nReady\n");
      lcd.print("?a?j?j?j?lBT: Ready");
  }
  else if (btStat == '2') { // Inquiring
      Serial.print("\nInquiring\n");
      lcd.print("?a?j?j?j?lBT: Inquiring");
  }
  else if (btStat == '3') { // Connecting
      Serial.print("\nConnecting\n");
      lcd.print("?a?j?j?j?lBT: Connecting");
  }
  else if (btStat == '4') { // Connected
      Serial.print("\nConnected\n");
      lcd.print("?a?j?j?j?lBT: Connected");
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
      Serial.print(pMessage);
      break; // go back to listen for message
    } else {
      pMessage += c;
    }
  }
}
 
// Listen for start of an incoming message
void listenForMsg()
{
  while(1) {
    char c = com();
    if (c == '+') { // seed admin message
      rcvSeedMsg();
    } else if (c == char('@')) { // program message
      rcvProgMsg();
    }
  }
}

void wind() {
  if (digitalRead(pin) == 1 && det == 1) { // first detect no magnet - High
    det = 0;
  } else if (digitalRead(pin) == 0 && det == 0) {
    det = 1;    
    if (moving == 0) { // first rotation, no print
      moving = 1;
      last = millis();
    } else {
      count = count+1;
      unsigned long now = millis();
      unsigned long time = now - last; 
      last = now;
      int rpm = 60000 / time;
      mph = rpm/6;
      if (mph > gust) {
        gust = mph;
        lcd.print("?a?j?lHighest Gust: " + String(gust));
      }
      //Serial.print("\nMPH: " + String(mph) + "\nRPM: " + String(rpm) + "\nCount: " + String(count) + "\nTime: " + String(time) + "\n");
      if (btStat == '4') {
        Serial3.print("{\"mph\":\"" + String(mph) + "\", \"gust\":\"" + String(gust) + "\"}"); // json formatted output
      }
      lcd.print("?a?lWind Speed: " + String(mph));
    }
  } else if ((moving == 1) && ((millis() - last) > 10000)) {
    moving = 0;
    mph = 0;
    lcd.print("?a?lWind Speed: " + String(mph));
    Serial3.print("{\"mph\":\"" + String(mph) + "\", \"gust\":\"" + String(gust) + "\"}");
  }  
}

// Check for incoming data
char com()
{
  while(1) {
    wind(); // this updates wind info
    char recvChar;
    if(Serial3.available()){// check if there's any data sent from the remote bluetooth shield
      recvChar = Serial3.read();
      return recvChar;
    }
    if(Serial.available()){// check if there's any data sent from the local serial terminal, you can add the other applications here
      recvChar  = Serial.read();
      //Serial3.print(recvChar);
      return recvChar;
    }
  }
}

// Start bluetooth shield
void setupBlueToothConnection()
{
    Serial3.begin(38400);                                  // Set BluetoothBee BaudRate to default baud rate 38400
    Serial3.print("\r\n+STWMOD=0\r\n");                    // set the bluetooth work in slave mode
    Serial3.print("\r\n+STNA=" + btDevName + "\r\n");      // set the bluetooth name as "Sees"
    Serial3.print("\r\n+STOAUT=1\r\n");                    // Permit Paired device to connect me
    Serial3.print("\r\n+STAUTO=1\r\n");                    // Auto-connection should be forbidden here
    Serial3.print("\r\n+STPIN =" + btDevPin + "\r\n");
    delay(2000);                                            // This delay is required.
    Serial3.print("\r\n+INQ=1\r\n");                        // make the slave bluetooth inquirable
    //lcd.print("?a?j?jDevice Name: " + btDevName);
    lcd.print("?a?j?j?jBT: Ready");
    delay(2000);                                            // This delay is required.
    Serial3.flush();
}
