import ConfigParser
import logging
from logging.handlers import RotatingFileHandler
import tweepy
from logging_twitter.handler import TwitterHandler
import time
import sys, os
import uuid
import threading

pathname = os.path.dirname(sys.argv[0])

if not pathname:
    pathname = "."

# load config
Config = ConfigParser.ConfigParser()


def reload_config():
    if os.path.isfile(pathname + '/config.ini'):
        Config.read(pathname + '/config.ini')
    else:
        Config.read(pathname + '/config.ini.sample')


reload_config()

# Logger
app_name= Config.get('Watering-Server', 'app-name')
log_level= Config.get('Log', 'level')
log_file= Config.get('Log', 'file')
log_format= '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
logging.basicConfig(filename=log_file, level=logging.getLevelName(log_level))
logger = logging.getLogger(app_name)
fh = RotatingFileHandler(log_file, maxBytes=10000000, backupCount=5)
formatter = logging.Formatter(log_format)
fh.setFormatter(formatter)
fh.setLevel(logging.getLevelName(log_level))
logger.addHandler(fh)


# twitter stuff
tweet_api = None
tweet_enabled = Config.get('Twitter', 'enable').upper() == 'TRUE'

if tweet_enabled:
    CONSUMER_KEY = Config.get('Twitter', 'CONSUMER_KEY')
    CONSUMER_SECRET = Config.get('Twitter', 'CONSUMER_SECRET')
    ACCESS_KEY = Config.get('Twitter', 'ACCESS_KEY')
    ACCESS_SECRET = Config.get('Twitter', 'ACCESS_SECRET')
    auth = tweepy.OAuthHandler(CONSUMER_KEY, CONSUMER_SECRET)
    auth.set_access_token(ACCESS_KEY, ACCESS_SECRET)
    tweet_api = tweepy.API(auth)

    USER = Config.get('Twitter', 'DIRECT_MSG_USER')

    # Add Twitter logging handler
    handler = TwitterHandler(consumer_key=CONSUMER_KEY,
                             consumer_secret=CONSUMER_SECRET,
                             access_token_key=ACCESS_KEY,
                             access_token_secret=ACCESS_SECRET,
                             direct_message_user=USER)
    handler.setLevel(logging.ERROR)
    logger.addHandler(handler)


def tweet(msg):
    if tweet_enabled:
        msg = "{}\n({})\n{}".format(msg, time.strftime("%H:%M:%S", time.localtime()), str(uuid.uuid4())[:8])
        try:
            tweet_api.update_status(msg)
        except Exception,e:
            logger.error("Tweet went wrong: <{}> on tweet <{}> ".format(e, msg))


def synchronized(func):
    func.__lock__ = threading.Lock()

    def synced_func(*args, **kws):
        with func.__lock__:
            return func(*args, **kws)
    return synced_func
