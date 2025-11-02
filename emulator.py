"""
Simple UDP proxy that forwards between sender and receiver while introducing
packet loss, delay, and jitter. Run as the middleman.
"""

import socket
import threading
import random
import time

# CONFIG
EMULATOR_PROXY = ('127.0.0.1', 11000)   # Proxy addr where sender & receiver sends to
RECEIVER_ADDR = ('127.0.0.1', 12001)
SENDER_ADDR = ('127.0.0.1', 12000)
LOSS_RATE = 0.2
MEAN_DELAY_MS = 30
JITTER_MS = 20
VERBOSE = True

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(EMULATOR_PROXY)
sock.setblocking(True)

# We will forward packets from Sender->Receiver and Receiver->Sender.
# Since both sides send to this emulator, use the packet's source to know where it's from.

def send_with_delay(data, dest, delay_ms):
    def _send():
        if VERBOSE:
            print(f"[EMULATOR] sleeping {delay_ms:.1f}ms then forwarding to {dest}")
        time.sleep(delay_ms / 1000.0)
        sock.sendto(data, dest)
    t = threading.Thread(target=_send, daemon=True)
    t.start()

print("[EMULATOR] running at", EMULATOR_PROXY)
print("[EMULATOR] forwarding between sender", SENDER_ADDR, "and receiver", RECEIVER_ADDR)
print(f"[EMULATOR] LOSS={LOSS_RATE*100:.1f}%, mean_delay={MEAN_DELAY_MS}ms, jitter={JITTER_MS}ms\n")

try:
    while True:
        data, addr = sock.recvfrom(65536)
        # Decide direction: if from sender port => forward to receiver; else -> sender
        if addr[1] == SENDER_ADDR[1]:
            dest = RECEIVER_ADDR
            src_label = "SENDER"
        elif addr[1] == RECEIVER_ADDR[1]:
            dest = SENDER_ADDR
            src_label = "RECEIVER"
        else:
            # Unknown source: if comes from anything else, try to infer by content;
            # default forward to receiver.
            dest = RECEIVER_ADDR
            src_label = f"UNKNOWN({addr})"

        # Loss check
        if random.random() < LOSS_RATE:
            if VERBOSE:
                print(f"[EMULATOR] DROPPED pkt from {src_label} ({addr}) -> {dest}")
            continue

        # Delay + jitter
        jitter = random.uniform(-JITTER_MS, JITTER_MS)
        delay_ms = max(0.0, MEAN_DELAY_MS + jitter)
        if VERBOSE:
            print(f"[EMULATOR] received {len(data)} bytes from {src_label} -> scheduling forward ({delay_ms:.1f}ms)")
        send_with_delay(data, dest, delay_ms)
except KeyboardInterrupt:
    print("\n[EMULATOR] shutting down")
