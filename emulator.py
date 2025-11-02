"""
Simple UDP proxy that forwards between sender and receiver while introducing
packet loss, delay, and jitter. Run as the middleman.
"""

import socket
import threading
import random
import time
import argparse

# CONFIG
# Proxy to intercept sender & receiver packets
EMULATOR_PROXY = ('127.0.0.1', 11000)
RECEIVER_ADDR = ('127.0.0.1', 12001)
SENDER_ADDR = ('127.0.0.1', 12000)
VERBOSE = True


def run_emulator():
    """Main emulator loop. Call this only when running emulator.py directly."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(EMULATOR_PROXY)
    sock.setblocking(True)

    def send_with_delay(data, dest, delay_ms):
        def _send():
            if VERBOSE:
                print(
                    f"[EMULATOR] sleeping {delay_ms:.1f}ms then forwarding to {dest}")
            time.sleep(delay_ms / 1000.0)
            sock.sendto(data, dest)
        t = threading.Thread(target=_send, daemon=True)
        t.start()

    print("[EMULATOR] running at", EMULATOR_PROXY)
    print("[EMULATOR] forwarding between sender",
          SENDER_ADDR, "and receiver", RECEIVER_ADDR)
    print(
        f"[EMULATOR] LOSS={LOSS_RATE*100:.1f}%, mean_delay={MEAN_DELAY_MS}ms, jitter={JITTER_MS}ms\n")

    try:
        while True:
            data, addr = sock.recvfrom(65536)

            # Determine direction
            if addr[1] == SENDER_ADDR[1]:
                dest = RECEIVER_ADDR
                src_label = "SENDER"
            elif addr[1] == RECEIVER_ADDR[1]:
                dest = SENDER_ADDR
                src_label = "RECEIVER"
            else:
                dest = RECEIVER_ADDR
                src_label = f"UNKNOWN({addr})"

            # Simulate loss
            if random.random() < LOSS_RATE:
                if VERBOSE:
                    print(
                        f"[EMULATOR] DROPPED pkt from {src_label} ({addr}) -> {dest}")
                continue

            # Delay + jitter
            jitter = random.uniform(-JITTER_MS, JITTER_MS)
            delay_ms = max(0.0, MEAN_DELAY_MS + jitter)
            if VERBOSE:
                print(
                    f"[EMULATOR] received {len(data)} bytes from {src_label} -> scheduling forward ({delay_ms:.1f}ms)")
            send_with_delay(data, dest, delay_ms)
    except KeyboardInterrupt:
        print("\n[EMULATOR] shutting down")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--loss", type=float,
                        default=0.2, help="Drop probability [0-1]")
    parser.add_argument("--delay", type=float,
                        default=30, help="Mean one-way delay in ms")
    parser.add_argument("--jitter", type=float,
                        default=20, help="Jitter range in ms (+/-)")
    parser.add_argument("--quiet", action="store_true",
                        help="Reduce emulator logging")
    args = parser.parse_args()

    LOSS_RATE = max(0.0, min(1.0, args.loss))
    MEAN_DELAY_MS = max(0.0, args.delay)
    JITTER_MS = max(0.0, args.jitter)
    VERBOSE = not args.quiet

    run_emulator()
