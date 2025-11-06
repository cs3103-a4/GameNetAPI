import socket
import threading
import time
import argparse
import json
import os
from collections import deque
from emulator import EMULATOR_PROXY, RECEIVER_ADDR, SENDER_ADDR
from utils import increment_seq, pack_packet, unpack_packet, now_ms, RELIABLE_CHANNEL, UNRELIABLE_CHANNEL
from metrics import ReceiverMetrics, format_receiver_summary

# Timeout t beyond which reliable packet is dropped = 200ms
RETRANSMIT_TIMEOUT_MS = 200

class Receiver:
    def __init__(self, src_socket_addr, dest_socket_addr):
        self.src_socket_addr = src_socket_addr
        self.dest_socket_addr = dest_socket_addr
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(src_socket_addr)
        self.sock.setblocking(False)

        self.seq_to_recv = 0
        # Unreliable packets buffer: FIFO queue of (recv_seq, send_ts, arrival_ts, payload)
        self.unreliable_buffer = deque()
        self.unreliable_seqs = set()  # To increment self.seq_to_recv if alr recv seq num
        # Reliable packets buffer: {recv_seq -> (payload, send_ts, arrival_ts)}
        self.reliable_buffer = {}
        self.last_recv_time = None

        self.unreliable_data_lock = threading.Lock()
        self.reliable_data_lock = threading.Lock()

        self.metrics = ReceiverMetrics()
        self.metrics.start(now_ms())

        self.running_threads = True
        self.recv_thread = threading.Thread(
            target=self._recv_and_ack, daemon=True)
        self.recv_thread.start()

    def recv(self):
        while True:
            now = now_ms()
            # Receive from reliable buffer first
            with self.reliable_data_lock:
                if self.seq_to_recv in self.reliable_buffer:
                    payload, send_ts, arrival_ts = self.reliable_buffer.pop(
                        self.seq_to_recv)
                    seq = self.seq_to_recv
                    self.seq_to_recv = increment_seq(seq)
                    self.last_recv_time = now
                    # Count metrics only on delivery to application layer
                    self.metrics.update_on_receive(
                        RELIABLE_CHANNEL, len(payload), send_ts, arrival_ts)
                    return seq, RELIABLE_CHANNEL, payload
                # Skip seq num if timeout
                if (self.last_recv_time and
                    (now - self.last_recv_time) > RETRANSMIT_TIMEOUT_MS):
                    print(
                        f"[RECEIVER] skipping missing seq={self.seq_to_recv} (200ms timeout)")
                    self.seq_to_recv = increment_seq(self.seq_to_recv)
                    self.last_recv_time = now
            # Then receive from unreliable buffer
            with self.unreliable_data_lock:
                if self.unreliable_buffer:
                    if self.seq_to_recv in self.unreliable_seqs:
                        self.unreliable_seqs.remove(self.seq_to_recv)
                        self.seq_to_recv = increment_seq(self.seq_to_recv)
                    seq, send_ts, arrival_ts, payload = self.unreliable_buffer.popleft()
                    self.last_recv_time = now
                    # Count metrics only on delivery
                    self.metrics.update_on_receive(
                        UNRELIABLE_CHANNEL, len(payload), send_ts, arrival_ts)
                    return seq, UNRELIABLE_CHANNEL, payload


    def close(self):
        self.running_threads = False
        self.sock.close()

    def _recv_and_ack(self):
        while self.running_threads:
            try:
                data, _ = self.sock.recvfrom(65536)
            except BlockingIOError:
                time.sleep(0.001)
                continue
            except ConnectionResetError:
                # Windows-specific: ICMP port unreachable
                time.sleep(0.001)
                continue
            try:
                ch, seq, ts, payload = unpack_packet(data)
            except Exception:
                continue

            arrival = now_ms()
            # print(f"seq={seq}, ch={ch} ARRIVED AT {arrival}, took {arrival-ts}ms to reach")
            
            # If critical packet, store in reliable buffer and send ACK
            if ch == RELIABLE_CHANNEL:
                with self.reliable_data_lock:
                    # Store payload and timing for delivery-time metrics
                    self.reliable_buffer[seq] = (payload, ts, arrival)
                ack = pack_packet(RELIABLE_CHANNEL, seq, arrival, b"ACK")
                # print(f"seq={seq}, ch={ch} SEND ACK AT {now_ms()}")
                self.sock.sendto(ack, self.dest_socket_addr)
            # Else simply push to unreliable buffer
            else:
                with self.unreliable_data_lock:
                    # Store seq, original send timestamp and arrival for delivery-time metrics
                    self.unreliable_buffer.append((seq, ts, arrival, payload))
                    self.unreliable_seqs.add(seq)
                # Do not count metrics yet; only when delivered to app in recv()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--direct", action="store_true",
                        help="Bypass emulator and receive ACKs directly to sender")
    parser.add_argument("--duration", type=float,
                        default=20.0, help="Run duration in seconds")
    parser.add_argument("--metrics-json", type=str, default="",
                        help="Optional path to write receiver metrics JSON summary")
    parser.add_argument("--pdr-from", type=str, default="",
                        help="Optional path to sender metrics JSON to compute PDR")
    args = parser.parse_args()

    # Main receiver logic
    print("[RECEIVER] listening...")
    dest = SENDER_ADDR if args.direct else EMULATOR_PROXY
    receiver = Receiver(RECEIVER_ADDR, dest)
    recv = []
    start_time = time.time()

    try:
        while time.time() - start_time < args.duration:
            msg = receiver.recv()
            if msg:
                seq, ch, data = msg
                print(
                    f"[RECEIVER] got seq={seq} ch={'REL' if ch==RELIABLE_CHANNEL else 'UNREL'} data={data}")
                recv.append((seq, ch))
    except KeyboardInterrupt:
        pass
    finally:
        receiver.metrics.stop(now_ms())
        recv_summary = receiver.metrics.summary()
        print(format_receiver_summary(recv_summary))

        # Optional JSON export
        if args.metrics_json:
            try:
                with open(args.metrics_json, "w") as f:
                    json.dump(recv_summary, f, indent=2)
                print(f"[RECEIVER] Wrote metrics JSON to {args.metrics_json}")
            except Exception as e:
                print(f"[RECEIVER] Failed to write metrics JSON: {e}")

        # Optional PDR computation if sender metrics available
        if args.pdr_from and os.path.exists(args.pdr_from):
            try:
                with open(args.pdr_from, "r") as f:
                    sender_summary = json.load(f)

                def pdr(recv_pkts, sent_pkts):
                    return (100.0 * recv_pkts / sent_pkts) if sent_pkts > 0 else 0.0
                rel_pdr = pdr(recv_summary.get("reliable", {}).get("packets", 0),
                              sender_summary.get("reliable", {}).get("sent_packets", 0))
                unrel_pdr = pdr(recv_summary.get("unreliable", {}).get("packets", 0),
                                sender_summary.get("unreliable", {}).get("sent_packets", 0))
                print("\n[PDR] Packet Delivery Ratio (%):")
                print(f"  reliable   : {rel_pdr:.2f}%")
                print(f"  unreliable : {unrel_pdr:.2f}%")
            except Exception as e:
                print(
                    f"[RECEIVER] Failed to compute PDR from {args.pdr_from}: {e}")
        receiver.close()
