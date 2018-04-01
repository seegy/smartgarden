#!/usr/bin/python
import smbus
import time, sys
import RPi.GPIO as GPIO

BUS_ADDRESS = 0x37
GPIO_SUPPLY_PIN = 21
STATUS_REG = 0x0c
MEASURE_REG = 0x09
CHANNEL_DISABLE_REG = 0x08
MODUS_REG = 0x0b
FIRST_INPUT_REG = 0x20
MEASURE_TIMES = 10
UPPER_MEASURE_LIMIT = 130

TIME_BETWEEN_POWER_AND_MEASURE= 0
WAIT_TIME_FOR_MEASURE_FINISH= 0
WAIT_TIME_AFTER_MEASURE= 0

MEASURE_OVERHEAD = 0.7692307692307692

MEASURE_FACTOR = UPPER_MEASURE_LIMIT / 100.
GPIO_SENSOR_SUPPLY_PINS = [ 20, 16, 12, 7, 8, 25, 24, 23 ]

# turn off stupid GPIO warnings
GPIO.setwarnings(False)
# set GIO-mode to pin numbers on dev board
GPIO.setmode(GPIO.BCM)
# set supply pin to output mode
GPIO.setup(GPIO_SUPPLY_PIN, GPIO.OUT)
# initialize low
GPIO.output(GPIO_SUPPLY_PIN, GPIO.LOW)

for i in GPIO_SENSOR_SUPPLY_PINS:
    GPIO.setup(i, GPIO.OUT)
    GPIO.output(i, GPIO.LOW)


def sensors_by_mask(sensor_mask):

    i = 0
    tmp_sensors = sensor_mask
    sensor_list = []

    while tmp_sensors:
        if 0x01 & tmp_sensors:
            sensor_list.append(i)
        i = i+1
        tmp_sensors = tmp_sensors >> 1

    return sensor_list


def read_sensors(sensors_mask):

    # turn supply on
    GPIO.output(GPIO_SUPPLY_PIN, GPIO.HIGH)

    sensor_list = sensors_by_mask(sensors_mask)
    measures = [0] * len(sensor_list)

    failed = False

    try:
        eeprom = smbus.SMBus(1)

        # start MODE 1 (8 inputs)
        eeprom.write_i2c_block_data(BUS_ADDRESS, MODUS_REG, [0x02])

        # open input channels
        eeprom.write_i2c_block_data(BUS_ADDRESS, CHANNEL_DISABLE_REG, [sensors_mask ^ 0xff])

        for t in range(MEASURE_TIMES):
            results = []

            for i in sensor_list:
                # turn on sensor supplys
                GPIO.output(GPIO_SENSOR_SUPPLY_PINS[i], GPIO.HIGH)

                time.sleep(TIME_BETWEEN_POWER_AND_MEASURE)

                # start single measure
                eeprom.write_i2c_block_data(BUS_ADDRESS, MEASURE_REG, [0x01])

                # wait until measure finishes
                while eeprom.read_byte_data(BUS_ADDRESS, STATUS_REG):
                    time.sleep(WAIT_TIME_FOR_MEASURE_FINISH)

                reg = FIRST_INPUT_REG  + i   # switch order because of hardware design
                results.append(eeprom.read_byte_data(BUS_ADDRESS, reg) / MEASURE_FACTOR)

                GPIO.output(GPIO_SENSOR_SUPPLY_PINS[i], GPIO.LOW)

                # turn off sensor supplys
                time.sleep(WAIT_TIME_AFTER_MEASURE)

            measures = [x + y for x, y in zip(measures, results)]

        # Zip single measures
        measures = [(x / y) - MEASURE_OVERHEAD for x, y in zip(measures, [MEASURE_TIMES] * len(sensor_list))]

        # filter negative measures
        measures = map(lambda x: x if x > 0 else 0, measures)

    except:
        print("WARNING: measure failed: {0}".format(sys.exc_info()[0]))
        failed = True
    finally:
        # turn supply off
        GPIO.output(GPIO_SUPPLY_PIN, GPIO.LOW)

        for i in GPIO_SENSOR_SUPPLY_PINS:
            GPIO.output(i, GPIO.LOW)

    return read_sensors(sensors_mask) if failed else zip(sensor_list, measures)


# print read_sensors(0x8f)