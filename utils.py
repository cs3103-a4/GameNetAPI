# utils.py
import struct
import time

HEADER_FORMAT = '!B H Q'  # ChannelType(1B), SeqNo(2B), Timestamp_ms(8B)
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
RELIABLE_CHANNEL = 0
UNRELIABLE_CHANNEL = 1

def now_ms():
    return int(time.time() * 1000)

def pack_packet(channel_type: int, seqno: int, timestamp_ms: int, payload: bytes) -> bytes:
    header = struct.pack(HEADER_FORMAT, channel_type, seqno & 0xFFFF, timestamp_ms)
    return header + payload

def unpack_packet(data: bytes):
    if len(data) < HEADER_SIZE:
        raise ValueError("Packet too short")
    channel_type, seqno, timestamp = struct.unpack(HEADER_FORMAT, data[:HEADER_SIZE])
    payload = data[HEADER_SIZE:]
    return channel_type, seqno, timestamp, payload

def increment_seq(seq):
    return (seq + 1) & 0xFFFF
