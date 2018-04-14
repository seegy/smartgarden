#!/usr/bin/python
import smbus
import time, sys
import RPi.GPIO as GPIO


class ADC128D818:

    BUS_ADDRESS = 0x37
    STATUS_REG = 0x0c
    MEASURE_REG = 0x09
    CHANNEL_DISABLE_REG = 0x08
    MODE_REG = 0x0b
    FIRST_INPUT_REG = 0x20

    MEASURE_TIMES = 10
    UPPER_MEASURE_LIMIT = 130
    MEASURE_OVERHEAD = 0.7692307692307692
    MEASURE_FACTOR = UPPER_MEASURE_LIMIT / 100.

    TIME_BETWEEN_POWER_AND_MEASURE= 0
    WAIT_TIME_FOR_MEASURE_FINISH= 0
    WAIT_TIME_AFTER_MEASURE= 0

    GPIO_SUPPLY_PIN = 21
    GPIO_SENSOR_SUPPLY_PINS = [20, 16, 12, 7, 8, 25, 24, 23]

    def __init__(self, gpio_supply_pin=GPIO_SUPPLY_PIN, gpio_sensor_supply_pins=GPIO_SENSOR_SUPPLY_PINS, measure_times=MEASURE_TIMES):
        self.gpio_supply_pin = gpio_supply_pin
        self.gpio_sensor_supply_pins = gpio_sensor_supply_pins
        self.measure_times = measure_times

        # turn off stupid GPIO warnings
        GPIO.setwarnings(False)
        # set GIO-mode to pin numbers on dev board
        GPIO.setmode(GPIO.BCM)
        # set supply pin to output mode
        GPIO.setup(self.gpio_supply_pin, GPIO.OUT)
        # initialize low
        GPIO.output(self.gpio_supply_pin, GPIO.LOW)

        for i in self.gpio_sensor_supply_pins:
            GPIO.setup(i, GPIO.OUT)
            GPIO.output(i, GPIO.LOW)

    def sensors_by_mask(self, sensor_mask):
        i = 0
        tmp_sensors = sensor_mask
        sensor_list = []

        while tmp_sensors:
            if 0x01 & tmp_sensors:
                sensor_list.append(i)
            i = i+1
            tmp_sensors = tmp_sensors >> 1

        return sensor_list

    def read_sensors(self, sensors_mask):
        # turn supply on
        GPIO.output(self.gpio_supply_pin, GPIO.HIGH)

        sensor_list = self.sensors_by_mask(sensors_mask)
        measures = [0] * len(sensor_list)

        failed = False

        try:
            eeprom = smbus.SMBus(1)
            # start MODE 1 (8 inputs)
            eeprom.write_i2c_block_data(ADC128D818.BUS_ADDRESS, ADC128D818.MODE_REG, [0x02])
            # open input channels
            eeprom.write_i2c_block_data(ADC128D818.BUS_ADDRESS, ADC128D818.CHANNEL_DISABLE_REG, [sensors_mask ^ 0xff])

            for t in range(self.measure_times):
                results = []

                for i in sensor_list:
                    # turn on sensor supplies
                    GPIO.output(self.gpio_sensor_supply_pins[i], GPIO.HIGH)
                    time.sleep(ADC128D818.TIME_BETWEEN_POWER_AND_MEASURE)

                    # start single measure
                    eeprom.write_i2c_block_data(ADC128D818.BUS_ADDRESS, ADC128D818.MEASURE_REG, [0x01])

                    # wait until measure finishes
                    while eeprom.read_byte_data(ADC128D818.BUS_ADDRESS, ADC128D818.STATUS_REG):
                        time.sleep(ADC128D818.WAIT_TIME_FOR_MEASURE_FINISH)

                    reg = ADC128D818.FIRST_INPUT_REG + i   # switch order because of hardware design
                    results.append(eeprom.read_byte_data(ADC128D818.BUS_ADDRESS, reg) / ADC128D818.MEASURE_FACTOR)

                    # turn off sensor supplies
                    GPIO.output(ADC128D818.GPIO_SENSOR_SUPPLY_PINS[i], GPIO.LOW)
                    time.sleep(ADC128D818.WAIT_TIME_AFTER_MEASURE)

                measures = [x + y for x, y in zip(measures, results)]

            # Zip single measures
            measures = [(x / y) - ADC128D818.MEASURE_OVERHEAD for x, y in zip(measures, [ADC128D818.MEASURE_TIMES] * len(sensor_list))]
            # filter negative measures
            measures = map(lambda x: x if x > 0 else 0, measures)

        except:
            print("WARNING: measure failed: {0}".format(sys.exc_info()[0]))
            failed = True
        finally:
            # turn supply off
            GPIO.output(self.gpio_supply_pin, GPIO.LOW)

            for i in self.gpio_sensor_supply_pins:
                GPIO.output(i, GPIO.LOW)

        return self.read_sensors(sensors_mask) if failed else zip(sensor_list, measures)


#print ADC128D818().read_sensors(0x8f)