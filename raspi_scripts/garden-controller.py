import crython
from random import randint, uniform
import requests
import subprocess
import pyowm
import libs.ADC128D818
from shared import *

DEBUG = False


# class for sensors
class HumiditySensor:
    def __init__(self, pin, threshold):
        self.pin = pin
        self.threshold = threshold

        self.measure = None
        self.humidity = None
        self.vote_for_watering = False
        self.measure_string = None


# watering server connection
watering_url = Config.get('Watering-Server', 'url')
watering_port = Config.get('Watering-Server', 'port')
check_scheduler = Config.get('Garden-Controller', 'status-schedule')

morning_watering_job_scheduler = Config.get('Morning-Watering-Schedule', 'watering-scheduler')
evening_watering_job_scheduler = Config.get('Evening-Watering-Schedule', 'watering-scheduler')

# open weather map connection
owm_enabled = bool(Config.get('OpenWeatherMap', 'enable'))


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
def get_weather_of_today():

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
def read_sensors_from_config(sensor_threshold_factor=1.0):
    sensors = []

    for each_section in Config.sections():
        if each_section.startswith('Humidity-Sensor'):
            sensors.append(HumiditySensor(int(Config.get(each_section, 'pin')),
                                          int(Config.get(each_section, 'threshold')) * sensor_threshold_factor))
    return sensors


def get_sensor_mask_by_sensors(sensors):
    result = 0
    for sensor in sensors:
        result += 1 << sensor.pin
    return result


def measure_to_humidity(measure):
    upper_measure_limit = float(Config.get('Garden-Controller', 'upper-measure-limit'))
    lower_measure_limit = float(Config.get('Garden-Controller', 'lower-measure-limit'))
    return (float(measure) - lower_measure_limit) / (upper_measure_limit - lower_measure_limit) * 100


def validate_measure(sensor):
    sensor.humidity = measure_to_humidity(sensor.measure)
    sensor.vote_for_watering = sensor.humidity <= sensor.threshold
    sensor.measure_string = "P{}, Hum.: {:.1f}/{:.1f}".format(sensor.pin, sensor.humidity, sensor.threshold)
    logger.info(sensor.measure_string)


# delivers the average difference threshold and dryer measures
def get_avg_hum_diff(sensors):

    def func(x, sensor):
        if sensor.vote_for_watering:
            return x + sensor.threshold - sensor.humidity
        else:
            return x

    sensors.insert(0, 0)
    return reduce(func, sensors) / len(sensors)


def get_humidity_advice(avg_diff):

    reload_config()
    upper_hum_measure_limit = float(Config.get('OpenWeatherMap', 'upper_hum_measure_limit'))
    lower_hum_measure_interval_factor = float(Config.get('OpenWeatherMap', 'lower_hum_measure_interval_factor'))

    if avg_diff >= upper_hum_measure_limit:
        return 1.0

    return ((avg_diff / upper_hum_measure_limit) * (1 - lower_hum_measure_interval_factor)) + lower_hum_measure_interval_factor


def get_interval_advice(sensors, or_pouring):

    if owm_enabled:
        try:
            weather = get_weather_of_today()
            temp = weather.get_temperature('celsius')['max']
            rain = weather.get_rain()

            interval = float(Config.get('OpenWeatherMap', 'initial_value'))
            interval += get_temperature_interval_advice(temp)
            interval += get_rain_interval_advice(rain)

            hum_avg_diff = get_avg_hum_diff(sensors)
            hum_factor = get_humidity_advice(hum_avg_diff)

            interval *= hum_factor

            return interval
        except requests.exceptions.ConnectionError as e:
            if DEBUG:
                print "no OWM connection!"
            else:
                logger.warning("no OWM connection: ", exc_info=True)

    return or_pouring


def start_watering_server():
    subprocess.Popen(["python", pathname + "/watering_server.py"])


def get_random_measure():
    upper_measure_limit = float(Config.get('Garden-Controller', 'upper-measure-limit'))
    lower_measure_limit = float(Config.get('Garden-Controller', 'lower-measure-limit'))
    return uniform((upper_measure_limit + lower_measure_limit)/2, upper_measure_limit)


def generate_debug_measures(sensors):
    result = []
    for sensor in sensors:
        result.append([sensor.pin, get_random_measure()])
    return result


def merge_sensors_and_measures(sensors, measures):
    result = []
    for sensor in sensors:
        for measure in measures:
            if sensor.pin == measure[0]:
                sensor.measure = measure[1]
                result.append(sensor)
                break
    return result


@synchronized
def do_measure(sensors):
    # check sensors
    sensor_mask = get_sensor_mask_by_sensors(sensors)

    if not DEBUG:
        measure_times = int(Config.get('Garden-Controller', 'measure-count'))
        measures = libs.ADC128D818.ADC128D818(measure_times=measure_times).read_sensors(sensor_mask)
    else:
        measures = generate_debug_measures(sensors)

    merge_sensors_and_measures(sensors, measures)

    for sensor in sensors:
        validate_measure(sensor)


def create_notification(sensors, will_pouring, pouring_intervals):
    tweet_string = 'I measured:\n'

    for sensor in sensors:
        tweet_string += sensor.measure_string + '\n'

    if will_pouring:
        tweet_string += 'I\'ll pour for {:.1f} intervals!'.format(pouring_intervals)
    else:
        tweet_string += 'I\'ll not pour!'

    if DEBUG:
        print tweet_string
    else:
        tweet(tweet_string)


def send_pour_request(pouring_intervals):
    try:
        url = 'http://{}:{}/pour/{:.2f}'.format(watering_url, watering_port, pouring_intervals)
        if not DEBUG:
            requests.put(url)
            logger.info('Send watering request.')
        else:
            print('request to: {}'.format(url))

        return True

    except requests.exceptions.ConnectionError:
        logger.warning("No watering server! restart watering server...")
        start_watering_server()
        time.sleep(1)

    return False


def measure_and_watering(pouring_intervals, sensor_threshold_factor=1.0, with_advice=False):

    pouring_intervals = float(pouring_intervals)

    sensors = read_sensors_from_config(sensor_threshold_factor)
    job_sensors = sensors[:]  # made new list mutable, TODO should be checked if necessary

    # make sure there is a quorum
    if len(job_sensors) % 2 == 0:
        del job_sensors[randint(0, len(job_sensors) - 1)]

    do_measure(job_sensors)

    yes_count = len([True for sensor in job_sensors if sensor.vote_for_watering])

    if yes_count > len(job_sensors) / 2:
        logger.info('Yes! Water it!')

        if with_advice:
            pouring_intervals = get_interval_advice(sensor, pouring_intervals)

            create_notification(job_sensors, True, pouring_intervals)

            if not send_pour_request(pouring_intervals):
                measure_and_watering(pouring_intervals, sensor_threshold_factor)

    else:
        logger.info('No! No water!')
        create_notification(job_sensors, False, 0)


@crython.job(expr=morning_watering_job_scheduler)
def morning_schedule():
    try:
        reload_config()
        pour_intervals = Config.get('Morning-Watering-Schedule', 'watering-pour')
        sensor_threshold_factor = float(Config.get('Morning-Watering-Schedule', 'sensor-threshold-factor'))
        measure_and_watering(pour_intervals, sensor_threshold_factor, True)
    except Exception as e:
        logger.exception(e)


@crython.job(expr=evening_watering_job_scheduler)
def evening_schedule():
    try:
        reload_config()
        pour_intervals = Config.get('Evening-Watering-Schedule', 'watering-pour')
        sensor_threshold_factor = float(Config.get('Evening-Watering-Schedule', 'sensor-threshold-factor'))
        measure_and_watering(pour_intervals, sensor_threshold_factor)
    except Exception as e:
        logger.exception(e)


@crython.job(expr=Config.get('Morning-Support-Watering-Schedule', 'watering-scheduler'))
def morning_support_schedule():
    try:
        reload_config()
        pour_intervals = Config.get('Morning-Support-Watering-Schedule', 'watering-pour')
        sensor_threshold_factor = float(Config.get('Morning-Support-Watering-Schedule', 'sensor-threshold-factor'))
        measure_and_watering(pour_intervals, sensor_threshold_factor)
    except Exception as e:
        logger.exception(e)


@crython.job(expr=check_scheduler)
def check_status_schedule():
    reload_config()

    sensors = read_sensors_from_config()
    job_sensors = sensors[:]

    # check sensors
    do_measure(job_sensors)


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