import threading
import re
import time
from .log import logging
from .event import Event
from serial import Serial
from yaml import load, dump

logger = logging.getLogger('onkyo-serial')
logger.setLevel(logging.DEBUG)

SOURCES = {
    "00": "VIDEO1,VCR/DVR,STB/DVR",
    "01": "VIDEO2,CBL/SAT",
    "02": "VIDEO3,GAME/TV,GAME,GAME1",
    "03": "VIDEO4,AUX1,AUX",
    "04": "VIDEO5,AUX2,GAME2",
    "05": "VIDEO6,PC",
    "06": "VIDEO7",
    "07": "HIDDEN1,EXTRA1",
    "08": "HIDDEN2,EXTRA2",
    "09": "HIDDEN3,EXTRA3",
    "10": "DVD,BD/DVD",
    "20": "TAPE,TV/TAPE",
    "21": "TAPE2",
    "22": "PHONO",
    "23": "CD,TV/CD",
    "24": "FM",
    "25": "AM",
    "26": "TUNER",
    "27": "MUSIC SERVER,P4S,DLNA*2",
    "28": "INTERNET RADIO,IRADIO FAVORITE*3",
    "29": "USB/USB (FRONT)",
    "2A": "USB (REAR)",
    "2B": "NETWORK,NET",
    "2C": "USB (TOGGLE)",
    "2D": "AIPLAY",
    "40": "UNIVERSALPORT",
    "30": "MULTICH",
    "31": "XM*1",
    "32": "SIRIUS*1",
    "33": "DAB*5"
}


class OnkyoBackgroundWorker(threading.Thread):
    """Listens for incoming messages from the serial port and updates status in the background."""
    state_changed = Event()

    def __init__(self, port, commands, sources):
        """Initialize the thread."""
        threading.Thread.__init__(self)
        self.daemon = True
        self._port = port
        self._commands = commands
        self._pattern = '!1([A-Z]{3})(.{2})?'
        self._sources = sources

        self.messages = {
            'power': self.power,
            'volume': self.volume,
            'source': self.source,
            'mute': self.mute
        }

    def _readline(self):
        """Read a single line from the serial port suffixed with a ^Z."""
        eol = b'\x1a'
        leneol = len(eol)
        line = bytearray()
        while True:
            cread = self._port.read(1)
            if cread:
                line += cread
                if line[-leneol:] == eol:
                    break
            else:
                break

        return bytes(line)

    def process(self, message, value):
        """Call the process handler for a specific message."""
        return self.messages[message](value)

    #pylint: disable=R
    def power(self, value):
        """Process power state."""
        return value == '01'

    def mute(self, value):
        """Process mute status."""
        return value == '01'

    def volume(self, value):
        """Process volume state."""
        return int(value, 16)

    def source(self, value):
        """Process the current input source."""
        return self._sources[value]

    def run(self):
        """Override run handler for the thread."""
        logger.info('Starting background worker for Onkyo Serial Device')
        while True:
            out = self._readline().decode('utf-8')
            match = re.search(self._pattern, out)
            if match:
                cmd = match.group(1)
                val = match.group(2)
                zone = None
                prop = None

                #pylint: disable=C,W
                for z, c in self._commands.items():
                    for child_key, child_cmd in self._commands[z]['commands'].items():
                        if child_cmd == cmd:
                            zone = z
                            prop = child_key
                            break

                if zone and prop:
                    val = self.process(prop, val)
                    logger.debug('zone: %s, property: %s, value: %s', zone, prop, val)
                    self.state_changed(zone, prop, val)

class OnkyoSerial():
    _serial = None
    _worker_thread = None

    @property
    def _port(self):
        """Serial port."""
        return type(self)._serial

    @property
    def _worker(self):
        """Worker thread."""
        return type(self)._worker_thread

    def __init__(self, config, zone, sources=SOURCES, port='/dev/ttyUSB0', baudrate=9600, timeout=10, rtscts=0, xonxoff=0):
        """Initialize an instance of the Onkyo class to manage communication with the Onkyo receiver."""
        self._sources = sources
        self._reverse_sources = {value: key for key, value in sources.items()}
        self._zone = zone
        self._queries = list(config[zone]['queries'].values())
        self._commands = config[zone]['commands']

        if not self._port:
            OnkyoSerial._serial = Serial(port, baudrate=baudrate, timeout=timeout, rtscts=rtscts, xonxoff=xonxoff)

        if not self._worker:
            OnkyoSerial._worker_thread = OnkyoBackgroundWorker(self._port, config, sources)
            OnkyoSerial._worker_thread.start()

        OnkyoSerial._worker_thread.state_changed += self.state_change
        # initial state
        self._power = False
        self._volume = 0
        self._source = None
        self._mute = False

    def command(self, command):
        """Write a command to an open serial port."""
        if self._port.isOpen():
            out = ''.join(['!1', command, '\r'])
            logger.debug('Writing command: %s', out)
            self._port.write(str.encode(out))
        else:
            logger.debug('Attempt to write command when port is not open.')

    def update(self):
        """Post an update to the port and let the background worker signal any updates."""
        for query in self._queries:
            self.command(query)

    def state_change(self, zone, prop, value):
        """Handle a state change from the worker thread."""
        if zone == self._zone:
            logger.info("state change [{z}] {k}={v}".format(z=zone, k=prop, v=value))
            self.__dict__['_' + prop] = value

    def power_on(self):
        """Send power on command."""
        if 'power' in self._commands:
            self.command(self._commands['power'] + '01')

    def power_off(self):
        """Send power off command."""
        if 'power' in self._commands:
            self.command(self._commands['power'] + '00')

    def mute_on(self):
        """Send mute command."""
        if 'mute' in self._commands:
            self.command(self._commands['mute'] + '01')

    def mute_off(self):
        """Send mute off command."""
        if 'mute' in self._commands:
            self.command(self._commands['mute'] + '00')

    def volume(self, level):
        """Send volume level command."""
        if 'volume' in self._commands:
            self.command(self._commands['volume'] + format(level, '02X'))

    def source(self, input):
        """Send set input source command."""
        if 'source' in self._commands:
            sel = self._reverse_sources.get(input.upper(), None)
            if not sel:
                for key, val in self._reverse_sources.items():
                    if input.upper() in key.split(','):
                        sel = self._reverse_sources[key]

            if sel:
                self.command(self._commands['source'] + sel)


if __name__ == '__main__':

    config = load("""
master:
    commands:
        power:  'PWR'
        volume: 'MVL'
        source: 'SLI'
        mute:   'AMT'
    queries:
        power:  'PWRQSTN'
        volume: 'MVLQSTN'
        source: 'SLIQSTN'
        mute:   'AMTQSTN'
zone2:
    commands:
        power:  'ZPW'
        volume: 'ZVL'
        source: 'SLZ'
        mute:   'ZMT'
    queries:
        power:  'ZPWQSTN'
        volume: 'SVLQSTN'
        source: 'SLZQSTN'
        mute:   'ZMTQSTN'
""")

    master = OnkyoSerial(config, 'master')
    zone2 = OnkyoSerial(config, 'zone2')

    while True:
        master.update()
        zone2.update()
        time.sleep(5)
        logger.info('power on')
        master.power_on()
        time.sleep(1)
        logger.info('mute on')
        master.mute_on()
        time.sleep(1)
        logger.info('mute off')
        master.mute_off()
        time.sleep(1)
        logger.info('volume')
        master.volume(55)
        time.sleep(1)
        logger.info('source')
        master.source('AUX')
        time.sleep(1)
        logger.info('power off')
        master.power_off()
        time.sleep(1)



        logger.info('power on')
        zone2.power_on()
        time.sleep(1)
        logger.info('power off')
        zone2.power_off()
        time.sleep(1)
        time.sleep(3)
        break