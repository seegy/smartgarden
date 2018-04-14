#!/usr/bin/env bash

sudo apt-get install -y pip
sudo pip install flask ConfigParser tweepy python-logging-twitter crython pyowm traceback

sudo touch /var/log/garden.log
sudo chmod +wx /var/log
sudo chown pi:pi /var/log/garden.log