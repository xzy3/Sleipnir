import asyncio
from operator import xor
from enum import IntEnum, Enum, auto, Flag, IntFlag
from functools import partial, reduce
from pprint import pprint
from io import BytesIO

import attr
import bitstruct

ACK_TYPE = 0x83
NACK_TYPE = 0x84

MESSAGES_ = {}


def hexdump(b):
    print(b.hex(" ", 1))


packet_preamble = bitstruct.compile("u16u8>")


@attr.s(kw_only=True)
class NavSparkRawProtocol(asyncio.Protocol):
    message_queue: asyncio.Queue = attr.ib(factory=lambda: asyncio.Queue())
    ack_event: asyncio.Event = attr.ib(factory=lambda: asyncio.Event())

    def connection_made(self, transport):
        self.transport = transport
        self.buffer = bytearray()

    def _update_buffer(self, packet_end):
        self.buffer = self.buffer[packet_end + 3 :]

    def _send_ack(self):
        self.transport.write(b"\xA0\xA1\x00\x01\x83\x83\x0D\x0A")

    def _send_nack(self):
        self.transport.write(b"\xA0\xA1\x00\x01\x84\x84\x0D\x0A")

    async def _send_command(self, inst):
        self.ack_event.clear()

        buffer = bytes(inst)
        self.transport.write(b"\xA0\xA1")
        self.transport.write(
            packet_preamble.pack(len(buffer).to_bytes(2, byteorder="big"))
        )
        self.transport.write(buffer)
        lrc = reduce(xor, buffer, cmd)
        self.transport.write(lrc.to_bytes(1))
        self.transport.write(b"\x0D\x0A")

        await self.ack_event.wait()

    def data_received(self, data):
        try:
            self.buffer.extend(data)
            if len(self.buffer) < 8:
                # there have to be at least 8 bytes for a complete packet
                return

            packet_start = self.buffer.find(b"\xA0\xA1")
            if packet_start == -1:
                return

            packet_start += 2  # skip the leader
            l, packet_type = packet_preamble.unpack_from(self.buffer[packet_start:])
            packet_start += 2  # skip the length

            packet_end = self.buffer.find(b"\x0D\x0A", packet_start + l)
            if packet_end == -1:
                return

            if packet_end - packet_start + 1 == l:
                return

            # the length does not include the crc
            lrc = reduce(xor, self.buffer[packet_start:packet_end])
            if lrc != 0:
                # packet lrc wrong
                self._update_buffer(packet_end)
                return

            packet_end -= 1  # backup to before the lrc
            if packet_type == ACK_TYPE or packet_type == NACK_TYPE:
                self.ack_event.set()
                return

            try:
                msg_cls = MESSAGES_[packet_type]

                # hexdump(self.buffer[packet_start:packet_end])

                # We could just ignore queue full exceptions for most packets.
                # The navigation messages would be out of date if we get behind
                # and we just want to catch up to the current state of the world.
                self.message_queue.put_nowait(
                    msg_cls.unpack(self.buffer[packet_start:packet_end])
                )
            except KeyError:
                print("unknown message type", hex(packet_type))

            finally:
                self._update_buffer(packet_end)

        except Exception as ex:
            print(ex)

    def connection_lost(self, exc):
        self.transport.loop.stop()

    def resume_reading(self):
        self.transport.resume_reading()


class MessageDirection(Flag):
    INPUT = auto()
    OUTPUT = auto()
    BOTH = INPUT | OUTPUT


def message_type(
    format_str,
    type,
    /,
    default=0,
    validator=None,
    repr=True,
    eq=True,
    order=None,
    hash=None,
    init=True,
    metadata={},
    converter=None,
    message_direction=MessageDirection.BOTH,
):
    metadata = dict() if not metadata else metadata
    metadata["NavSpark_console"] = {
        "format": format_str,
        "direction": message_direction,
    }
    return attr.ib(
        default=default,
        validator=validator,
        repr=repr,
        eq=eq,
        order=order,
        hash=hash,
        init=init,
        metadata=metadata,
        type=type,
        converter=converter or type,
    )


def UINT8(**kwargs):
    return message_type(">u8", int, **kwargs)


def UINT16(**kwargs):
    return message_type(">u16", int, **kwargs)


def UINT32(**kwargs):
    return message_type(">u32", int, **kwargs)


def SINT8(**kwargs):
    return message_type(">s8", int, **kwargs)


def SINT16(**kwargs):
    return message_type(">s16", int, **kwargs)


def SINT32(**kwargs):
    return message_type(">s32", int, **kwargs)


def SPFP(**kwargs):
    return message_type(">f32", float, **kwargs)


def DPFP(**kwargs):
    return message_type(">f64", float, **kwargs)


def ENUM(e, *, size=8, **kwargs):
    return message_type(f"u{size}", e, converter=e, **kwargs)


def BYTES(l, **kwargs):
    return message_type(f"r{8*l}", bytes, **kwargs)


class PersistSetting(IntEnum):
    update_to_sram = 0
    update_to_both = 1


def PERSIST(message_direction=MessageDirection.INPUT, **kwargs):
    return message_type(
        ">u8",
        PersistSetting,
        message_direction=message_direction,
        converter=lambda v: PersistSetting(int(v)),
        **kwargs,
    )


class EnableSetting(IntEnum):
    disable = 0
    enable = 1


def ENABELED(**kwargs):
    return message_type(
        ">u8", EnableSetting, converter=lambda v: EnableSetting(int(v)), **kwargs
    )


def pack_message_(compiled_struct_format, self):
    return compiled_struct_format.pack(
        attr.asdict(
            self,
            filter=lambda att, val: att.metadata["NavSparkConsole"]["Direction"]
            & Direction.INPUT,
        )
    )


def unpack_message_(compiled_struct_format, cls, data):
    inst = compiled_struct_format.unpack(data)
    return cls(**inst)


def message(
    *msg_ids,
    direction=MessageDirection.BOTH,
    message_length=None,
    input_message_length=None,
):
    if direction is MessageDirection.BOTH and len(msg_ids) != 2:
        raise ValueError("Message direction both requires two ids be given")

    def update_message_attrs(cls, fields):
        results = []
        if msg_ids and direction & MessageDirection.INPUT:
            results.append(
                attr.Attribute(
                    "input_id",
                    msg_ids[0],
                    None,
                    True,
                    True,
                    False,
                    True,
                    False,
                    type=int,
                    metadata={
                        "NavSpark_console": {
                            "format": ">u8",
                            "direction": MessageDirection.INPUT,
                        }
                    },
                )
            )

        if msg_ids and direction & MessageDirection.OUTPUT:
            results.append(
                attr.Attribute(
                    "output_id",
                    msg_ids[-1],
                    None,
                    True,
                    True,
                    False,
                    True,
                    False,
                    type=int,
                    metadata={
                        "NavSpark_console": {
                            "format": ">u8",
                            "direction": MessageDirection.OUTPUT,
                        }
                    },
                )
            )

        results.extend(fields)

        if direction & MessageDirection.INPUT:
            pack_format = {
                attrib.name: attrib.metadata["NavSpark_console"]["format"]
                for attrib in results
                if attrib.metadata["NavSpark_console"]["direction"]
                & MessageDirection.INPUT
            }

            expected_length = input_message_length or message_length
            struct_format = "".join(pack_format.values())
            actual_length = bitstruct.calcsize(struct_format) // 8
            if expected_length != None and actual_length != expected_length:
                print(
                    f"input message {cls.__name__} not the expected length {actual_length} expected {expected_length}"
                )

            cls.__bytes__ = partial(
                pack_message_, bitstruct.compile(struct_format), pack_format.keys()
            )

        if direction & MessageDirection.OUTPUT:
            unpack_format = {
                attrib.name: attrib.metadata["NavSpark_console"]["format"]
                for attrib in results
                if attrib.metadata["NavSpark_console"]["direction"]
                & MessageDirection.OUTPUT
            }

            struct_format = "".join(unpack_format.values())
            actual_length = bitstruct.calcsize(struct_format) // 8
            if message_length != None and actual_length != message_length:
                print(
                    f"output message {cls.__name__} not the expected length {actual_length} expected {message_length}"
                )

            cls.unpack = classmethod(
                partial(
                    unpack_message_,
                    bitstruct.compile(struct_format, list(unpack_format.keys())),
                )
            )

        return results

    def decorator(cls):
        try:
            c = attr.s(slots=True, frozen=True, field_transformer=update_message_attrs)(
                cls
            )
            for i in msg_ids:
                MESSAGES_[i] = c
            return c
        except bitstruct.Error as ex:
            raise Exception(
                f"Error creating class {cls.__module__}.{cls.__name__}"
            ) from ex

    return decorator


def arr_message(msg_id, sub_message_cls, *, message_length=None):
    def update_message_attrs(cls, fields):
        results = []
        results.append(
            attr.Attribute(
                "output_id",
                msg_id,
                None,
                True,
                True,
                False,
                True,
                False,
                type=int,
                metadata={
                    "NavSpark_console": {
                        "format": ">u8",
                        "direction": MessageDirection.OUTPUT,
                    }
                },
            )
        )

        results.extend(fields)
        results.extend(
            [
                attr.Attribute(
                    "array_count",
                    0,
                    None,
                    True,
                    True,
                    False,
                    True,
                    False,
                    type=int,
                    metadata={
                        "NavSpark_console": {
                            "format": ">u8",
                            "direction": MessageDirection.OUTPUT,
                        }
                    },
                ),
                attr.Attribute(
                    "sub_messages",
                    attr.Factory(list),
                    None,
                    True,
                    True,
                    False,
                    True,
                    False,
                    type=list,
                    metadata={
                        "NavSpark_console": {
                            "format": None,
                            "direction": MessageDirection.OUTPUT,
                        }
                    },
                ),
            ]
        )

        unpack_format = {
            attrib.name: attrib.metadata["NavSpark_console"]["format"]
            for attrib in results
            if attrib.metadata["NavSpark_console"]["format"]
        }

        parent_format = "".join(unpack_format.values())
        parent_len = bitstruct.calcsize(parent_format)
        parent_format_compiled = bitstruct.compile(
            parent_format, list(unpack_format.keys())
        )
        if message_length != None and parent_len != message_length * 8:
            print(
                f"message {cls.__name__} is not the expected length {parent_len//8} expected {message_length}"
            )

        unpack_format = {
            attrib.name: attrib.metadata["NavSpark_console"]["format"]
            for attrib in attr.fields(sub_message_cls)
        }

        sub_format = "".join(unpack_format.values())
        sub_format_compiled = bitstruct.compile(sub_format, list(unpack_format.keys()))
        sub_format_len = bitstruct.calcsize(sub_format)

        def unpack_message_arr(cls, buffer):
            parent_inst = parent_format_compiled.unpack(buffer)

            sub_messages = []
            for i in range(parent_len, len(buffer) * 8, sub_format_len):
                sub_messages.append(
                    sub_message_cls(**sub_format_compiled.unpack_from(buffer, offset=i))
                )

            ret = cls(**parent_inst, sub_messages=sub_messages)
            return ret

        cls.unpack = classmethod(unpack_message_arr)
        return results

    def decorator(cls):
        try:
            c = attr.s(slots=True, frozen=True, field_transformer=update_message_attrs)(
                cls
            )
            MESSAGES_[msg_id] = c
            return c
        except bitstruct.Error as ex:
            raise Exception(
                f"Error creating message class {cls.__module__}.{cls.__name__}"
            ) from ex

    return decorator


def simple_message(name, id):
    assert id > 0 and id < 256
    cls = attr.make_class(name, [], slots=True, frozen=True)
    cls.__bytes__ = lambda self: b"\xA0\xA1\x00\x01%(id)c%(id)c\x0D\x0A"
    MESSAGES_[id] = cls
    return cls


class MessageType(IntEnum):
    no_output = 0
    NMEA_message = 1
    binary_message = 2


@message(0x9, direction=MessageDirection.INPUT, message_length=3)
class ConfigureMessageType:
    type = ENUM(MessageType)
    persist = PERSIST()


class UpdateRate(IntEnum):
    r1Hz = 1
    r2Hz = 2
    r4Hz = 4
    r5Hz = 5
    r8Hz = 8
    r10Hz = 10
    r20Hz = 20
    r25Hz = 25
    r40Hz = 40
    r50Hz = 50


simple_message("QueryPositionUpdateRate", 0x10)


@message(0xE, 0x86, message_length=2, input_message_length=3)
class ConfigurePositionUpdateRate:
    update_rate = ENUM(UpdateRate)
    persist = PERSIST()


class BinaryUpdateRate(IntEnum):
    r1Hz = 0
    r2Hz = 1
    r4Hz = 2
    r5Hz = 3
    r10Hz = 4
    r20Hz = 5
    r8Hz = 6


class SubframeEnabeledFlag(IntFlag):
    gps = 0b1
    glonass = 0b10
    galileo = 0b100
    beidou = 0b1000


simple_message("QueryBinaryMeasurementDataOutputStatus", 0x1F)


@message(0x1E, 0x89, message_length=8, input_message_length=9)
class ConfigureBinaryMeasurmentDataOutput:
    output_rate = ENUM(BinaryUpdateRate)
    measure_time = ENABELED()
    raw_measuremnt = ENABELED()
    save_channel_status = ENABELED()
    receive_state = ENABELED()
    subframe_enabeled = ENUM(SubframeEnabeledFlag)
    extended_raw_measurment_enabeled = ENABELED()
    persist = PERSIST()


simple_message("QueryBinaryRTCMDataOutputStatus", 0x21)


@message(0x20, 0x8A, message_length=16, input_message_length=17)
class BinaryRTCMDataOutput:
    rtcm_output = ENABELED()
    output_rate = ENUM(BinaryUpdateRate)
    stationary_rtk = ENABELED()
    gps_msm7 = ENABELED()
    glonass_msm7 = ENABELED()
    reserved0 = UINT8()
    sbas_msm7 = ENABELED()
    qzss_msm7 = ENABELED()
    bds_msm7 = ENABELED()
    reserved = BYTES(6)
    persist = PERSIST()


class BasePositionMode(IntEnum):
    kinematic_mode = 0
    survey_mode = 1
    static_mode = 2


simple_message("QueryBasePosition", 0x23)


@message(0x22, 0x8B, message_length=30, input_message_length=31)
class ConfigureBasePosition:
    base_position_mode = ENUM(BasePositionMode)
    survey_length = UINT32()
    standard_deviation = UINT32()
    latitude = DPFP()
    longitude = DPFP()
    ellipsoidal_height = SPFP()
    persist = PERSIST()


@message(0x30, direction=MessageDirection.INPUT, message_length=2)
class GetGPSEphemeris:
    satellite_number = UINT8()


@message(0x41, 0xB1, message_length=87)
class GPSEphemeris:
    satellite_number = UINT16()
    eph_data_subframe1 = BYTES(28)
    eph_data_subframe2 = BYTES(28)
    eph_data_subframe3 = BYTES(28)


@message(0x58, direction=MessageDirection.INPUT, message_length=2)
class GetGLONASSEphemeris:
    satellite_number = UINT8()


@message(0x5C, 0x90, message_length=43)
class GLONASSEphemeris:
    slot_number = UINT8()
    k_number = SINT8()
    eph_data0 = BYTES(10)
    eph_data1 = BYTES(10)
    eph_data2 = BYTES(10)
    eph_data3 = BYTES(10)


@message(0x80, direction=MessageDirection.OUTPUT, message_length=14)
class ReceiverSoftwareVersion:
    software_type = UINT8()
    kernel_version = UINT32()
    odm_version = UINT32()
    revision = UINT32()


@message(0x81, direction=MessageDirection.OUTPUT, message_length=4)
class ReceiverSoftwareCRC:
    software_type = UINT8()
    crc = UINT16()


# these two can have sub ids but we aren't handling them right now
@message(0x83, direction=MessageDirection.OUTPUT, message_length=2)
class AckRequest:
    ack_id = UINT8()


@message(0x84, direction=MessageDirection.OUTPUT, message_length=2)
class NackRequest:
    nack_id = UINT8()


@message(0xDC, direction=MessageDirection.OUTPUT, message_length=10)
class MeasurementTimeInformation:
    iod = UINT8()
    receiver_wn = UINT16()
    receiver_tow = UINT32()
    measurement_period = UINT16()


class NavigationState(IntEnum):
    NO_FIX = 0
    FIX_PREDICTION = 1
    FIX_2D = 2
    FIX_3D = 3
    FIX_DIFFERENTIAL = 4


@message(0xDF, direction=MessageDirection.OUTPUT)
class ReceiverNavigationStatus:
    iod = UINT8()
    navigation_state = ENUM(NavigationState)
    week_number = UINT16()
    time_of_week = DPFP()
    ecef_x = DPFP()
    ecef_y = DPFP()
    ecef_z = DPFP()
    ecef_x_vel = SPFP()
    ecef_y_vel = SPFP()
    ecef_z_vel = SPFP()
    clock_bias = DPFP()
    clock_drift = SPFP()
    gdop = SPFP()
    pdop = SPFP()
    hdop = SPFP()
    vdop = SPFP()
    tdop = SPFP()


@message(0xE0, direction=MessageDirection.OUTPUT, message_length=33)
class GPSSubframe:
    svid = UINT8()
    sfid = UINT8()
    words = BYTES(30)


@message(0xE1, direction=MessageDirection.OUTPUT, message_length=12)
class GLONASSString:
    svid = UINT8()
    string_number = UINT8()
    words = BYTES(9)


@message(0xE2, direction=MessageDirection.OUTPUT, message_length=31)
class Beidou2D1Subframe:
    svid = UINT8()
    sfid = UINT8()
    words = BYTES(28)


@message(0xE3, direction=MessageDirection.OUTPUT, message_length=31)
class Beidou2D2Subframe:
    svid = UINT8()
    sfid = UINT8()
    words = BYTES(28)


class GPSRawMeasurementIndicator(IntFlag):
    pseudo_range_available = 0b1
    doppler_frequency_available = 0b10
    carrier_phase_available = 0b100
    cycle_slip_possible = 0b1000
    coherent_integration = 0b10000


@message(direction=MessageDirection.OUTPUT, message_length=23)
class RawMeasurement:
    svid = UINT8()
    cn0 = UINT8()
    pseudo_range = DPFP()
    accumulated_carrier_cycle = DPFP()
    doppler_frequency = SPFP()
    measurement_indicator = ENUM(GPSRawMeasurementIndicator)


@arr_message(0xDD, RawMeasurement, message_length=3)
class RawMeasurementsArray:
    iod = UINT8()


class SattelliteStatusIndicator(IntFlag):
    almanac_received = 0b1
    ephemeris_received = 0b10
    healthy_sattellite = 0b100


class SattelliteChannelStatusIndicator(IntFlag):
    pull_in_done = 0b1
    bit_synchronized = 0b10
    frame_synchronized = 0b100
    ephemeris_received = 0b1000
    normal_fix_mode = 0b10000
    differential_fix_mode = 0b100000


@message(direction=MessageDirection.OUTPUT, message_length=10)
class SattelliteChannelStatus:
    channel_id = UINT8()
    svid = UINT8()
    sv_status_indicator = ENUM(SattelliteStatusIndicator)
    ura_ft = UINT8()
    cn0 = SINT8()
    elevation = SINT16()
    azimuth = SINT16()
    channel_status_indicator = ENUM(SattelliteChannelStatusIndicator)


@arr_message(0xDE, SattelliteChannelStatus, message_length=3)
class SattelliteChannelStatuses:
    iod = UINT8()


class GNSSType(IntEnum):
    GPS = 0
    SBAS = 1
    GLONASS = 2
    GALILEO = 3
    QZSS = 4
    BEIDOU = 5
    IRNSS = 6


class ExtendedRawChannelIndicator(IntFlag):
    pseudorange_available = 0b1
    doppler_frequency = 0b10
    carrier_phase_available = 0b100
    cycle_slip_possible = 0b1000
    coherent_integration_time = 0b10000
    unknown_half_cycle_ambiguity = 0b100000


@message(direction=MessageDirection.OUTPUT, message_length=31)
class ExtendedRawMeasurement:
    signal_type = message_type(">u4", int)
    gnss_type = message_type(">u4", GNSSType)
    svid = UINT8()
    frequency_id = message_type(">u4", int)
    lock_time_indicator = message_type(">u4", int)
    cn0 = UINT8()
    pseudorange = DPFP()
    accumulated_carrier_cycle = DPFP()
    doppler_frequency = SPFP()
    pseudorange_standard_dev = UINT8()
    accumulated_carrier_cycle_standard_dev = UINT8()
    doppler_freq_standard_dev = UINT8()
    channel_indicator = ENUM(ExtendedRawChannelIndicator, size=16)
    reserved = BYTES(2)


class MeasurementIndicatorFlags(IntFlag):
    triggerd_by_geotagging = 0b1
    receiver_increment = 0b10
    receiver_decrement = 0b100


@arr_message(0xE5, ExtendedRawMeasurement, message_length=14)
class ExtendedRawMeasurements:
    version = UINT8()
    iod = UINT8()
    receiver_wn = UINT16()
    tow = UINT32()
    measurement_period = UINT16()
    measurement_indicator = ENUM(MeasurementIndicatorFlags)
    reserved = BYTES(1)


if __name__ == "__main__":
    import serial_asyncio

    async def reader():
        transport, protocol = await serial_asyncio.create_serial_connection(
            loop, NavSparkRawProtocol, "/dev/ttyUSB0", baudrate=115200
        )

        await asyncio.sleep(0.3)
        protocol.resume_reading()

        while True:
            msg = await protocol.message_queue.get()
            print(msg)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(reader())
    loop.close()
