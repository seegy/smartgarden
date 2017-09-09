#!/usr/bin/python

sensors = 0x1f

i = 0
tmp_sensors = sensors
sensor_list = []

while tmp_sensors:
    if 0x01 & tmp_sensors:
        sensor_list.append(i)

    i = i+1
    tmp_sensors = tmp_sensors >> 1

print sensor_list
