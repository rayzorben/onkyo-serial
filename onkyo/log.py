import logging
import os
from datetime import datetime

USE_LOGFILE=False

approot = os.path.dirname(os.path.realpath(__file__))
logdir = os.path.join(approot, 'logs')
if not os.path.exists(logdir):
    os.makedirs(logdir)

if USE_LOGFILE:
    logfile = os.path.join(logdir, datetime.now().strftime("%Y-%m") + '.log')
    print('logfile: ', logfile)
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
        datefmt='%m-%d %H:%M',
        filename=logfile,
        filemode='w'
    )

console = logging.StreamHandler()
console.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(name)-12s: %(levelname)-8s %(message)s')
console.setFormatter(formatter)
logging.getLogger('').addHandler(console)
