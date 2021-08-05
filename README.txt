btwind - Arduino / Python / Kivy

Arduino -
The Arduino code implements a basic hall sensor for detecting the RPM of a homemade rotating wind sensor. A TMP421 temperature sensor is also implemented to detect air temperature. Values are rendered on an LCD display and transmitted over bluetooth serial connection via a Seeduino bluetooth shield (v1).

Python -
The Python code initiates a bluetooth connection with the Seeduino bluetooth shield and establishes a bluetooth serial connection. Incoming sensor values are parsed and displayed in a Kivy GUI window.

