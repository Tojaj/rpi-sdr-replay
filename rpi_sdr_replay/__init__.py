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
FN_SUFFIX = ".rec"
FN_PATTERN = f"%y%m%d-%H%M%S.{FN_SUFFIX}"


class Replayer(object):

    def __init__(self, directory, rx_freq=FREQUENCY, tx_freq=FREQUENCY):
        self.directory = directory
        self.rx_freq = rx_freq
        self.tx_freq = tx_freq

        self._recording_in_progress = False
        self._transmission_in_progress = False

    def get_available_recordings(self):
        """Returns sorted list of available recordings, the newest recording is the first."""
        pattern = os.path.join(self.directory, f"*{FN_SUFFIX}")
        return sorted(glob.glob(pattern), reverse=True)

    def start_recording(self) -> str:
        """Start recording and return a filename."""
        if self._recording_in_progress is not None:
            return False  # Exception here

        filename = time.strftime(FN_PATTERN)

        command = [
            "/usr/bin/rtl_sdr",
            "-s",
            f"{SAMPLING}",
            "-f",
            f"{self.rx_freq}",
            filename
        ]

        self._recording_in_progress = subprocess.Popen(command)

        return filename

    def stop_recording(self):
        """Stop the ongoing recording."""
        if self._recording_in_progress is None:
            return False  # Exception here

        self._recording_in_progress.terminate()
        self._recording_in_progress.wait()
        # TODO: Check for errors
        self._recording_in_progress = None

    def start_replay(self, filename):
        if self._transmission_in_progress is not None:
            return False  # Exception here

        command = [
            "sudo",  # TODO: Get rid of sudo here
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

        self._transmission_in_progress = subprocess.Popen(command)

    def stop_replay(self):
        if self._transmission_in_progress is not None:
            return False  # Exception here

        self._transmission_in_progress.terminate()
        self._transmission_in_progress.wait()
        # TODO: Check for errors
        self._transmission_in_progress = None

    def wait_replay(self):
        if self._transmission_in_progress is not None:
            return False  # Exception here

        self._transmission_in_progress.wait()
        self._transmission_in_progress = None


Recording = collections.namedtuple("Recording", ["filename", "color"])


class ReplayerBluetoothUI(object):

    _STATE_INIT = 0
    _STATE_LIST = 1
    _STATE_LIST_LAST = 2
    _STATE_REC = 3
    _STATE_REPLAY = 4
    _STATE_SHUTDOWN = 5

    def __init__(self, replayer, bd, pairing=False):
        self.replayer = replayer
        self.bd = bd
        self.pairing = pairing

        self._state = self._STATE_INIT
        self._recordings = []  # List of Recording named tuples [(filename, color), ..]
        self._rec_pointer = 0

    def _update_recordings(self) -> None:
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
        sys_bus = dbus.SystemBus()
        ck_srv = sys_bus.get_object('org.freedesktop.login1', '/org/freedesktop/login1')
        ck_iface = dbus.Interface(ck_srv, 'org.freedesktop.login1.Manager')
        can = ck_iface.get_dbus_method("CanPowerOff")()
        if not can:
            print("You cannot shutdown this system! (Update polkit policy to allow you org.freedesktop.login1.power-off)")
            return False
        print("Power off")
        ck_iface.get_dbus_method("PowerOff")(False)

    def pressed(self, pos) -> None:

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
        self._update_recordings()

        self.bd.when_released = self.pressed

        if self.pairing:
            print("Pairing..")
            self.bd.allow_pairing()
            print("Pairing over")

        signal.pause()
