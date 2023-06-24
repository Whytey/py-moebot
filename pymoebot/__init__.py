import logging
import threading

import tinytuya

_log = logging.getLogger("pymoebot")


class MoeBot:

    def __init__(self, device_id: str, device_ip: str, local_key: str) -> None:
        self.__id = device_id
        self.__ip = device_ip
        self.__key = local_key

        self.__device = tinytuya.Device(self.__id, self.__ip, self.__key)
        self.__device.set_version(3.3)
        self.__device.set_socketPersistent(True)

        self.__thread = threading.Thread(target=self.listen)
        self.__thread.start()
        self.__shutdown = threading.Event()

        self.__listeners = []

        self.__battery = None
        self.__state = None
        self.__emergency_state = None
        self.__mow_in_rain = None
        self.__mow_time = None
        self.__work_mode = None

    def __parse_payload(self, data) -> bool:
        if data is None or 'Err' in data or 'dps' not in data:
            _log.error("Error from device: %r" % data)
            return False

        _log.debug("Parsing data from device: %r" % data)
        dps = data['dps']
        if '6' in dps:
            self.__battery = dps['6']
        if '101' in dps:
            self.__state = dps['101']
        if '103' in dps:
            self.__emergency_state = dps['103']
        if '104' in dps:
            self.__mow_in_rain = dps['104']
        if '105' in dps:
            self.__mow_time = dps['105']
        if '114' in dps:
            self.__work_mode = dps['114']

        return True

    # def __query_state(self):
    #     _log.debug(" > Send Request for Status < ")
    #     payload = self.__device.generate_payload(tinytuya.DP_QUERY)
    #     self.__device.send(payload)

    def listen(self):
        _log.debug(" > Send Request for Status < ")
        payload = self.__device.generate_payload(tinytuya.DP_QUERY)
        self.__device.send(payload)

        _log.debug(" > Begin Monitor Loop <")
        while True:
            if self.__shutdown.is_set():
                _log.debug("Thread has been shutdown, exiting listen loop")
                break
            # See if any data is available
            data = self.__device.receive()
            if data is not None:
                _log.debug("Received Payload: %r", data, exc_info=1)

                self.__parse_payload(data)
                for listener in self.__listeners:
                    listener(data)

            # Send keepalive heartbeat
            payload = self.__device.generate_payload(tinytuya.HEART_BEAT)
            self.__device.send(payload)

    def add_listener(self, listener) -> None:
        self.__listeners.append(listener)

    def unlisten(self) -> None:
        _log.debug("Unlistening to MoeBot")
        self.__shutdown.set()
        self.__thread.join()

    @property
    def id(self) -> str:
        return self.__id

    @property
    def mow_time(self) -> int:
        return self.__mow_time

    @mow_time.setter
    def mow_time(self, mow_time: int):
        result = self.__device.set_value(105, mow_time)
        self.__parse_payload(result)

    @property
    def mow_in_rain(self) -> bool:
        return self.__mow_in_rain

    @mow_in_rain.setter
    def mow_in_rain(self, mow_in_rain: bool):
        result = self.__device.set_value(104, mow_in_rain)
        self.__parse_payload(result)

    @property
    def battery(self) -> int:
        return self.__battery

    @property
    def state(self) -> str:
        return self.__state

    @property
    def emergency_state(self) -> str:
        return self.__emergency_state

    @property
    def work_mode(self) -> str:
        return self.__work_mode

    def start(self, spiral=False) -> None:
        _log.debug("Attempting to start mowing: %r", self.__state)
        if self.__state in ("STANDBY", "PAUSED", "CHARGING"):
            if self.__state == "PAUSED":
                _log.debug("ContinueWork")
                result = self.__device.set_value(115, "ContinueWork")
            elif not spiral:
                _log.debug("StartMowing")
                result = self.__device.set_value(115, "StartMowing")
            else:
                _log.debug("StartFixedMowing")
                result = self.__device.set_value(115, "StartFixedMowing")
            self.__parse_payload(result)
        else:
            _log.error("Unable to start due to current state: %r", self.__state)
            raise MoeBotStateException()

    def pause(self) -> None:
        _log.debug("Attempting to pause mowing: %r", self.__state)
        if self.__state in ("MOWING", "FIXED_MOWING"):
            result = self.__device.set_value(115, "PauseWork")
            self.__parse_payload(result)
        else:
            _log.error("Unable to pause due to current state: %r", self.__state)
            raise MoeBotStateException()

    def cancel(self) -> None:
        _log.debug("Attempting to cancel mowing: %r", self.__state)
        if self.__state in ("PAUSED", "CHARGING_WITH_TASK_SUSPEND"):
            result = self.__device.set_value('115', "CancelWork")
            self.__parse_payload(result)

            # # When work is cancelled, the mower will send two reports; one to confirm the new state and one to
            # # report on the work completed.  Often only one comes through, so we need to query state to ensure
            # # we know it.
            # self.__query_state()
        else:
            _log.error("Unable to cancel due to current state: %r", self.__state)
            raise MoeBotStateException()

    def dock(self) -> None:
        _log.debug("Attempting to dock mower: %r", self.__state)
        if self.__state in ("STANDBY", "STANDBY"):
            result = self.__device.set_value('115', "StartReturnStation")
            self.__parse_payload(result)
        else:
            _log.error("Unable to dock due to current state: %r", self.__state)
            raise MoeBotStateException()

    def __repr__(self) -> str:
        return "[MoeBot - {id: %s, state: %s, battery: %s}]" % (self.id, self.__state, self.__battery)


class MoeBotStateException(Exception):
    pass


class MoeBotConnectionError(Exception):
    pass
