import crython
from random import randint
import requests
import subprocess
import grovepi

from shared import *


# class for sensors
class HumiditySensor:
    def __init__(self, pin, threshold):
        self.pin = pin
        self.threshold = threshold


# read sensors from config
sensors = []

# watering server connection
watering_url = Config.get('Watering-Server', 'url')
watering_port = Config.get('Watering-Server', 'port')

# own stuff
watering_job_scheduler = Config.get('Garden-Controller', 'watering-scheduler')

# global tweet string for multi function level appending
tweet_string= ''


def reset_sensors():
    global sensors
    sensors = []
    for each_section in Config.sections():
        if each_section.startswith('Humidity-Sensor'):
            sensors.append(HumiditySensor(int(Config.get(each_section, 'pin')),
                                          int(Config.get(each_section, 'threshold'))))


def measure_to_humidity(measure):
    upper_measure_limit = int(Config.get('Garden-Controller', 'upper-measure-limit'))
    lower_measure_limit = int(Config.get('Garden-Controller', 'lower-measure-limit'))
    return (float(measure) - lower_measure_limit) / (upper_measure_limit - lower_measure_limit) * 100


def check_sensor(sensor):
    measure_sum = 0
    global tweet_string

    measure_count = int(Config.get('Garden-Controller', 'measure-count'))

    for x in range(0, measure_count):
        # read sensor
        measure = grovepi.analogRead(sensor.pin)
        measure_sum += measure

    final_measure = measure_sum / measure_count
    humidity = measure_to_humidity(final_measure)

    out_string = "P: {}, M: {:.1f}, T: {}".format(sensor.pin, humidity, sensor.threshold)
    logger.info(out_string)
    tweet_string += out_string + '\n'

    if humidity <= sensor.threshold:
        return True

    return False


def start_watering_server():
    result = subprocess.Popen(["python", pathname + "/watering_server.py"])


@crython.job(expr=watering_job_scheduler)
def watering():
    global tweet_string

    reset_sensors()

    job_sensors = sensors[:]

    tweet_string= 'I measured:\n'

    # make sure there is a quorum
    if len(job_sensors) % 2 == 0:
        del job_sensors[randint(0, len(job_sensors) - 1)]

    # check sensors
    decisions = []
    for sensor in job_sensors:
        decisions.append(check_sensor(sensor))

    yes_count = len([e for e in decisions if e])

    if yes_count > len(job_sensors) / 2:
        logger.info('Yes! Water it!')
        tweet_string += 'I\'ll pour!'

        try:
            requests.put('http://' + watering_url + ':' + watering_port + '/pour/' + Config.get('Garden-Controller', 'watering-pour'))
            logger.info('Send watering request.')
        except requests.exceptions.ConnectionError:
            logger.warning("No watering server! restart watering server...")
            start_watering_server()
            time.sleep(1)
            watering()

    else:
        logger.info('No! No water!')
        tweet_string += 'I\'ll not pour!'

    tweet(tweet_string)


if __name__ == '__main__':
    time.sleep(10)

    watering_server_available = False

    try:
        r = requests.get('http://' + watering_url + ':' + watering_port + '/status')
        if r.status_code == 200:
            watering_server_available = True

    except requests.exceptions.ConnectionError:
        pass

    if not watering_server_available:
        logger.warning( "No watering server found! Starting watering server...")
        start_watering_server()

    crython.start()

    logger.info("Garden Controller started up!")
    tweet("I'm up now!")
    while True:
        time.sleep(1)