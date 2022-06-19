import unittest
import struct
import asyncio

import attrs

from NavSpark_console.protocol import *


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


class MessageTestCase(unittest.TestCase):
    @staticmethod
    def convert(array_types, *args, **kwargs):
        assert not (args and kwargs)

        def c(t, d):
            if t == "i":
                return d
            elif t == "f" and len(d) == 4:
                return struct.unpack(">f", d)[0]
            elif t == "d" and len(d) == 8:
                return struct.unpack(">d", d)[0]
            elif t == "b":
                return d
            else:
                return t(d)

        if args:
            return tuple(c(t, d) for t, d in zip(array_types, args))

        if kwargs:
            return {k: c(t, d) for t, (k, d) in zip(array_types, kwargs.items())}

    def assertPacked(self, message_kls, packed_bytes, kw_types=None, **kwargs):
        expected = kwargs
        if kw_types:
            expected = MessageTestCase.convert(kw_types, **kwargs)

        self.assertEqual(packed_bytes, bytes(message_kls(**expected)))

    def assertUnpacked(self, message_kls, packed_bytes, kw_types=None, **kwargs):
        msg = message_kls.unpack(packed_bytes)
        expected = kwargs
        if kw_types:
            expected = MessageTestCase.convert(kw_types, **kwargs)

        self.assertEqual(msg, message_kls(**expected))

    def assertArrUnpacked(
        self,
        message_kls,
        sub_message_kls,
        packed_bytes,
        sub_array,
        array_types,
        **kwargs,
    ):

        msg = message_kls.unpack(packed_bytes)
        actual_dict = attr.asdict(msg)
        actual_dict.pop("sub_messages")
        actual_dict.pop("output_id")

        expected_dict = dict(kwargs)
        expected_dict["array_count"] = len(sub_array)

        self.assertDictEqual(actual_dict, expected_dict)

        for i, (actual, expected) in enumerate(zip(msg.sub_messages, sub_array)):
            expected_conv = MessageTestCase.convert(array_types, *expected)
            self.assertEqual(
                actual, sub_message_kls(*expected_conv), msg=f"Array item {i} differs"
            )


class TestConfigureMessageType(MessageTestCase):
    def test_pack(self):
        self.assertPacked(
            ConfigureMessageType, b"\x09\x00\x00", msg_type=MessageType(0), persist=0
        )


class TestConfigurePositionUpdateRate(MessageTestCase):
    def test_pack(self):
        self.assertPacked(
            ConfigurePositionUpdateRate,
            b"\x0E\x01\x00",
            update_rate=UpdateRate.r1Hz,
            persist=0,
        )

    def test_unpack(self):
        self.assertUnpacked(
            ConfigurePositionUpdateRate,
            b"\x86\x01",
            update_rate=UpdateRate.r1Hz,
        )


class TestConfigureBinaryMeasurmentDataOutput(MessageTestCase):
    def test_pack(self):
        self.assertPacked(
            ConfigureBinaryMeasurmentDataOutput,
            b"\x1E\x00\x00\x00\x00\x01\x03\x01\x01",
            output_rate=BinaryUpdateRate.r1Hz,
            measure_time=False,
            raw_measurement=False,
            save_channel_status=False,
            receive_state_enabled=True,
            subframe_enabled=SubframeEnabledFlag(0x3),
            extended_raw_measurement_enabled=True,
            persist=True,
        )

    def test_unpack(self):
        self.assertUnpacked(
            ConfigureBinaryMeasurmentDataOutput,
            b"\x89\x00\x00\x00\x01\x01\x03\x01",
            output_rate=BinaryUpdateRate.r1Hz,
            measure_time=False,
            raw_measurement=False,
            save_channel_status=True,
            receive_state_enabled=True,
            subframe_enabled=SubframeEnabledFlag(0x3),
            extended_raw_measurement_enabled=True,
        )


class TestBinaryRTCMDataOutput(MessageTestCase):
    def test_unpack(self):
        self.assertUnpacked(
            BinaryRTCMDataOutput,
            b"\x8A\x01\x00\x01\x01\x01\x00\x01\x01\x00\x00\x00\x00\x00\x01\x02",
            rtcm_output=True,
            output_rate=BinaryUpdateRate.r1Hz,
            stationary_rtk=True,
            gps_msm7=True,
            glonass_msm7=True,
            galileo_msm7=False,
            sbas_msm7=True,
            qzss_msm7=True,
            bds_msm7=False,
            gps_ephemeris_interval=0,
            glonass_ephemeris_interval=0,
            beidou_ephemeris_interval=0,
            galileo_ephemeris_interval=0,
            rtcm_type=RTCMType.MSM4,
            version=2,
        )

    def test_pack(self):
        self.assertPacked(
            BinaryRTCMDataOutput,
            b"\x20\x01\x00\x01\x01\x01\x00\x01\x01\x00\x00\x00\x00\x00\x00\x02\x01",
            rtcm_output=True,
            output_rate=BinaryUpdateRate.r1Hz,
            stationary_rtk=True,
            gps_msm7=True,
            glonass_msm7=True,
            galileo_msm7=False,
            sbas_msm7=True,
            qzss_msm7=True,
            bds_msm7=False,
            gps_ephemeris_interval=0,
            glonass_ephemeris_interval=0,
            beidou_ephemeris_interval=0,
            galileo_ephemeris_interval=0,
            rtcm_type=RTCMType.MSM7,
            version=2,
            persist=True,
        )


class TestConfigureBasePosition(MessageTestCase):
    def test_pack(self):
        packed_data = (
            b"\x22\x02\x00\x00\x07\xD0\x00\x00\x00\x1E\x40\x38\xC7\xAE\x14\x7A\xE1\x48\x40"
            b"\x5E\x40\x00\x00\x00\x00\x00\x42\xDC\x00\x00\x01"
        )
        self.assertPacked(
            ConfigureBasePositionInput,
            packed_data,
            base_position_mode=BasePositionMode.static_mode,
            survey_length=0x7D0,
            standard_deviation=0x1E,
            latitude=b"\x40\x38\xC7\xAE\x14\x7A\xE1\x48",
            longitude=b"\x40\x5E\x40\x00\x00\x00\x00\x00",
            ellipsoidal_height=b"\x42\xDC\x00\x00",
            persist=True,
            kw_types="iiiddfi",
        )

    def test_unpack(self):
        packed_data = (
            b"\x8B\x02\x00\x00\x00\x00\x20\x00\xB3\x00\x40\x38\xC7\xAE\x14\x7A\xE1\x48\x40"
            b"\x5E\x40\x00\x00\x00\x00\x01\x42\xDC\x00\x00\x02\x00\x00\x07\xD0"
        )
        self.assertUnpacked(
            ConfigureBasePositionOutput,
            packed_data,
            base_position_mode=BasePositionMode.static_mode,
            survey_length=0,
            standard_deviation=0x2000B300,
            latitude=b"\x40\x38\xC7\xAE\x14\x7A\xE1\x48",
            longitude=b"\x40\x5E\x40\x00\x00\x00\x00\x01",
            ellipsoidal_height=b"\x42\xDC\x00\x00",
            runtime_base_position_mode=BasePositionMode.static_mode,
            runtime_survey_length=0x7D0,
            kw_types="iiiddfiii",
        )


class TestGetGPSEphemeris(MessageTestCase):
    def test_pack(self):
        self.assertPacked(GetGPSEphemeris, b"\x30\x00", satellite_number=0)


class TestGPSEphemeris(MessageTestCase):
    def test_pack(self):
        packed_data = (
            b"\x41\x00\x02\x00\x77\x88\x04\x61\x10\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
            b"\x00\x00\xDB\xDF\x59\xA6\x00\x00\x1E\x0A\x47\x7C\x00\x77\x88\x88\xDF\xFD\x2E"
            b"\x35\xA9\xCD\xB0\xF0\x9F\xFD\xA7\x04\x8E\xCC\xA8\x10\x2C\xA1\x0E\x22\x31\x59"
            b"\xA6\x74\x00\x77\x89\x0C\xFF\xA3\x59\x86\xC7\x77\xFF\xF8\x26\x97\xE3\xB9\x1C"
            b"\x60\x59\xC3\x07\x44\xFF\xA6\x37\xDF\xF0\xB0"
        )
        self.assertPacked(
            GPSEphemeris,
            packed_data,
            satellite_number=2,
            eph_data_subframe1=(
                b"\x00\x77\x88\x04\x61\x10\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
                b"\xDB\xDF\x59\xA6\x00\x00\x1E\x0A\x47\x7C"
            ),
            eph_data_subframe2=(
                b"\x00\x77\x88\x88\xDF\xFD\x2E\x35\xA9\xCD\xB0\xF0\x9F\xFD\xA7\x04\x8E\xCC"
                b"\xA8\x10\x2C\xA1\x0E\x22\x31\x59\xA6\x74"
            ),
            eph_data_subframe3=(
                b"\x00\x77\x89\x0C\xFF\xA3\x59\x86\xC7\x77\xFF\xF8\x26\x97\xE3\xB9\x1C\x60"
                b"\x59\xC3\x07\x44\xFF\xA6\x37\xDF\xF0\xB0"
            ),
        )

    def test_unpack(self):
        packed_data = (
            b"\xB1\x00\x02\x00\x77\x88\x04\x61\x10\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
            b"\x00\x00\xDB\xDF\x59\xA6\x00\x00\x1E\x0A\x47\x7C\x00\x77\x88\x88\xDF\xFD\x2E"
            b"\x35\xA9\xCD\xB0\xF0\x9F\xFD\xA7\x04\x8E\xCC\xA8\x10\x2C\xA1\x0E\x22\x31\x59"
            b"\xA6\x74\x00\x77\x89\x0C\xFF\xA3\x59\x86\xC7\x77\xFF\xF8\x26\x97\xE3\xB9\x1C"
            b"\x60\x59\xC3\x07\x44\xFF\xA6\x37\xDF\xF0\xB0"
        )

        self.assertUnpacked(
            GPSEphemeris,
            packed_data,
            satellite_number=2,
            eph_data_subframe1=(
                b"\x00\x77\x88\x04\x61\x10\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
                b"\xDB\xDF\x59\xA6\x00\x00\x1E\x0A\x47\x7C"
            ),
            eph_data_subframe2=(
                b"\x00\x77\x88\x88\xDF\xFD\x2E\x35\xA9\xCD\xB0\xF0\x9F\xFD\xA7\x04\x8E\xCC"
                b"\xA8\x10\x2C\xA1\x0E\x22\x31\x59\xA6\x74"
            ),
            eph_data_subframe3=(
                b"\x00\x77\x89\x0C\xFF\xA3\x59\x86\xC7\x77\xFF\xF8\x26\x97\xE3\xB9\x1C\x60"
                b"\x59\xC3\x07\x44\xFF\xA6\x37\xDF\xF0\xB0"
            ),
        )

    def test_subframe1_fields(self):
        msg = GPSEphemeris.unpack(
            b"\xB1\x00\x02\x00\x77\x88\x04\x61\x10\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
            b"\x00\x00\xDB\xDF\x59\xA6\x00\x00\x1E\x0A\x47\x7C\x00\x77\x88\x88\xDF\xFD\x2E"
            b"\x35\xA9\xCD\xB0\xF0\x9F\xFD\xA7\x04\x8E\xCC\xA8\x10\x2C\xA1\x0E\x22\x31\x59"
            b"\xA6\x74\x00\x77\x89\x0C\xFF\xA3\x59\x86\xC7\x77\xFF\xF8\x26\x97\xE3\xB9\x1C"
            b"\x60\x59\xC3\x07\x44\xFF\xA6\x37\xDF\xF0\xB0"
        )

        self.assertDictEqual(
            msg.subframe1_fields,
            {
                "sf1_how": b"\x77\x88\x04",
                "wn": 388,
                "ca_or_P_on_l2": 1,
                "ura_index": 0,
                "sv_health": 0,
                "iodc": 0b0011011111,
                "l2_p_data_flag": 0,
                "t_gd": -37,
                "t_oc": 0x59A6,
                "a_f2": 0,
                "a_f1": 30,
                "a_f0": 0x291DF,
            },
        )

    def test_subframe2_fiels(self):
        msg = GPSEphemeris.unpack(
            b"\xB1\x00\x02\x00\x77\x88\x04\x61\x10\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
            b"\x00\x00\xDB\xDF\x59\xA6\x00\x00\x1E\x0A\x47\x7C\x00\x77\x88\x88\xDF\xFD\x2E"
            b"\x35\xA9\xCD\xB0\xF0\x9F\xFD\xA7\x04\x8E\xCC\xA8\x10\x2C\xA1\x0E\x22\x31\x59"
            b"\xA6\x74\x00\x77\x89\x0C\xFF\xA3\x59\x86\xC7\x77\xFF\xF8\x26\x97\xE3\xB9\x1C"
            b"\x60\x59\xC3\x07\x44\xFF\xA6\x37\xDF\xF0\xB0"
        )

        self.assertDictEqual(
            msg.subframe2_fields,
            {
                 "how" : b"\x77\x88\x88",
                 "iode" : 0xDF,
                 "c_rs" : 0xFD2E,
                 "delta_n" : 0x35A9,
                 "M_0" : 0xCDB0F09F,
                 "C_UC" : 0xFDA7,
                 "e" : 0x048ECCA8,
                 "C_us" : 0x102C,
                 "root_a" : 0xA10E2231,
                 "t_oe" : 0x59A6,
                 "fit_interval_flag" : 0x0,
                 "AODO" : 0x1D,
            },
        )

    def test_subframe2_fiels(self):
        msg = GPSEphemeris.unpack(
            b"\xB1\x00\x02\x00\x77\x88\x04\x61\x10\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
            b"\x00\x00\xDB\xDF\x59\xA6\x00\x00\x1E\x0A\x47\x7C\x00\x77\x88\x88\xDF\xFD\x2E"
            b"\x35\xA9\xCD\xB0\xF0\x9F\xFD\xA7\x04\x8E\xCC\xA8\x10\x2C\xA1\x0E\x22\x31\x59"
            b"\xA6\x74\x00\x77\x89\x0C\xFF\xA3\x59\x86\xC7\x77\xFF\xF8\x26\x97\xE3\xB9\x1C"
            b"\x60\x59\xC3\x07\x44\xFF\xA6\x37\xDF\xF0\xB0"
        )

        self.assertDictEqual(
            msg.subframe3_fields,
            {
                "sf3_how" : b"\x77\x89\x0C",
                "C_ic" : 0xFFA3,
                "Omega_0" : 0x5986C777,
                "C_is" : 0xFFF8,
                "I_0" : 0x2697E3B9,
                "C_rc" : 0x1C60,
                "omega" : 0x59C30744,
                "Omega_dot" : 0xFFA637,
                "iode" : 0xDF,
                "iodt" : 0xF0B0 >> 2,
            },
        )


class TestGetGLONASSEphemeris(MessageTestCase):
    def test_pack(self):
        self.assertPacked(
            GetGLONASSEphemeris,
            b"\x5B\x00",
            satellite_number=0,
        )


class TestGLONASSEphemeris(MessageTestCase):
    def test_pack(self):
        packed_data = (
            b"\x5C\x02\xFC\x01\x02\x57\x07\x56\x1C\x9D\x2F\xE6\x84\x02\x12\x60\x99\x5C\xB8"
            b"\x0A\x7A\x7D\x33\x03\x80\x26\x30\xC3\x9B\xA1\x78\x6A\x18\x04\x83\x4C\x84\xC0"
            b"\x00\x02\xA1\x6D\x89"
        )
        self.assertPacked(
            GLONASSEphemeris,
            packed_data,
            slot_number=2,
            k_number=-4,
            eph_data0=b"\x01\x02\x57\x07\x56\x1C\x9D\x2F\xE6\x84",
            eph_data1=b"\x02\x12\x60\x99\x5C\xB8\x0A\x7A\x7D\x33",
            eph_data2=b"\x03\x80\x26\x30\xC3\x9B\xA1\x78\x6A\x18",
            eph_data3=b"\x04\x83\x4C\x84\xC0\x00\x02\xA1\x6D\x89",
        )

    def test_unpack(self):
        packed_data = (
            b"\x90\x02\xFC\x01\x02\xD2\x81\xF4\x75\x05\x16\x51\x9A\x02\x12\xE0\xAD\x0F\x37"
            b"\x01\x7A\xD2\x06\x03\x80\x26\x19\xA1\x22\xA2\x84\xEB\xD6\x04\x83\x4C\xA8\xC0"
            b"\x00\x02\xA1\x6D\x89"
        )
        self.assertUnpacked(
            GLONASSEphemeris,
            packed_data,
            slot_number=2,
            k_number=-4,
            eph_data0=b"\x01\x02\xD2\x81\xF4\x75\x05\x16\x51\x9A",
            eph_data1=b"\x02\x12\xE0\xAD\x0F\x37\x01\x7A\xD2\x06",
            eph_data2=b"\x03\x80\x26\x19\xA1\x22\xA2\x84\xEB\xD6",
            eph_data3=b"\x04\x83\x4C\xA8\xC0\x00\x02\xA1\x6D\x89",
        )


class TestReceiverSoftwareVersion(MessageTestCase):
    def test_unpack(self):
        self.assertUnpacked(
            ReceiverSoftwareVersion,
            b"\x80\x01\x00\x01\x01\x01\x00\x01\x03\x0E\x00\x07\x01\x12",
            software_type=1,
            kernel_version=0x00010101,
            odm_version=0x0001030E,
            revision=0x00070112,
        )


class TestReceiverSoftwareCRC(MessageTestCase):
    def test_unpack(self):
        self.assertUnpacked(
            ReceiverSoftwareCRC,
            b"\x81\x01\x98\x76",
            software_type=1,
            crc=0x9876,
        )


class TestMeasurementTimeInformation(MessageTestCase):
    def test_unpack(self):
        self.assertUnpacked(
            MeasurementTimeInformation,
            b"\xDC\x3D\x06\xED\x0B\x0C\xBC\x40\x03\xE8",
            iod=0x3D,
            receiver_wn=0x06ED,
            receiver_tow=0x0B0CBC40,
            measurement_period=0x03E8,
        )


class TestRawMeasurementsArray(MessageTestCase):
    def test_unpack(self):
        expected_array_data = [
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
        packed_data = (
            b"\xDD\x3D\x0F\x02\x2B\x41\x74\x42\xDB\x76\x55\xFA\x29\xC0\xE2\xE4\x02\x21\x5A"
            b"\x00\x00\x44\x20\x80\x00\x07\x09\x29\x41\x77\x8C\xF0\xA9\xE7\x0C\x43\xC0\xF9"
            b"\x72\x54\x2E\xEB\x80\x00\x44\xE3\xA0\x00\x07\x0A\x28\x41\x75\xCA\x96\x91\xA9"
            b"\xE9\x23\x41\x04\x7D\xB1\xE9\xA9\x80\x00\xC5\x31\x20\x00\x07\x05\x2B\x41\x74"
            b"\x9E\xBE\xEE\x17\x8C\x6A\x40\xD3\x71\xD4\x80\xCF\x00\x00\xC3\xAE\x00\x00\x07"
            b"\x1A\x2E\x41\x75\x02\x83\xE5\xEC\xD7\x65\xC1\x04\x6D\x73\xBD\xE6\x20\x00\x45"
            b"\x33\x30\x00\x07\x0C\x28\x41\x77\xC1\xE0\x1D\xA7\x2E\xC1\x40\xFF\x79\x4C\xC9"
            b"\x14\x80\x00\xC5\x0D\x80\x00\x07\x11\x28\x41\x77\xE7\xB0\xE8\x15\x9A\xA8\x41"
            b"\x0C\x87\x99\x0C\xFA\xA0\x00\xC5\x80\xD8\x00\x07\x0F\x27\x41\x77\x93\x96\x77"
            b"\x03\x2B\x0A\xC1\x06\xBF\x2C\x49\x05\x60\x00\x45\x4F\xB0\x00\x07\x04\x2C\x41"
            b"\x75\xBA\x4E\xB0\x68\x2B\x43\x40\xFB\x25\xC7\xA3\xB6\xC0\x00\xC4\xFE\x60\x00"
            b"\x07\x07\x26\x41\x78\x48\x7F\x72\xDF\xC5\x81\xC0\xD0\x89\xC8\xBF\x96\x00\x00"
            b"\x43\xA7\x80\x00\x07\x0D\x1D\x00\x00\x00\x00\x00\x00\x00\x00\x41\x05\xF9\xA2"
            b"\xD6\x0D\x40\x00\xC5\x66\x00\x00\x16\x08\x27\x41\x78\x6A\xD7\xA4\x71\x2A\x50"
            b"\xC0\xEF\x02\x44\x2E\x09\x80\x00\x44\xA2\x80\x00\x07\x19\x23\x41\x78\x7E\xE4"
            b"\x8B\x0C\x9E\x26\x40\xE6\xAD\x04\x2B\x85\x80\x00\xC4\x98\x20\x00\x07\x42\x1F"
            b"\x41\x75\x27\xEA\xE2\x16\x7D\x10\x41\x06\xD6\x0A\x57\x6B\x00\x00\xC5\x53\x10"
            b"\x00\x07\x52\x1E\x00\x00\x00\x00\x00\x00\x00\x00\xC0\xFE\x83\x49\x5D\xA7\x00"
            b"\x00\x45\x16\xC0\x00\x06"
        )

        self.assertArrUnpacked(
            RawMeasurementsArray,
            RawMeasurement,
            packed_data,
            expected_array_data,
            "iiddfi",
            iod=0x3D,
        )


class TestSattelliteChannelStatuses(MessageTestCase):
    def test_unpack(self):
        packed_data = (
            b"\xDE\x3D\x10\x00\x02\x07\x01\x2B\x00\x3E\x00\x10\x1F\x01\x09\x07\x01\x29\x00"
            b"\x10\x00\x72\x1F\x02\x0A\x07\x01\x28\x00\x22\x00\x27\x1F\x03\x05\x07\x00\x2B"
            b"\x00\x38\x01\x38\x1F\x04\x1A\x07\x00\x2E\x00\x2E\x00\xBA\x1F\x05\x0C\x07\x00"
            b"\x28\x00\x0E\x00\xF8\x1F\x06\x11\x07\x01\x28\x00\x0A\x00\x9A\x1F\x07\x0F\x07"
            b"\x00\x27\x00\x0E\x00\xD1\x1F\x08\x21\x07\x00\x29\x00\x42\x00\x2E\x1F\x09\x04"
            b"\x07\x00\x2C\x00\x26\x00\x5B\x1F\x0C\x07\x07\x00\x26\x00\x09\x00\x4D\x1F\x0D"
            b"\x0D\x07\x00\x1D\x00\x06\x00\x24\x1F\x0E\x08\x07\x00\x27\x00\x0A\x00\x6B\x1F"
            b"\x0F\x19\x07\x00\x23\x00\x06\x01\x1B\x1F\x10\x42\x06\x05\x1F\x00\x20\x00\x15"
            b"\x1F\x11\x52\x07\x05\x1E\x00\x31\x01\x4E\x1F"
        )

        expected_array_data = [
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

        self.assertArrUnpacked(
            SattelliteChannelStatuses,
            SattelliteChannelStatus,
            packed_data,
            expected_array_data,
            [
                "i",
                "i",
                SattelliteStatusIndicator,
                "i",
                "i",
                "i",
                "i",
                SattelliteChannelStatusIndicator,
            ],
            iod=0x3D,
        )


class TestReceiverNavigationStatus(MessageTestCase):
    def test_unpack(self):
        # the example message from the reference doc has a typo in this message. The clock
        # bias field ends in 0x78 in the packed message but 0x68 in the message table. I
        # just went with the 0x68 version
        packed_data = (
            b"\xDF\x92\x03\x06\xED\x41\x07\xDB\xE7\xFD\x76\x3B\x21\xC1\x46\xC6\x04\x2F\x62"
            b"\xBF\xD8\x41\x52\xF1\xB6\x4B\x17\xF7\xCC\x41\x44\x46\x79\xB8\x7A\xDB\x12\x3C"
            b"\x8A\xAA\xD4\xBC\x1A\x6E\xF0\xBB\xC5\x67\xD2\x41\x16\xAD\x5E\x6D\x3F\x7C\x78"
            b"\x42\x8F\xD9\x1E\x40\x5D\x7C\x6B\x40\x4B\x07\xFB\x3F\x7C\x51\xAD\x40\x40\xFB"
            b"\xC2\x3F\xB1\x06\x30"
        )

        self.assertUnpacked(
            ReceiverNavigationStatus,
            packed_data,
            kw_types=[
                "i",
                NavigationState,
                "i",
                "d",
                "d",
                "d",
                "d",
                "f",
                "f",
                "f",
                "d",
                "f",
                "f",
                "f",
                "f",
                "f",
                "f",
            ],
            iod=0x92,
            navigation_state=0x03,
            week_number=0x06ED,
            time_of_week=b"\x41\x07\xDB\xE7\xFD\x76\x3B\x21",
            ecef_x=b"\xC1\x46\xC6\x04\x2F\x62\xBF\xD8",
            ecef_y=b"\x41\x52\xF1\xB6\x4B\x17\xF7\xCC",
            ecef_z=b"\x41\x44\x46\x79\xB8\x7A\xDB\x12",
            ecef_x_vel=b"\x3C\x8A\xAA\xD4",
            ecef_y_vel=b"\xBC\x1A\x6E\xF0",
            ecef_z_vel=b"\xBB\xC5\x67\xD2",
            clock_bias=b"\x41\x16\xAD\x5E\x6D\x3F\x7C\x78",
            clock_drift=b"\x42\x8F\xD9\x1E",
            gdop=b"\x40\x5D\x7C\x6B",
            pdop=b"\x40\x4B\x07\xFB",
            hdop=b"\x3F\x7C\x51\xAD",
            vdop=b"\x40\x40\xFB\xC2",
            tdop=b"\x3F\xB1\x06\x30",
        )


class TestGPSSubframe(MessageTestCase):
    def test_unpack(self):
        packed_data = (
            b"\xE0\x02\x05\x8B\x0B\xB4\x3F\x22\xB5\x4F\x31\xCF\x4E\xFD\x81\xFD\x4D\x00\xA1"
            b"\x0C\x98\x79\xE7\x09\x08\xD5\xC5\xF8\xED\x03\xEB\xFF\xF4"
        )

        self.assertUnpacked(
            GPSSubframe,
            packed_data,
            svid=0x02,
            sfid=0x05,
            words=(
                b"\x8B\x0B\xB4\x3F\x22\xB5\x4F\x31\xCF\x4E\xFD\x81\xFD\x4D\x00\xA1\x0C\x98"
                b"\x79\xE7\x09\x08\xD5\xC5\xF8\xED\x03\xEB\xFF\xF4"
            ),
        )


class TestGLONASSString(MessageTestCase):
    def test_unpack(self):
        self.assertUnpacked(
            GLONASSString,
            b"\xE1\x52\x0E\xB4\x05\xA9\xC3\x94\x17\x50\x04\x82",
            svid=0x52,
            string_number=0x0E,
            words=b"\xB4\x05\xA9\xC3\x94\x17\x50\x04\x82",
        )


class TestBeidou2D1Subframe(MessageTestCase):
    def test_unpack(self):
        packed_data = (
            b"\xE2\xCF\x01\xE2\x40\x47\x37\x58\x00\x0D\xA0\xE1\x00\xAC\x03\x87\x8E\x31\x5B"
            b"\x53\xB4\x12\xB2\xC0\x02\x5B\x04\x60\x07\xAB\x81"
        )

        self.assertUnpacked(
            Beidou2D1Subframe,
            packed_data,
            svid=0xCF,
            sfid=0x01,
            words=(
                b"\xE2\x40\x47\x37\x58\x00\x0D\xA0\xE1\x00\xAC\x03\x87\x8E\x31\x5B\x53"
                b"\xB4\x12\xB2\xC0\x02\x5B\x04\x60\x07\xAB\x81"
            ),
        )


class TestBeidou2D2Subframe(MessageTestCase):
    def test_unpack(self):
        packed_data = (
            b"\xE3\xCB\x01\xE2\x40\x47\x37\x95\xA5\x14\xC8\xCA\xEA\xCF\xA5\x00\x15\x55\x55"
            b"\x55\x55\x55\x55\x55\x55\x55\x55\x55\x55\x55\x55"
        )

        self.assertUnpacked(
            Beidou2D2Subframe,
            packed_data,
            svid=0xCB,
            sfid=0x01,
            words=(
                b"\xE2\x40\x47\x37\x95\xA5\x14\xC8\xCA\xEA\xCF\xA5\x00\x15\x55\x55\x55\x55"
                b"\x55\x55\x55\x55\x55\x55\x55\x55\x55\x55"
            ),
        )


class TestExtendedRawMeasurement(MessageTestCase):
    def test_unpack(self):
        packed_data = (
            b"\xE5\x01\x0D\x07\x7C\x06\xAC\x40\x80\x03\xE8\x00\x00\x11\x00\x0D\xE0\x32\x41"
            b"\xB3\x33\x99\x89\x62\xC9\xBA\x41\xB3\x7F\x98\xFD\xAD\xE0\x00\x45\x79\x40\x00"
            b"\x00\x00\x00\x40\x07\x00\x00\x00\x02\xE0\x31\x41\xB3\x22\x3E\xED\xEA\xFB\xD6"
            b"\x41\xB3\xB3\xB8\x3A\xEB\xA0\x00\x44\xF1\x40\x00\x00\x00\x00\x40\x07\x00\x00"
            b"\x00\x06\xE0\x30\x41\xB3\x31\xEE\x4F\x2D\x2C\xD9\x41\xB3\xE3\x77\x47\x15\x20"
            b"\x00\xC3\x39\x00\x00\x00\x00\x00\x40\x07\x00\x00\x00\x04\xE0\x33\x41\xB3\x21"
            b"\xA6\x72\x9C\x9E\x8D\x41\xB3\x97\x3F\x77\x2B\x60\x00\x45\x2E\xF0\x00\x00\x00"
            b"\x00\x40\x07\x00\x00\x00\x05\xE0\x31\x41\xB3\x24\x52\x84\x6C\x89\x0E\x41\xB3"
            b"\xC4\xEF\x07\xA8\xE0\x00\x44\x7C\xC0\x00\x00\x00\x00\x40\x07\x00\x00\x00\x0C"
            b"\xE0\x29\x41\xB3\x55\xD6\xAE\x07\x64\xC5\x41\xB3\xF5\x9A\xF1\xB5\xE0\x00\xC4"
            b"\x7C\x00\x00\x00\x00\x00\xC0\x07\x00\x00\x00\x14\xE0\x29\x41\xB3\x53\x25\x16"
            b"\x98\x94\x03\x41\xB3\x99\xD7\x19\x9B\x60\x00\x45\x40\x60\x00\x00\x00\x00\x80"
            b"\x07\x00\x00\x00\x13\xE0\x2C\x41\xB3\x48\x02\x4B\x63\xBF\xD0\x41\xB4\x15\x80"
            b"\x1A\xC7\x60\x00\xC5\x16\xD0\x00\x00\x00\x00\x40\x07\x00\x00\x04\xC1\xE0\x30"
            b"\x41\xB4\x3D\x68\x15\x86\x5B\x87\x41\xB3\xD2\x37\xDB\x1A\x20\x00\x44\x3D\x00"
            b"\x00\x00\x00\x00\x40\x07\x00\x00\x01\x80\xC0\x2D\x41\xB4\x26\x6A\x74\xEB\xC0"
            b"\x97\x41\xB3\xCC\x0C\x45\x53\xA0\x00\x44\x71\x00\x00\x00\x00\x00\x40\x07\x00"
            b"\x00\x01\x81\xC0\x2B\x41\xB4\x19\xE0\xD3\xAB\x6B\xBA\x41\xB3\xCC\xAC\xC2\xC4"
            b"\x20\x00\x44\x6F\xC0\x00\x00\x00\x00\x40\x07\x00\x00\x02\x06\xE3\x31\x41\xB3"
            b"\x15\x16\x02\x23\x16\x1C\x41\xB4\x0A\x57\x97\x61\x20\x00\x44\xBA\xA0\x00\x00"
            b"\x00\x00\x40\x07\x00\x00\x02\x05\xE8\x2D\x41\xB3\x21\xD8\x78\x41\x5F\x35\x41"
            b"\xB4\x5E\x18\x7C\x73\xA0\x00\xC4\xE3\x00\x00\x00\x00\x00\x40\x07\x00\x00\x02"
            b"\x14\xE9\x2D\x41\xB3\x0B\x52\x79\xC4\x94\x08\x41\xB4\x0F\xE8\x10\xA1\x60\x00"
            b"\x44\x9E\x40\x00\x00\x00\x00\x40\x07\x00\x00\x02\x13\xEA\x2C\x41\xB3\x30\x72"
            b"\x52\x8C\x68\x0F\x41\xB4\x68\x6E\x04\xCF\xE0\x00\xC5\x0F\x90\x00\x00\x00\x00"
            b"\x40\x07\x00\x00\x02\x15\xEB\x2F\x41\xB3\x2A\x46\xFD\x31\x68\x39\x41\xB3\xD0"
            b"\x8E\xE5\x12\xE0\x00\x45\x8D\xA8\x00\x00\x00\x00\x40\x07\x00\x00\x02\x07\xEC"
            b"\x2C\x41\xB3\x45\xAB\x04\x39\x61\xD6\x41\xB3\xE5\x52\x58\x10\x20\x00\x45\x72"
            b"\xB0\x00\x00\x00\x00\x80\x07\x00\x00"
        )

        expected_data = [
            (
                0,
                0,
                0xD,
                0xE,
                0,
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
                0xE,
                0,
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
                0xE,
                0,
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
                0xE,
                0,
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
                0xE,
                0,
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
                0xE,
                0,
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
                0xE,
                0,
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
                0xE,
                0,
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
                0,
                0x4,
                0xC1,
                0xE,
                0,
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
                0,
                0x1,
                0x80,
                0xC,
                0,
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
                0,
                0x1,
                0x81,
                0xC,
                0,
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
                0,
                0x2,
                0x6,
                0xE,
                0x3,
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
                0,
                0x2,
                0x5,
                0xE,
                0x8,
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
                0,
                0x2,
                0x14,
                0xE,
                0x9,
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
                0,
                0x2,
                0x13,
                0xE,
                0xA,
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
                0,
                0x2,
                0x15,
                0xE,
                0xB,
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
                0,
                0x2,
                0x7,
                0xE,
                0xC,
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

        self.assertArrUnpacked(
            ExtendedRawMeasurements,
            ExtendedRawMeasurement,
            packed_data,
            expected_data,
            [GNSSType, "i", "i", "i", "i", "i", "d", "d", "f", "i", "i", "i", "i", "b"],
            iod=0x0D,
            version=0x01,
            receiver_wn=0x077C,
            tow=0x06AC4080,
            measurement_period=0x03E8,
            measurement_indicator=0x00,
            reserved=b"\x00",
        )


class TestGNSSSatelliteStatuses(MessageTestCase):
    def test_unpack(self):
        packed_data = (
            b"\xE7\x01\x07\x14\x01\x00\x01\x01\xFF\x2E\x03\x02\x00\x07\x01\xFF\x2D\x03\x03"
            b"\x00\x03\x01\xFF\x2C\x03\x04\x00\x1E\x01\xFF\x2B\x03\x05\x00\x16\x01\xFF\x2D"
            b"\x03\x0E\x05\x03\x00\x00\x2C\x07\x0F\x05\x07\x00\x00\x2F\x03\x10\x05\x08\x00"
            b"\x00\x2D\x03\x11\x05\x0A\x00\x00\x2C\x03\x12\x05\x01\x00\x00\x2B\x03\x19\x03"
            b"\x01\x01\x01\x2C\x07\x1A\x03\x0D\x00\x01\x28\x03\x1B\x03\x12\x00\x01\x00\x01"
            b"\x2B\x55\x03\x00\x00\x20\x07\x2C\x55\x07\x00\x00\x21\x03\x2D\x55\x08\x00\x00"
            b"\x21\x03\x2E\x55\x0A\x00\x00\x21\x03\x2F\x55\x01\x00\x00\x21\x03\x31\x53\x01"
            b"\x01\x01\x25\x07\x32\x53\x0D\x00\x01\x22\x03"
        )

        expected_data = [
            (0x01, 0, 0, 0x01, 1, 0xFF, 0x2E, 3),
            (0x02, 0, 0, 0x07, 1, 0xFF, 0x2D, 3),
            (0x03, 0, 0, 0x03, 1, 0xFF, 0x2C, 3),
            (0x04, 0, 0, 0x1E, 1, 0xFF, 0x2B, 3),
            (0x05, 0, 0, 0x16, 1, 0xFF, 0x2D, 3),
            (0x0E, 0, 5, 0x03, 0, 0x00, 0x2C, 7),
            (0x0F, 0, 5, 0x07, 0, 0x00, 0x2F, 3),
            (0x10, 0, 5, 0x08, 0, 0x00, 0x2D, 3),
            (0x11, 0, 5, 0x0A, 0, 0x00, 0x2C, 3),
            (0x12, 0, 5, 0x01, 0, 0x00, 0x2B, 3),
            (0x19, 0, 3, 0x01, 1, 0x01, 0x2C, 7),
            (0x1A, 0, 3, 0x0D, 0, 0x01, 0x28, 3),
            (0x1B, 0, 3, 0x12, 0, 0x01, 0x00, 1),
            (0x2B, 5, 5, 0x03, 0, 0x00, 0x20, 7),
            (0x2C, 5, 5, 0x07, 0, 0x00, 0x21, 3),
            (0x2D, 5, 5, 0x08, 0, 0x00, 0x21, 3),
            (0x2E, 5, 5, 0x0A, 0, 0x00, 0x21, 3),
            (0x2F, 5, 5, 0x01, 0, 0x00, 0x21, 3),
            (0x31, 5, 3, 0x01, 1, 0x01, 0x25, 7),
            (0x32, 5, 3, 0x0D, 0, 0x01, 0x22, 3),
        ]
        self.assertArrUnpacked(
            GNSSSatelliteStatuses,
            GNSSSatelliteStatus,
            packed_data,
            expected_data,
            [
                "i",
                "i",
                GNSSType,
                "i",
                SattelliteStatusIndicator,
                "i",
                "i",
                SattelliteChannelStatusIndicator,
            ],
            version=1,
            iod=7,
        )
