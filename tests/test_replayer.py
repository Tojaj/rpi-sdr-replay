import sys
import mock
import shutil
import os.path
import tempfile
import unittest

from bluedot import MockBlueDot

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import rpi_sdr_replay


class TestReplayer(unittest.TestCase):

    def setUp(self) -> None:
        self.tempdir = tempfile.mkdtemp(prefix="sdr-replay-")

    def tearDown(self) -> None:
        shutil.rmtree(self.tempdir)

    def test_get_available_recordings(self) -> None:

        replayer = rpi_sdr_replay.Replayer(self.tempdir)

        # Empty dir
        recs = replayer.get_available_recordings()
        self.assertEqual(recs, [])

        # One file
        _, fn1 = tempfile.mkstemp(prefix="1-", suffix=rpi_sdr_replay.FN_SUFFIX, dir=self.tempdir)
        recs = replayer.get_available_recordings()
        self.assertEqual(recs, [fn1])

        # Two files (To make sure they are returned in sorted order)
        _, fn2 = tempfile.mkstemp(prefix="2-", suffix=rpi_sdr_replay.FN_SUFFIX, dir=self.tempdir)
        recs = replayer.get_available_recordings()
        self.assertEqual(recs, [fn2, fn1])


class TestReplayerBluetoothUI(unittest.TestCase):

    def setUp(self) -> None:
        self.tempdir = tempfile.mkdtemp(prefix="sdr-replay-")

    def tearDown(self) -> None:
        shutil.rmtree(self.tempdir)

    def test_update_recordings(self) -> None:
        bd_mock = MockBlueDot()
        replayer_mock = mock.Mock()

        ui = rpi_sdr_replay.ReplayerBluetoothUI(replayer_mock, bd_mock)

        replayer_mock.get_available_recordings.return_value = []
        ui._update_recordings()
        replayer_mock.get_available_recordings.assert_called()
        self.assertEqual(len(ui._recordings), 0)

        replayer_mock.get_available_recordings.return_value = ["/01-a", "/02-b", "/03-c"]
        ui._update_recordings()
        replayer_mock.get_available_recordings.assert_called()
        self.assertEqual(len(ui._recordings), 3)
        self.assertEqual(ui._recordings[0], ("/01-a", (0, 225, 0)))
        self.assertEqual(ui._recordings[1], ("/02-b", (0, 100, 0)))


if __name__ == '__main__':
    unittest.main()
