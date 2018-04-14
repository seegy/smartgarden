#!/usr/bin/python
import RPi.GPIO as GPIO


class CustomRelay:

    def __init__(self, BCM_pin):
        self.pin = BCM_pin
        self.status_is_open = None
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.pin, GPIO.OUT)
        self.open()

    def close(self):
        GPIO.output(self.pin, GPIO.HIGH)
        self.status_is_open = False

    def open(self):
        GPIO.output(self.pin, GPIO.LOW)
        self.status_is_open = True

    def is_open(self):
        return self.status_is_open

