import unittest
import struct
import asyncio

from NavSpark_console.protocol import *


def conv(x):
    if len(x) == 8:
        return struct.unpack(">d", x)[0]

    return struct.unpack(">f", x)[0]


class TestNavSparkRawProtocol(unittest.IsolatedAsyncioTestCase):
    async def test_data_received(self):
        proto = NavSparkRawProtocol()
        proto.connection_made(None)

        # a whole packet arriving at once
        proto.data_received(
            b"\xA0\xA1\x00\x0A\xDC\x3D\x06\xED\x0B\x0C\xBC\x40\x03\xE8\x1A\x0D\x0A"
        )

        msg = await proto.message_queue.get()
        self.assertEqual(
            msg,
            MeasurementTimeInformation(
                iod=0x3D,
                receiver_wn=0x06ED,
                receiver_tow=0x0B0CBC40,
                measurement_period=0x03E8,
            ),
        )

        # a whole packet and a partial packet. The partial packet has a very small
        # change in one field.
        proto.data_received(
            b"\xA0\xA1\x00\x0A\xDC\x3D\x06\xED\x0B\x0C\xBC\x40\x03\xE8\x1A\x0D\x0A"
            b"\xA0\xA1\x00\x0A\xDC\x3E\x06\xED\x0B\x0C\xBC\x40"
        )

        msg = await proto.message_queue.get()
        self.assertEqual(
            msg,
            MeasurementTimeInformation(
                iod=0x3D,
                receiver_wn=0x06ED,
                receiver_tow=0x0B0CBC40,
                measurement_period=0x03E8,
            ),
        )

        # there shouldn't be anything in the queue
        with self.assertRaises(asyncio.QueueEmpty):
            proto.message_queue.get_nowait()

        # the rest of the partial packet
        proto.data_received(b"\x03\xE8\x19\x0D\x0A")

        msg = await proto.message_queue.get()
        self.assertEqual(
            msg,
            MeasurementTimeInformation(
                iod=0x3E,
                receiver_wn=0x06ED,
                receiver_tow=0x0B0CBC40,
                measurement_period=0x03E8,
            ),
        )


class TestMeasurementTimeInformation(unittest.TestCase):
    def test_unpack(self):
        msg = MeasurementTimeInformation.unpack(
            b"\xDC\x3D\x06\xED\x0B\x0C\xBC\x40\x03\xE8"
        )

        self.assertEqual(
            msg,
            MeasurementTimeInformation(
                iod=0x3D,
                receiver_wn=0x06ED,
                receiver_tow=0x0B0CBC40,
                measurement_period=0x03E8,
            ),
        )


class TestRawMeasurementsArray(unittest.TestCase):
    def test_unpack(self):
        msg = RawMeasurementsArray.unpack(
            b"\xDD\x3D\x0F\x02\x2B\x41\x74\x42\xDB\x76\x55\xFA\x29\xC0\xE2\xE4\x02\x21\x5A\x00\x00"
            b"\x44\x20\x80\x00\x07\x09\x29\x41\x77\x8C\xF0\xA9\xE7\x0C\x43\xC0\xF9\x72\x54\x2E\xEB"
            b"\x80\x00\x44\xE3\xA0\x00\x07\x0A\x28\x41\x75\xCA\x96\x91\xA9\xE9\x23\x41\x04\x7D\xB1"
            b"\xE9\xA9\x80\x00\xC5\x31\x20\x00\x07\x05\x2B\x41\x74\x9E\xBE\xEE\x17\x8C\x6A\x40\xD3"
            b"\x71\xD4\x80\xCF\x00\x00\xC3\xAE\x00\x00\x07\x1A\x2E\x41\x75\x02\x83\xE5\xEC\xD7\x65"
            b"\xC1\x04\x6D\x73\xBD\xE6\x20\x00\x45\x33\x30\x00\x07\x0C\x28\x41\x77\xC1\xE0\x1D\xA7"
            b"\x2E\xC1\x40\xFF\x79\x4C\xC9\x14\x80\x00\xC5\x0D\x80\x00\x07\x11\x28\x41\x77\xE7\xB0"
            b"\xE8\x15\x9A\xA8\x41\x0C\x87\x99\x0C\xFA\xA0\x00\xC5\x80\xD8\x00\x07\x0F\x27\x41\x77"
            b"\x93\x96\x77\x03\x2B\x0A\xC1\x06\xBF\x2C\x49\x05\x60\x00\x45\x4F\xB0\x00\x07\x04\x2C"
            b"\x41\x75\xBA\x4E\xB0\x68\x2B\x43\x40\xFB\x25\xC7\xA3\xB6\xC0\x00\xC4\xFE\x60\x00\x07"
            b"\x07\x26\x41\x78\x48\x7F\x72\xDF\xC5\x81\xC0\xD0\x89\xC8\xBF\x96\x00\x00\x43\xA7\x80"
            b"\x00\x07\x0D\x1D\x00\x00\x00\x00\x00\x00\x00\x00\x41\x05\xF9\xA2\xD6\x0D\x40\x00\xC5"
            b"\x66\x00\x00\x16\x08\x27\x41\x78\x6A\xD7\xA4\x71\x2A\x50\xC0\xEF\x02\x44\x2E\x09\x80"
            b"\x00\x44\xA2\x80\x00\x07\x19\x23\x41\x78\x7E\xE4\x8B\x0C\x9E\x26\x40\xE6\xAD\x04\x2B"
            b"\x85\x80\x00\xC4\x98\x20\x00\x07\x42\x1F\x41\x75\x27\xEA\xE2\x16\x7D\x10\x41\x06\xD6"
            b"\x0A\x57\x6B\x00\x00\xC5\x53\x10\x00\x07\x52\x1E\x00\x00\x00\x00\x00\x00\x00\x00\xC0"
            b"\xFE\x83\x49\x5D\xA7\x00\x00\x45\x16\xC0\x00\x06"
        )

        expected_data = [
            (
                0x02,
                0x2B,
                b"\x41\x74\x42\xDB\x76\x55\xFA\x29",
                b"\xC0\xE2\xE4\x02\x21\x5A\x00\x00",
                b"\x44\x20\x80\x00",
                0x07,
            ),
            (
                0x09,
                0x29,
                b"\x41\x77\x8C\xF0\xA9\xE7\x0C\x43",
                b"\xC0\xF9\x72\x54\x2E\xEB\x80\x00",
                b"\x44\xE3\xA0\x00",
                0x07,
            ),
            (
                0x0A,
                0x28,
                b"\x41\x75\xCA\x96\x91\xA9\xE9\x23",
                b"\x41\x04\x7D\xB1\xE9\xA9\x80\x00",
                b"\xC5\x31\x20\x00",
                0x07,
            ),
            (
                0x05,
                0x2B,
                b"\x41\x74\x9E\xBE\xEE\x17\x8C\x6A",
                b"\x40\xD3\x71\xD4\x80\xCF\x00\x00",
                b"\xC3\xAE\x00\x00",
                0x07,
            ),
            (
                0x1A,
                0x2E,
                b"\x41\x75\x02\x83\xE5\xEC\xD7\x65",
                b"\xC1\x04\x6D\x73\xBD\xE6\x20\x00",
                b"\x45\x33\x30\x00",
                0x07,
            ),
            (
                0x0C,
                0x28,
                b"\x41\x77\xC1\xE0\x1D\xA7\x2E\xC1",
                b"\x40\xFF\x79\x4C\xC9\x14\x80\x00",
                b"\xC5\x0D\x80\x00",
                0x07,
            ),
            (
                0x11,
                0x28,
                b"\x41\x77\xE7\xB0\xE8\x15\x9A\xA8",
                b"\x41\x0C\x87\x99\x0C\xFA\xA0\x00",
                b"\xC5\x80\xD8\x00",
                0x07,
            ),
            (
                0x0F,
                0x27,
                b"\x41\x77\x93\x96\x77\x03\x2B\x0A",
                b"\xC1\x06\xBF\x2C\x49\x05\x60\x00",
                b"\x45\x4F\xB0\x00",
                0x07,
            ),
            (
                0x04,
                0x2C,
                b"\x41\x75\xBA\x4E\xB0\x68\x2B\x43",
                b"\x40\xFB\x25\xC7\xA3\xB6\xC0\x00",
                b"\xC4\xFE\x60\x00",
                0x07,
            ),
            (
                0x07,
                0x26,
                b"\x41\x78\x48\x7F\x72\xDF\xC5\x81",
                b"\xC0\xD0\x89\xC8\xBF\x96\x00\x00",
                b"\x43\xA7\x80\x00",
                0x07,
            ),
            (
                0x0D,
                0x1D,
                b"\x00\x00\x00\x00\x00\x00\x00\x00",
                b"\x41\x05\xF9\xA2\xD6\x0D\x40\x00",
                b"\xC5\x66\x00\x00",
                0x16,
            ),
            (
                0x08,
                0x27,
                b"\x41\x78\x6A\xD7\xA4\x71\x2A\x50",
                b"\xC0\xEF\x02\x44\x2E\x09\x80\x00",
                b"\x44\xA2\x80\x00",
                0x07,
            ),
            (
                0x19,
                0x23,
                b"\x41\x78\x7E\xE4\x8B\x0C\x9E\x26",
                b"\x40\xE6\xAD\x04\x2B\x85\x80\x00",
                b"\xC4\x98\x20\x00",
                0x07,
            ),
            (
                0x42,
                0x1F,
                b"\x41\x75\x27\xEA\xE2\x16\x7D\x10",
                b"\x41\x06\xD6\x0A\x57\x6B\x00\x00",
                b"\xC5\x53\x10\x00",
                0x07,
            ),
            (
                0x52,
                0x1E,
                b"\x00\x00\x00\x00\x00\x00\x00\x00",
                b"\xC0\xFE\x83\x49\x5D\xA7\x00\x00",
                b"\x45\x16\xC0\x00",
                0x06,
            ),
        ]

        self.assertEqual(msg.iod, 0x3D)
        self.assertEqual(msg.array_count, 0xF)
        self.assertEqual(msg.array_count, len(msg.sub_messages))

        self.assertListEqual(
            msg.sub_messages,
            [
                RawMeasurement(
                    svid=data[0],
                    cn0=data[1],
                    pseudo_range=conv(data[2]),
                    accumulated_carrier_cycle=conv(data[3]),
                    doppler_frequency=conv(data[4]),
                    measurement_indicator=GPSRawMeasurementIndicator(data[5]),
                )
                for data in expected_data
            ],
        )


class TestSattelliteChannelStatuses(unittest.TestCase):
    def test_unpack(self):
        msg = SattelliteChannelStatuses.unpack(
            b"\xDE\x3D\x10\x00\x02\x07\x01\x2B\x00\x3E\x00\x10\x1F\x01\x09\x07\x01\x29\x00\x10\x00"
            b"\x72\x1F\x02\x0A\x07\x01\x28\x00\x22\x00\x27\x1F\x03\x05\x07\x00\x2B\x00\x38\x01\x38"
            b"\x1F\x04\x1A\x07\x00\x2E\x00\x2E\x00\xBA\x1F\x05\x0C\x07\x00\x28\x00\x0E\x00\xF8\x1F"
            b"\x06\x11\x07\x01\x28\x00\x0A\x00\x9A\x1F\x07\x0F\x07\x00\x27\x00\x0E\x00\xD1\x1F\x08"
            b"\x21\x07\x00\x29\x00\x42\x00\x2E\x1F\x09\x04\x07\x00\x2C\x00\x26\x00\x5B\x1F\x0C\x07"
            b"\x07\x00\x26\x00\x09\x00\x4D\x1F\x0D\x0D\x07\x00\x1D\x00\x06\x00\x24\x1F\x0E\x08\x07"
            b"\x00\x27\x00\x0A\x00\x6B\x1F\x0F\x19\x07\x00\x23\x00\x06\x01\x1B\x1F\x10\x42\x06\x05"
            b"\x1F\x00\x20\x00\x15\x1F\x11\x52\x07\x05\x1E\x00\x31\x01\x4E\x1F"
        )

        expected_data = [
            (0x00, 0x02, 0x07, 0x01, 0x2B, 0x003E, 0x0010, 0x1F),
            (0x01, 0x09, 0x07, 0x01, 0x29, 0x0010, 0x0072, 0x1F),
            (0x02, 0x0A, 0x07, 0x01, 0x28, 0x0022, 0x0027, 0x1F),
            (0x03, 0x05, 0x07, 0x00, 0x2B, 0x0038, 0x0138, 0x1F),
            (0x04, 0x1A, 0x07, 0x00, 0x2E, 0x002E, 0x00BA, 0x1F),
            (0x05, 0x0C, 0x07, 0x00, 0x28, 0x000E, 0x00F8, 0x1F),
            (0x06, 0x11, 0x07, 0x01, 0x28, 0x000A, 0x009A, 0x1F),
            (0x07, 0x0F, 0x07, 0x00, 0x27, 0x000E, 0x00D1, 0x1F),
            (0x08, 0x21, 0x07, 0x00, 0x29, 0x0042, 0x002E, 0x1F),
            (0x09, 0x04, 0x07, 0x00, 0x2C, 0x0026, 0x005B, 0x1F),
            (0x0C, 0x07, 0x07, 0x00, 0x26, 0x0009, 0x004D, 0x1F),
            (0x0D, 0x0D, 0x07, 0x00, 0x1D, 0x0006, 0x0024, 0x1F),
            (0x0E, 0x08, 0x07, 0x00, 0x27, 0x000A, 0x006B, 0x1F),
            (0x0F, 0x19, 0x07, 0x00, 0x23, 0x0006, 0x011B, 0x1F),
            (0x10, 0x42, 0x06, 0x05, 0x1F, 0x0020, 0x0015, 0x1F),
            (0x11, 0x52, 0x07, 0x05, 0x1E, 0x0031, 0x014E, 0x1F),
        ]

        self.assertEqual(msg.iod, 0x3D)
        self.assertEqual(msg.array_count, 0x10)
        self.assertEqual(msg.array_count, len(msg.sub_messages))

        self.assertListEqual(
            msg.sub_messages,
            [
                SattelliteChannelStatus(
                    channel_id=data[0],
                    svid=data[1],
                    sv_status_indicator=SattelliteStatusIndicator(data[2]),
                    ura_ft=data[3],
                    cn0=data[4],
                    elevation=data[5],
                    azimuth=data[6],
                    channel_status_indicator=SattelliteChannelStatusIndicator(data[7]),
                )
                for data in expected_data
            ],
        )


class TestReceiverNavigationStatus(unittest.TestCase):
    def test_unpack(self):
        # the example message from the reference doc has a typo in this message. The clock bias field
        # ends in 0x78 in the packed message but 0x68 in the message table. I just went with the 0x68
        # version
        msg = ReceiverNavigationStatus.unpack(
            b"\xDF\x92\x03\x06\xED\x41\x07\xDB\xE7\xFD\x76\x3B\x21\xC1\x46\xC6\x04\x2F\x62\xBF\xD8"
            b"\x41\x52\xF1\xB6\x4B\x17\xF7\xCC\x41\x44\x46\x79\xB8\x7A\xDB\x12\x3C\x8A\xAA\xD4\xBC"
            b"\x1A\x6E\xF0\xBB\xC5\x67\xD2\x41\x16\xAD\x5E\x6D\x3F\x7C\x78\x42\x8F\xD9\x1E\x40\x5D"
            b"\x7C\x6B\x40\x4B\x07\xFB\x3F\x7C\x51\xAD\x40\x40\xFB\xC2\x3F\xB1\x06\x30"
        )

        self.assertEqual(
            msg,
            ReceiverNavigationStatus(
                iod=0x92,
                navigation_state=NavigationState(0x03),
                week_number=0x06ED,
                time_of_week=conv(b"\x41\x07\xDB\xE7\xFD\x76\x3B\x21"),
                ecef_x=conv(b"\xC1\x46\xC6\x04\x2F\x62\xBF\xD8"),
                ecef_y=conv(b"\x41\x52\xF1\xB6\x4B\x17\xF7\xCC"),
                ecef_z=conv(b"\x41\x44\x46\x79\xB8\x7A\xDB\x12"),
                ecef_x_vel=conv(b"\x3C\x8A\xAA\xD4"),
                ecef_y_vel=conv(b"\xBC\x1A\x6E\xF0"),
                ecef_z_vel=conv(b"\xBB\xC5\x67\xD2"),
                clock_bias=conv(b"\x41\x16\xAD\x5E\x6D\x3F\x7C\x78"),
                clock_drift=conv(b"\x42\x8F\xD9\x1E"),
                gdop=conv(b"\x40\x5D\x7C\x6B"),
                pdop=conv(b"\x40\x4B\x07\xFB"),
                hdop=conv(b"\x3F\x7C\x51\xAD"),
                vdop=conv(b"\x40\x40\xFB\xC2"),
                tdop=conv(b"\x3F\xB1\x06\x30"),
            ),
        )


class TestGPSSubframe(unittest.TestCase):
    def test_unpack(self):
        msg = GPSSubframe.unpack(
            b"\xE0\x02\x05\x8B\x0B\xB4\x3F\x22\xB5\x4F\x31\xCF\x4E\xFD\x81\xFD\x4D\x00\xA1\x0C"
            b"\x98\x79\xE7\x09\x08\xD5\xC5\xF8\xED\x03\xEB\xFF\xF4"
        )

        self.assertEqual(
            msg,
            GPSSubframe(
                svid=0x02,
                sfid=0x05,
                words=(
                    b"\x8B\x0B\xB4\x3F\x22\xB5\x4F\x31\xCF\x4E\xFD\x81\xFD\x4D\x00\xA1\x0C"
                    b"\x98\x79\xE7\x09\x08\xD5\xC5\xF8\xED\x03\xEB\xFF\xF4"
                ),
            ),
        )


class TestGLONASSString(unittest.TestCase):
    def test_unpack(self):
        msg = GLONASSString.unpack(b"\xE1\x52\x0E\xB4\x05\xA9\xC3\x94\x17\x50\x04\x82")

        self.assertEqual(
            msg,
            GLONASSString(
                svid=0x52,
                string_number=0x0E,
                words=b"\xB4\x05\xA9\xC3\x94\x17\x50\x04\x82",
            ),
        )


class TestBeidou2D1Subframe(unittest.TestCase):
    def test_unpack(self):
        msg = Beidou2D1Subframe.unpack(
            b"\xE2\xCF\x01\xE2\x40\x47\x37\x58\x00\x0D\xA0\xE1\x00\xAC\x03\x87\x8E\x31\x5B\x53"
            b"\xB4\x12\xB2\xC0\x02\x5B\x04\x60\x07\xAB\x81"
        )

        self.assertEqual(
            msg,
            Beidou2D1Subframe(
                svid=0xCF,
                sfid=0x01,
                words=(
                    b"\xE2\x40\x47\x37\x58\x00\x0D\xA0\xE1\x00\xAC\x03\x87\x8E\x31\x5B\x53"
                    b"\xB4\x12\xB2\xC0\x02\x5B\x04\x60\x07\xAB\x81"
                ),
            ),
        )


class TestBeidou2D2Subframe(unittest.TestCase):
    def test_unpack(self):
        msg = Beidou2D2Subframe.unpack(
            b"\xE3\xCB\x01\xE2\x40\x47\x37\x95\xA5\x14\xC8\xCA\xEA\xCF\xA5\x00\x15\x55\x55\x55"
            b"\x55\x55\x55\x55\x55\x55\x55\x55\x55\x55\x55"
        )

        self.assertEqual(
            msg,
            Beidou2D2Subframe(
                svid=0xCB,
                sfid=0x01,
                words=(
                    b"\xE2\x40\x47\x37\x95\xA5\x14\xC8\xCA\xEA\xCF\xA5\x00\x15\x55\x55\x55"
                    b"\x55\x55\x55\x55\x55\x55\x55\x55\x55\x55\x55"
                ),
            ),
        )


class TestExtendedRawMeasurement(unittest.TestCase):
    def test_unpack(self):
        msg = ExtendedRawMeasurements.unpack(
            b"\xE5\x01\x0D\x07\x7C\x06\xAC\x40\x80\x03\xE8\x00\x00\x11\x00\x0D\xE0\x32\x41\xB3"
            b"\x33\x99\x89\x62\xC9\xBA\x41\xB3\x7F\x98\xFD\xAD\xE0\x00\x45\x79\x40\x00\x00\x00"
            b"\x00\x40\x07\x00\x00\x00\x02\xE0\x31\x41\xB3\x22\x3E\xED\xEA\xFB\xD6\x41\xB3\xB3"
            b"\xB8\x3A\xEB\xA0\x00\x44\xF1\x40\x00\x00\x00\x00\x40\x07\x00\x00\x00\x06\xE0\x30"
            b"\x41\xB3\x31\xEE\x4F\x2D\x2C\xD9\x41\xB3\xE3\x77\x47\x15\x20\x00\xC3\x39\x00\x00"
            b"\x00\x00\x00\x40\x07\x00\x00\x00\x04\xE0\x33\x41\xB3\x21\xA6\x72\x9C\x9E\x8D\x41"
            b"\xB3\x97\x3F\x77\x2B\x60\x00\x45\x2E\xF0\x00\x00\x00\x00\x40\x07\x00\x00\x00\x05"
            b"\xE0\x31\x41\xB3\x24\x52\x84\x6C\x89\x0E\x41\xB3\xC4\xEF\x07\xA8\xE0\x00\x44\x7C"
            b"\xC0\x00\x00\x00\x00\x40\x07\x00\x00\x00\x0C\xE0\x29\x41\xB3\x55\xD6\xAE\x07\x64"
            b"\xC5\x41\xB3\xF5\x9A\xF1\xB5\xE0\x00\xC4\x7C\x00\x00\x00\x00\x00\xC0\x07\x00\x00"
            b"\x00\x14\xE0\x29\x41\xB3\x53\x25\x16\x98\x94\x03\x41\xB3\x99\xD7\x19\x9B\x60\x00"
            b"\x45\x40\x60\x00\x00\x00\x00\x80\x07\x00\x00\x00\x13\xE0\x2C\x41\xB3\x48\x02\x4B"
            b"\x63\xBF\xD0\x41\xB4\x15\x80\x1A\xC7\x60\x00\xC5\x16\xD0\x00\x00\x00\x00\x40\x07"
            b"\x00\x00\x04\xC1\xE0\x30\x41\xB4\x3D\x68\x15\x86\x5B\x87\x41\xB3\xD2\x37\xDB\x1A"
            b"\x20\x00\x44\x3D\x00\x00\x00\x00\x00\x40\x07\x00\x00\x01\x80\xC0\x2D\x41\xB4\x26"
            b"\x6A\x74\xEB\xC0\x97\x41\xB3\xCC\x0C\x45\x53\xA0\x00\x44\x71\x00\x00\x00\x00\x00"
            b"\x40\x07\x00\x00\x01\x81\xC0\x2B\x41\xB4\x19\xE0\xD3\xAB\x6B\xBA\x41\xB3\xCC\xAC"
            b"\xC2\xC4\x20\x00\x44\x6F\xC0\x00\x00\x00\x00\x40\x07\x00\x00\x02\x06\xE3\x31\x41"
            b"\xB3\x15\x16\x02\x23\x16\x1C\x41\xB4\x0A\x57\x97\x61\x20\x00\x44\xBA\xA0\x00\x00"
            b"\x00\x00\x40\x07\x00\x00\x02\x05\xE8\x2D\x41\xB3\x21\xD8\x78\x41\x5F\x35\x41\xB4"
            b"\x5E\x18\x7C\x73\xA0\x00\xC4\xE3\x00\x00\x00\x00\x00\x40\x07\x00\x00\x02\x14\xE9"
            b"\x2D\x41\xB3\x0B\x52\x79\xC4\x94\x08\x41\xB4\x0F\xE8\x10\xA1\x60\x00\x44\x9E\x40"
            b"\x00\x00\x00\x00\x40\x07\x00\x00\x02\x13\xEA\x2C\x41\xB3\x30\x72\x52\x8C\x68\x0F"
            b"\x41\xB4\x68\x6E\x04\xCF\xE0\x00\xC5\x0F\x90\x00\x00\x00\x00\x40\x07\x00\x00\x02"
            b"\x15\xEB\x2F\x41\xB3\x2A\x46\xFD\x31\x68\x39\x41\xB3\xD0\x8E\xE5\x12\xE0\x00\x45"
            b"\x8D\xA8\x00\x00\x00\x00\x40\x07\x00\x00\x02\x07\xEC\x2C\x41\xB3\x45\xAB\x04\x39"
            b"\x61\xD6\x41\xB3\xE5\x52\x58\x10\x20\x00\x45\x72\xB0\x00\x00\x00\x00\x80\x07\x00"
            b"\x00"
        )

        expected_data = [
            (
                0,
                0,
                0xD,
                0,
                0xE,
                0x32,
                b"\x41\xB3\x33\x99\x89\x62\xC9\xBA",
                b"\x41\xB3\x7F\x98\xFD\xAD\xE0\x00",
                b"\x45\x79\x40\x00",
                0,
                0,
                0,
                0x4007,
                b"\x00\x00",
            ),
            (
                0,
                0,
                0x2,
                0,
                0xE,
                0x31,
                b"\x41\xB3\x22\x3E\xED\xEA\xFB\xD6",
                b"\x41\xB3\xB3\xB8\x3A\xEB\xA0\x00",
                b"\x44\xF1\x40\x00",
                0,
                0,
                0,
                0x4007,
                b"\x00\x00",
            ),
            (
                0,
                0,
                0x6,
                0,
                0xE,
                0x30,
                b"\x41\xB3\x31\xEE\x4F\x2D\x2C\xD9",
                b"\x41\xB3\xE3\x77\x47\x15\x20\x00",
                b"\xC3\x39\x00\x00",
                0,
                0,
                0,
                0x4007,
                b"\x00\x00",
            ),
            (
                0,
                0,
                0x4,
                0,
                0xE,
                0x33,
                b"\x41\xB3\x21\xA6\x72\x9C\x9E\x8D",
                b"\x41\xB3\x97\x3F\x77\x2B\x60\x00",
                b"\x45\x2E\xF0\x00",
                0,
                0,
                0,
                0x4007,
                b"\x00\x00",
            ),
            (
                0,
                0,
                0x5,
                0,
                0xE,
                0x31,
                b"\x41\xB3\x24\x52\x84\x6C\x89\x0E",
                b"\x41\xB3\xC4\xEF\x07\xA8\xE0\x00",
                b"\x44\x7C\xC0\x00",
                0,
                0,
                0,
                0x4007,
                b"\x00\x00",
            ),
            (
                0,
                0,
                0x0C,
                0,
                0xE,
                0x29,
                b"\x41\xB3\x55\xD6\xAE\x07\x64\xC5",
                b"\x41\xB3\xF5\x9A\xF1\xB5\xE0\x00",
                b"\xC4\x7C\x00\x00",
                0,
                0,
                0,
                0xC007,
                b"\x00\x00",
            ),
            (
                0,
                0,
                0x14,
                0,
                0xE,
                0x29,
                b"\x41\xB3\x53\x25\x16\x98\x94\x03",
                b"\x41\xB3\x99\xD7\x19\x9B\x60\x00",
                b"\x45\x40\x60\x00",
                0,
                0,
                0,
                0x8007,
                b"\x00\x00",
            ),
            (
                0,
                0,
                0x13,
                0,
                0xE,
                0x2C,
                b"\x41\xB3\x48\x02\x4B\x63\xBF\xD0",
                b"\x41\xB4\x15\x80\x1A\xC7\x60\x00",
                b"\xC5\x16\xD0\x00",
                0,
                0,
                0,
                0x4007,
                b"\x00\x00",
            ),
            (
                0x4,
                0,
                0xC1,
                0,
                0xE,
                0x30,
                b"\x41\xB4\x3D\x68\x15\x86\x5B\x87",
                b"\x41\xB3\xD2\x37\xDB\x1A\x20\x00",
                b"\x44\x3D\x00\x00",
                0,
                0,
                0,
                0x4007,
                b"\x00\x00",
            ),
            (
                0x1,
                0,
                0x80,
                0,
                0xC,
                0x2D,
                b"\x41\xB4\x26\x6A\x74\xEB\xC0\x97",
                b"\x41\xB3\xCC\x0C\x45\x53\xA0\x00",
                b"\x44\x71\x00\x00",
                0,
                0,
                0,
                0x4007,
                b"\x00\x00",
            ),
            (
                0x1,
                0,
                0x81,
                0,
                0xC,
                0x2B,
                b"\x41\xB4\x19\xE0\xD3\xAB\x6B\xBA",
                b"\x41\xB3\xCC\xAC\xC2\xC4\x20\x00",
                b"\x44\x6F\xC0\x00",
                0,
                0,
                0,
                0x4007,
                b"\x00\x00",
            ),
            (
                0x2,
                0,
                0x6,
                0x3,
                0xE,
                0x31,
                b"\x41\xB3\x15\x16\x02\x23\x16\x1C",
                b"\x41\xB4\x0A\x57\x97\x61\x20\x00",
                b"\x44\xBA\xA0\x00",
                0,
                0,
                0,
                0x4007,
                b"\x00\x00",
            ),
            (
                0x2,
                0,
                0x5,
                0x8,
                0xE,
                0x2D,
                b"\x41\xB3\x21\xD8\x78\x41\x5F\x35",
                b"\x41\xB4\x5E\x18\x7C\x73\xA0\x00",
                b"\xC4\xE3\x00\x00",
                0,
                0,
                0,
                0x4007,
                b"\x00\x00",
            ),
            (
                0x2,
                0,
                0x14,
                0x9,
                0xE,
                0x2D,
                b"\x41\xB3\x0B\x52\x79\xC4\x94\x08",
                b"\x41\xB4\x0F\xE8\x10\xA1\x60\x00",
                b"\x44\x9E\x40\x00",
                0,
                0,
                0,
                0x4007,
                b"\x00\x00",
            ),
            (
                0x2,
                0,
                0x13,
                0xA,
                0xE,
                0x2C,
                b"\x41\xB3\x30\x72\x52\x8C\x68\x0F",
                b"\x41\xB4\x68\x6E\x04\xCF\xE0\x00",
                b"\xC5\x0F\x90\x00",
                0,
                0,
                0,
                0x4007,
                b"\x00\x00",
            ),
            (
                0x2,
                0,
                0x15,
                0xB,
                0xE,
                0x2F,
                b"\x41\xB3\x2A\x46\xFD\x31\x68\x39",
                b"\x41\xB3\xD0\x8E\xE5\x12\xE0\x00",
                b"\x45\x8D\xA8\x00",
                0,
                0,
                0,
                0x4007,
                b"\x00\x00",
            ),
            (
                0x2,
                0,
                0x7,
                0xC,
                0xE,
                0x2C,
                b"\x41\xB3\x45\xAB\x04\x39\x61\xD6",
                b"\x41\xB3\xE5\x52\x58\x10\x20\x00",
                b"\x45\x72\xB0\x00",
                0,
                0,
                0,
                0x8007,
                b"\x00\x00",
            ),
        ]

        self.assertEqual(msg.iod, 0x0D)
        self.assertEqual(msg.version, 0x01)
        self.assertEqual(msg.receiver_wn, 0x077C)
        self.assertEqual(msg.tow, 0x06AC4080)
        self.assertEqual(msg.measurement_period, 0x03E8)
        self.assertEqual(msg.measurement_indicator, 0x00)
        self.assertEqual(msg.reserved, b"\x00")

        self.assertEqual(msg.array_count, 0x11)
        self.assertEqual(msg.array_count, len(msg.sub_messages))

        self.assertListEqual(
            msg.sub_messages,
            [
                ExtendedRawMeasurement(
                    gnss_type=GNSSType(data[0]),
                    signal_type=data[1],
                    svid=data[2],
                    frequency_id=data[4],
                    lock_time_indicator=data[3],
                    cn0=data[5],
                    pseudorange=conv(data[6]),
                    accumulated_carrier_cycle=conv(data[7]),
                    doppler_frequency=conv(data[8]),
                    pseudorange_standard_dev=data[9],
                    accumulated_carrier_cycle_standard_dev=data[10],
                    doppler_freq_standard_dev=data[11],
                    channel_indicator=ExtendedRawChannelIndicator(data[12]),
                    reserved=data[13],
                )
                for data in expected_data
            ],
        )
