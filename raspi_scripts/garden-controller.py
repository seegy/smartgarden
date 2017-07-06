import crython
from random import randint
import requests
import subprocess
import grovepi
import pyowm

from shared import *

DEBUG = False


# class for sensors
class HumiditySensor:
    def __init__(self, pin, threshold):
        self.pin = pin
        self.threshold = threshold


# watering server connection
watering_url = Config.get('Watering-Server', 'url')
watering_port = Config.get('Watering-Server', 'port')
check_scheduler = Config.get('Garden-Controller', 'status-schedule')

morning_watering_job_scheduler = Config.get('Morning-Watering-Schedule', 'watering-scheduler')
evening_watering_job_scheduler = Config.get('Evening-Watering-Schedule', 'watering-scheduler')

# open weather map connection
owm_enabled = bool(Config.get('OpenWeatherMap', 'enable'))


# global tweet string for multi function level appending
tweet_string= ''


# calculate advice of how many intervals should be poured on delivered temperature
def get_temperature_interval_advice(temp):

    reload_config()
    lower_env_temp_limit = float(Config.get('OpenWeatherMap', 'lower_env_temp_limit'))
    upper_env_temp_limit = float(Config.get('OpenWeatherMap', 'upper_env_temp_limit'))
    temp_diff = upper_env_temp_limit - lower_env_temp_limit
    max_intervals = float(Config.get('OpenWeatherMap', 'max_intervals'))
    min_intervals = float(Config.get('OpenWeatherMap', 'min_intervals'))

    if temp >= upper_env_temp_limit:
        return max_intervals
    elif temp <= lower_env_temp_limit:
        return min_intervals

    return (((temp - lower_env_temp_limit) / temp_diff) * (max_intervals - min_intervals)) + min_intervals


def get_rain_interval_advice(rain):

    reload_config()
    rain_sum = 0

    if 'all' in rain:
        rain_sum += rain['all']
    else:
        return 0

    rain_pour_deduction_limit = float(Config.get('OpenWeatherMap', 'rain_pour_deduction_limit'))
    upper_env_rain_limit = float(Config.get('OpenWeatherMap', 'upper_env_rain_limit'))
    lower_env_rain_limit = float(Config.get('OpenWeatherMap', 'lower_env_rain_limit'))

    if rain_sum >= upper_env_rain_limit:
        return rain_pour_deduction_limit

    return ((rain_sum - lower_env_rain_limit) / upper_env_rain_limit ) * rain_pour_deduction_limit


# asks open weather map for max temperature of current day. if owm is disabled, it always returns 0
def get_today_weather():

    if owm_enabled:
        try:
            access_token = Config.get('OpenWeatherMap', 'TOKEN')
            owm = pyowm.OWM(access_token)
            forecast = owm.daily_forecast(Config.get('OpenWeatherMap', 'location'))
            return forecast.get_forecast().get(0)
        except Exception:
            raise requests.exceptions.ConnectionError("no OWM connection!")

    return 0


# read sensors from config
def get_sensors():
    sensors = []

    for each_section in Config.sections():
        if each_section.startswith('Humidity-Sensor'):
            sensors.append(HumiditySensor(int(Config.get(each_section, 'pin')),
                                          int(Config.get(each_section, 'threshold'))))
    return sensors


def measure_to_humidity(measure):
    upper_measure_limit = int(Config.get('Garden-Controller', 'upper-measure-limit'))
    lower_measure_limit = int(Config.get('Garden-Controller', 'lower-measure-limit'))
    return (float(measure) - lower_measure_limit) / (upper_measure_limit - lower_measure_limit) * 100


def check_sensor(sensor, threshold_factor):
    measure_sum = 0
    global tweet_string
    measure_count = int(Config.get('Garden-Controller', 'measure-count'))

    for x in range(0, measure_count):

        # wait between 2 measures
        if x > 0:
            time.sleep(0.1)

        # read sensor

        measure = None
        if not DEBUG:
            measure = grovepi.analogRead(sensor.pin)
        else:
            measure = randint((int(Config.get('Garden-Controller', 'upper-measure-limit'))
                               + int(Config.get('Garden-Controller', 'lower-measure-limit')))/2,
                              int(Config.get('Garden-Controller', 'upper-measure-limit')))
        measure_sum += measure

    final_measure = measure_sum / measure_count
    humidity = measure_to_humidity(final_measure)

    threshold = threshold_factor * float(sensor.threshold)
    out_string = "P{}, Hum.: {:.1f}/{:.1f}%".format(sensor.pin, humidity, threshold)
    logger.info(out_string)
    tweet_string += out_string + '\n'
    if humidity <= threshold:
        return True, humidity, threshold

    return False, humidity, threshold


# delivers the average difference threshold and dryer measures
def get_avg_hum_diff(sensor_results):

    def func(x, y):
        torf, hum, thres = y
        if torf:
            return x + thres - hum
        else:
            return x

    sensor_results.insert(0, 0)

    return reduce(func, sensor_results) / len(sensor_results)


def get_humidity_advice(avg_diff):

    reload_config()
    upper_hum_measure_limit = float(Config.get('OpenWeatherMap', 'upper_hum_measure_limit'))
    lower_hum_measure_interval_factor = float(Config.get('OpenWeatherMap', 'lower_hum_measure_interval_factor'))

    if avg_diff >= upper_hum_measure_limit:
        return 1.0

    return ((avg_diff / upper_hum_measure_limit) * (1 - lower_hum_measure_interval_factor)) + lower_hum_measure_interval_factor


def get_interval_advice(measures, or_pouring):

    if owm_enabled:
        try:
            weather = get_today_weather()
            temp = weather.get_temperature('celsius')['max']
            rain = weather.get_rain()

            interval = 0.0
            interval += get_temperature_interval_advice(temp)
            interval += get_rain_interval_advice(rain)

            hum_avg_diff = get_avg_hum_diff(measures)
            hum_factor = get_humidity_advice(hum_avg_diff)

            interval *= hum_factor

            return interval
        except requests.exceptions.ConnectionError:
            if DEBUG:
                print "no OWM connection!"

    return or_pouring


def start_watering_server():
    result = subprocess.Popen(["python", pathname + "/watering_server.py"])


def measure_and_watering(pouring_intervals, sensor_threshold_factor=1.0, with_advice=False):
    global tweet_string
    tweet_string= 'I measured:\n'

    sensors = get_sensors()
    job_sensors = sensors[:]

    # make sure there is a quorum
    if len(job_sensors) % 2 == 0:
        del job_sensors[randint(0, len(job_sensors) - 1)]

    # check sensors
    measures = []
    for sensor in job_sensors:
        d= check_sensor(sensor, sensor_threshold_factor)
        measures.append(d)

    yes_count = len([torf for torf, _, _ in measures if torf])

    if yes_count > len(job_sensors) / 2:
        logger.info('Yes! Water it!')

        if with_advice:
            pouring_intervals = get_interval_advice(measures, pouring_intervals)

        tweet_string += 'I\'ll pour!'

        try:
            url = 'http://{}:{}/pour/{:.2f}'.format(watering_url, watering_port, pouring_intervals)
            if not DEBUG:
                #requests.put(url)
                print url
                logger.info('Send watering request.')
            else:
                print('request to: {}'.format(url))

        except requests.exceptions.ConnectionError:
            logger.warning("No watering server! restart watering server...")
            start_watering_server()
            time.sleep(1)
            measure_and_watering(pouring_intervals, sensor_threshold_factor)

    else:
        logger.info('No! No water!')
        tweet_string += 'I\'ll not pour!'

    if DEBUG:
        print tweet_string
    else:
        tweet(tweet_string)


@crython.job(expr=morning_watering_job_scheduler)
def morning_schedule():
    reload_config()
    pour_intervals= Config.get('Morning-Watering-Schedule', 'watering-pour')
    sensor_threshold_factor = float(Config.get('Morning-Watering-Schedule', 'sensor-threshold-factor'))
    measure_and_watering(pour_intervals, sensor_threshold_factor, True)


@crython.job(expr=evening_watering_job_scheduler)
def evening_schedule():
    reload_config()
    pour_intervals= Config.get('Evening-Watering-Schedule', 'watering-pour')
    sensor_threshold_factor = float(Config.get('Evening-Watering-Schedule', 'sensor-threshold-factor'))
    measure_and_watering(pour_intervals, sensor_threshold_factor)


@crython.job(expr=Config.get('Morning-Support-Watering-Schedule', 'watering-scheduler'))
def morning_support_schedule():
    reload_config()
    pour_intervals= Config.get('Morning-Support-Watering-Schedule', 'watering-pour')
    sensor_threshold_factor = float(Config.get('Morning-Support-Watering-Schedule', 'sensor-threshold-factor'))
    measure_and_watering(pour_intervals, sensor_threshold_factor)


@crython.job(expr=check_scheduler)
def check_status_schedule():
    reload_config()
    global tweet_string
    tweet_string= 'I measured:\n'

    sensors = get_sensors()
    job_sensors = sensors[:]

    # check sensors
    decisions = []
    for sensor in job_sensors:
        d, _, _ = check_sensor(sensor, 1.0)
        decisions.append(d)

    if DEBUG:
        print tweet_string
    else:
        tweet(tweet_string)


if __name__ == '__main__':

    if not DEBUG:
        time.sleep(5)

    watering_server_available = False

    try:
        if not DEBUG:
            r = requests.get('http://' + watering_url + ':' + watering_port + '/status')
            if r.status_code == 200:
                watering_server_available = True

    except requests.exceptions.ConnectionError:
        pass

    if not watering_server_available and not DEBUG:
        logger.warning("No watering server found! Starting watering server...")
        start_watering_server()

    crython.start()

    logger.info("Garden Controller started up! Morning schedule: {}. Evening schedule: {}".format(morning_watering_job_scheduler, evening_watering_job_scheduler))

    if DEBUG:
        print "I'm up now!"
    else:
        tweet("I'm up now!")
    while True:
        time.sleep(1)