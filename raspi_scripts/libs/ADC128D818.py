#!/usr/bin/python
import smbus
import time, sys
import RPi.GPIO as GPIO

GPIO_SUPPLY_PIN = 21
STATUS_REG = 0x0c
MEASURE_REG = 0x09
CHANNEL_DISABLE_REG = 0x08
MODUS_REG = 0x0b
FIRST_INPUT_REG = 0x20
MEASURE_TIMES = 15

GPIO_SENSOR_SUPPLY_PINS = [23, 24, 25, 12, 16, 20, 21, 26]

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


def read_sensors(sensors):

    # turn supply on
    GPIO.output(GPIO_SUPPLY_PIN, GPIO.HIGH)

    sensor_list = sensors_by_mask(sensors)
    measures = [0] * len(sensor_list)

    for i in sensor_list:
        print GPIO_SENSOR_SUPPLY_PINS[i]
        GPIO.output(GPIO_SENSOR_SUPPLY_PINS[i], GPIO.HIGH)

    try:

        eeprom = smbus.SMBus(1)
        address = 0x1d

        # start MODE 1 (8 inputs)
        eeprom.write_i2c_block_data(address, MODUS_REG, [0x02])

        # open input channels
        eeprom.write_i2c_block_data(address, CHANNEL_DISABLE_REG, [sensors ^ 0xff])

        for t in range(MEASURE_TIMES):

            # start single measure
            eeprom.write_i2c_block_data(address, MEASURE_REG, [0x01])

            # wait until measure finishes
            while eeprom.read_byte_data(address, STATUS_REG):
                time.sleep(0.01)

            results = []

            # gather measure value of each sensor
            for i in sensor_list:
                reg = FIRST_INPUT_REG + i
                results.append(eeprom.read_byte_data(address, reg))

            measures = [x + y for x, y in zip(measures, results)]

            measures.append(results)
            time.sleep(0.1)

        measures = [x / y for x, y in zip(measures, [MEASURE_TIMES] * len(sensor_list))]

    except:
        pass

    # turn supply off
    GPIO.output(GPIO_SUPPLY_PIN, GPIO.LOW)

    for i in GPIO_SENSOR_SUPPLY_PINS:
        GPIO.output(i, GPIO.LOW)

    return zip(sensor_list, measures)


def read_sensors2(sensors_mask):

    # turn supply on
    GPIO.output(GPIO_SUPPLY_PIN, GPIO.HIGH)

    sensor_list = sensors_by_mask(sensors_mask)
    measures = [0] * len(sensor_list)

    failed = False

    try:
        eeprom = smbus.SMBus(1)
        address = 0x1d

        # start MODE 1 (8 inputs)
        eeprom.write_i2c_block_data(address, MODUS_REG, [0x02])

        # open input channels
        eeprom.write_i2c_block_data(address, CHANNEL_DISABLE_REG, [sensors_mask ^ 0xff])

        for t in range(MEASURE_TIMES):

            results = []

            for i in sensor_list:
                GPIO.output(GPIO_SENSOR_SUPPLY_PINS[i], GPIO.HIGH)

                time.sleep(0.001)

                # start single measure
                eeprom.write_i2c_block_data(address, MEASURE_REG, [0x01])

                # wait until measure finishes
                while eeprom.read_byte_data(address, STATUS_REG):
                    time.sleep(0.001)

                GPIO.output(GPIO_SENSOR_SUPPLY_PINS[i], GPIO.LOW)

                reg = FIRST_INPUT_REG + i
                results.append(eeprom.read_byte_data(address, reg))

            measures = [x + y for x, y in zip(measures, results)]
            #print results
            #print measures
            #print("###")

        measures = [x / y for x, y in zip(measures, [MEASURE_TIMES] * len(sensor_list))]

    except:
        print("WARNING: measure failed: ", sys.exc_info()[0])
        failed = True
    finally:
        # turn supply off
        GPIO.output(GPIO_SUPPLY_PIN, GPIO.LOW)

        for i in GPIO_SENSOR_SUPPLY_PINS:
            GPIO.output(i, GPIO.LOW)



    return read_sensors2(sensors_mask) if failed else zip(sensor_list, measures)


print read_sensors2(0x1f)
