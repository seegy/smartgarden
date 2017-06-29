#!flask/bin/python
from flask import Flask
from werkzeug.routing import FloatConverter as BaseFloatConverter
import time
import threading
import ConfigParser
import grovepi
import sys, os
import logging
from logging.handlers import RotatingFileHandler


pathname = os.path.dirname(sys.argv[0])

if not pathname:
    pathname = "."

Config = ConfigParser.ConfigParser()
Config.read(pathname + '/config.ini')

#Logger
app_name= Config.get('Watering-Server', 'app-name')
log_level= Config.get('Log', 'level')
log_file= Config.get('Log', 'file')
log_format= '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

logging.basicConfig(filename=log_file,level=logging.getLevelName(log_level))
logger = logging.getLogger(app_name)
fh = RotatingFileHandler(log_file, maxBytes=10000000, backupCount=5)
formatter = logging.Formatter(log_format)
fh.setFormatter(formatter)
fh.setLevel(logging.getLevelName(log_level))
logger.addHandler(fh)

pour_interval_time= int(Config.get('Watering-Server', 'pour_interval_time'))   # approx one minute in seconds
pour_pause_time= int(Config.get('Watering-Server', 'pour_pause_time'))
relay_pin = int(Config.get('Watering-Server', 'relay-pin'))
server_port = int(Config.get('Watering-Server', 'port'))

grovepi.pinMode(relay_pin, "OUTPUT")
grovepi.digitalWrite(relay_pin, 0)


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
        logger.info('start watering')
        grovepi.digitalWrite(relay_pin, 1)
        time.sleep(pour_interval_time)

        logger.info('stop watering')
        grovepi.digitalWrite(relay_pin, 0)
        time.sleep(pour_pause_time)

    rest_interval= intervals - full_intervals

    if rest_interval > 0:
        logger.info('start watering')
        grovepi.digitalWrite(relay_pin, 1)
        time.sleep(rest_interval * pour_interval_time)

        logger.info('stop watering')
        grovepi.digitalWrite(relay_pin, 0)
        time.sleep(pour_pause_time)


app = Flask(__name__)
app.url_map.converters['float'] = FloatConverter # set floatconverter
app.logger.addHandler(fh)

@app.route('/status', methods=['GET'])
def status_request():
    return "OK!"


@app.route('/pour/<float:interval_count>', methods=['PUT'])
def pour_request(interval_count):
    threading.Thread(target= pour, args=[interval_count]).start()
    return "ok, I will do " + str(interval_count) + " intervals."


if __name__ == '__main__':
    logger.info('starting server...')
    app.run(host='0.0.0.0', port=server_port)