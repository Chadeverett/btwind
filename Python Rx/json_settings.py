import json

json_settings = json.dumps([
    
    {
        "type": "bool",
        "title": "Display Lights",
        "desc": "Turn the display lights on or off",
        "section": "General",
        "key": "lights"
    },
    {
        "type": "string",
        "title": "Device Address",
        "desc": "Device MAC Address",
        "section": "General",
        "key": "address"
    }
    
])
