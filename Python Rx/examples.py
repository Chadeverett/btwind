



from kivy.config import ConfigParser

config = ConfigParser()

config.read('btwindrx.ini')

print(config.get('General', 'address'))


