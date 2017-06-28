#!flask/bin/python
from flask import Flask
from werkzeug.routing import FloatConverter as BaseFloatConverter
import time
import threading
import ConfigParser
import grovepi



Config = ConfigParser.ConfigParser()
Config.read('./config.ini')

pour_interval_time= int(Config.get('Watering-Server', 'pour_interval_time'))   # approx one minute in seconds
pour_pause_time= int(Config.get('Watering-Server', 'pour_pause_time'))
relay_pin = int(Config.get('Watering-Server', 'relay-pin'))
server_port = int(Config.get('Watering-Server', 'port'))

grovepi.pinMode(relay_pin, "OUTPUT")
grovepi.writeDigital(relay_pin, 0)

class FloatConverter(BaseFloatConverter):
    regex = r'-?\d+(\.\d+)?'


def synchronized(func):
    func.__lock__ = threading.Lock()

    def synced_func(*args, **kws):
        with func.__lock__:
            return func(*args, **kws)

    return synced_func



@synchronized
def pour(intervals):
    full_intervals=int(intervals)

    for i in range(0, full_intervals):
        print('start watering')
        grovepi.writeDigital(relay_pin, 1)
        time.sleep(pour_interval_time)

        print('stop watering')
        grovepi.writeDigital(relay_pin, 0)
        time.sleep(pour_pause_time)

    rest_interval= intervals - full_intervals

    if(rest_interval > 0):
        print('start watering')
        grovepi.writeDigital(relay_pin, 1)
        time.sleep(rest_interval * pour_interval_time)

        print('stop watering')
        grovepi.writeDigital(relay_pin, 0)
        time.sleep(pour_pause_time)


app = Flask(__name__)
app.url_map.converters['float'] = FloatConverter # set floatconverter

@app.route('/status', methods=['GET'])
def status_request():
    return "OK!"

@app.route('/pour/<float:interval_count>', methods=['PUT'])
def pour_request(interval_count):
    threading.Thread(target= pour, args=[interval_count]).start()
    return "ok, I will do " + str(interval_count) + " intervals."


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=server_port)