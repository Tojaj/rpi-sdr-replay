#!/usr/bin/env python3

import sys
import time
import glob
import dbus
import signal
import os.path
import subprocess
import collections

import bluedot


SAMPLING = 250000  # Hz
FREQUENCY = 433050000  # Hz
FN_SUFFIX = "rec"
FN_PATTERN = f"%y%m%d-%H%M%S.{FN_SUFFIX}"


class ReplayerException(Exception):
    """Exception raised by Replayer class that handles radio capturing and transmission."""
    pass


class Replayer(object):
    """Replayer class handles radio capturing and transmission (replay)."""

    def __init__(self, directory, rx_freq=FREQUENCY, tx_freq=FREQUENCY) -> None:
        self.directory = directory
        self.rx_freq = rx_freq
        self.tx_freq = tx_freq

        self._recording_in_progress = None
        self._transmission_in_progress = None

    def get_available_recordings(self) -> list:
        """Returns sorted list of available recordings, the newest recording is the first."""
        pattern = os.path.join(self.directory, f"*{FN_SUFFIX}")
        return sorted(glob.glob(pattern), reverse=True)

    def start_recording(self) -> str:
        """Start recording and return a filename."""

        if self._recording_in_progress is not None:
            raise ReplayerException("One recording is already in progress!")

        filename = time.strftime(FN_PATTERN)

        command = [
            "/usr/bin/rtl_sdr",
            "-s",
            f"{SAMPLING}",
            "-f",
            f"{self.rx_freq}",
            filename
        ]

        # TODO: In future use shlex.join (Added in Python 3.8)
        print(f"Starting: {' '.join(command)}")

        self._recording_in_progress = subprocess.Popen(command)

        return filename

    def stop_recording(self) -> bool:
        """Stop the ongoing recording.

        :returns: True if recording command return code was success, False otherwise."""

        if self._recording_in_progress is None:
            raise ReplayerException("No recording in progress!")

        self._recording_in_progress.terminate()
        self._recording_in_progress.wait()
        print(f"Recording return code: {self._recording_in_progress.returncode}")
        self._recording_in_progress = None

        if self._recording_in_progress.returncode != 0:
            return False

        return True

    def start_replay(self, filename) -> None:
        """Start radio replay of the recording specified by the filename"""

        if self._transmission_in_progress is not None:
            raise ReplayerException("One transmission is already in progress!")

        command = [
            "sudo",
            "/usr/bin/sendiq",
            "-s",
            f"{SAMPLING}",
            "-f",
            f"{self.tx_freq}",
            "-t",
            "u8",
            "-i",
            filename
        ]

        # TODO: In future use shlex.join (Added in Python 3.8)
        print(f"Starting: {' '.join(command)}")

        self._transmission_in_progress = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def stop_replay(self) -> bool:
        """Stop ongoing replay

        :returns: True if replay command return code was success, False otherwise."""

        if self._transmission_in_progress is None:
            raise ReplayerException("No transmission in progress!")

        self._transmission_in_progress.terminate()
        return self.wait_replay()

    def wait_replay(self, timeout=None) -> bool:
        """Wait until the ongoing replay is over

        If the process does not terminate after "timeout" seconds, raise
        a TimeoutExpired exception. It is safe to catch this exception and
        retry the wait.

        :returns: True if replay command return code was success, False otherwise."""

        if self._transmission_in_progress is None:
            raise ReplayerException("No transmission in progress!")

        self._transmission_in_progress.wait(timeout)
        print(f"Replay return code: {self._transmission_in_progress.returncode}")
        self._transmission_in_progress = None

        if self._transmission_in_progress.returncode != 0:
            return False

        return True


Recording = collections.namedtuple("Recording", ["filename", "color"])


class ReplayerBluetoothUI(object):
    """Class that handles the Bluetooth UI via the Blue Dot android app."""

    # States
    _STATE_INIT = 0
    _STATE_LIST = 1
    _STATE_LIST_LAST = 2
    _STATE_REC = 3
    _STATE_REPLAY = 4
    _STATE_SHUTDOWN = 5

    def __init__(self, replayer, bd, pairing=False) -> None:
        self.replayer = replayer
        self.bd = bd
        self.pairing = pairing

        self._state = self._STATE_INIT
        self._recordings = []  # List of Recording named tuples [(filename, color), ..]
        self._rec_pointer = 0

    def _update_recordings(self) -> None:
        """Update internal list of available recordings.
        It also generates an appropriate "greenish" color for each record."""

        recs = self.replayer.get_available_recordings()
        num = len(recs)
        if num == 0:
            self._recordings = []
            return

        # Calculate colors
        colors = [(0, 225, 0)]  # First (latest) is always "Green"

        first = (0, 100, 0)     # Other colors starts at "DarkGreen
        last = (232, 255, 232)  # Last color

        step = (
            (last[0] - first[0]) / num,
            (last[1] - first[1]) / num,
            (last[2] - first[2]) / num,
        )

        for i in range(num):
            # Calculate a delta
            delta = tuple(int(i * item) for item in step)
            # Calculate the final color (first + delta)
            color = tuple(map(sum, zip(first, delta)))
            colors.append(color)

        # Merge recordings and colors (note we calculated +1 color, but it doesn't matter)
        self._recordings = [Recording(*recording) for recording in zip(recs, colors)]

    def _shutdown(self) -> bool:
        """Shut down the system via D-Bus and login1.

        :returns: False if system cannot be turned off this way, True otherwise"""

        sys_bus = dbus.SystemBus()
        ck_srv = sys_bus.get_object('org.freedesktop.login1', '/org/freedesktop/login1')
        ck_iface = dbus.Interface(ck_srv, 'org.freedesktop.login1.Manager')
        can = ck_iface.get_dbus_method("CanPowerOff")()
        if not can:
            print("You cannot shutdown this system! (Update polkit policy to allow you org.freedesktop.login1.power-off)")
            return False
        print("Power off")
        ck_iface.get_dbus_method("PowerOff")(False)
        return True

    def _pressed(self, pos) -> None:
        """Method that handles a "blue" button press"""

        if self._state == self._STATE_INIT:
            if pos.middle:
                self._state = self._STATE_REC
                self.bd.color = bluedot.COLORS["red"]
                fn = self.replayer.start_recording()
                print(f"Started recording '{fn}' ...")
            elif pos.bottom:
                self._state = self._STATE_SHUTDOWN
                self.bd.color = bluedot.COLORS["black"]
                print("Do you really want to shut down?")
            elif pos.left:
                if len(self._recordings) > 0:
                    self._state = self._STATE_LIST
                    self._rec_pointer = 0
                    self.bd.color = self._recordings[self._rec_pointer].color
                    print(f"Current recording: '{self._recordings[self._rec_pointer].filename}'")

        elif self._state == self._STATE_REC:
            # Regardless the position, stop the recording on press
            self.bd.visible = False
            self.replayer.stop_recording()
            print("Stopped the recording")
            self._update_recordings()
            assert len(self._recordings) > 0  # Should be always true now when we recorded one!
            self._state = self._STATE_LIST
            self._rec_pointer = 0
            self.bd.color = self._recordings[self._rec_pointer].color
            self.bd.visible = True

        elif self._state == self._STATE_LIST:
            if pos.middle:
                self.bd.visible = False
                assert self._rec_pointer < len(self._recordings)  # Should be always true!
                print(f"Replaying '{self._recordings[self._rec_pointer].filename}'..")
                self.replayer.start_replay(self._recordings[self._rec_pointer].filename)
                self.replayer.wait_replay()
                self.bd.visible = True
                # Stay on the state and the rec pointer
            elif pos.left:
                if len(self._recordings) > (self._rec_pointer + 1):
                    self._rec_pointer += 1
                    self.bd.color = self._recordings[self._rec_pointer].color
                    print(f"Current recording: '{self._recordings[self._rec_pointer].filename}'")
                else:
                    self._state = self._STATE_LIST_LAST
                    self.bd.color = bluedot.COLORS["white"]
                    self.bd.border = True
                    print("No more records! Go back!")
            elif pos.right:
                if self._rec_pointer == 0:
                    self._state = self._STATE_INIT
                    self.bd.color = bluedot.COLORS["blue"]
                    print("Press the middle to start recording!")
                else:
                    self._rec_pointer -= 1
                    self.bd.color = self._recordings[self._rec_pointer].color
                    print(f"Current recording: '{self._recordings[self._rec_pointer].filename}'")

        elif self._state == self._STATE_LIST_LAST:
            if pos.right:
                self.bd.border = False
                self._state = self._STATE_LIST
                self.bd.color = self._recordings[self._rec_pointer].color
                print(f"Current recording: '{self._recordings[self._rec_pointer].filename}'")

        elif self._state == self._STATE_SHUTDOWN:
            if pos.middle:
                print("Shutting down...")
                self._shutdown()
                sys.exit(0)
            else:
                # TODO: Return to previous state
                self._state = self._STATE_INIT
                self.bd.color = bluedot.COLORS["blue"]
                self._rec_pointer = 0

    def run(self) -> None:
        """This method starts the bluetooth UI"""

        self._update_recordings()

        self.bd.when_released = self._pressed

        if self.pairing:
            print("Pairing..")
            self.bd.allow_pairing()
            print("Pairing over")

        signal.pause()
