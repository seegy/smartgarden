#!flask/bin/python
from flask import Flask
from werkzeug.routing import FloatConverter as BaseFloatConverter
import threading
import libs.CustomRelay


from shared import *

# general configs
relay_pin = int(Config.get('Watering-Server', 'relay-pin'))
server_port = int(Config.get('Watering-Server', 'port'))

# configure pins
relay = libs.CustomRelay.CustomRelay(relay_pin)


class FloatConverter(BaseFloatConverter):
    regex = r'-?\d+(\.\d+)?'


@synchronized
def pour(intervals):
    full_intervals=int(intervals)

    reload_config()

    pour_interval_time= int(Config.get('Watering-Server', 'pour_interval_time'))
    pour_pause_time= int(Config.get('Watering-Server', 'pour_pause_time'))

    for i in range(0, full_intervals):
        logger.info('start watering')
        relay.close()
        time.sleep(pour_interval_time)

        logger.info('stop watering')
        relay.open()
        time.sleep(pour_pause_time)

    rest_interval= intervals - full_intervals

    if rest_interval > 0:
        logger.info('start watering')
        relay.close()
        time.sleep(rest_interval * pour_interval_time)

        logger.info('stop watering')
        relay.open()

    tweet("I poured successfully for {} intervals.".format(intervals))


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