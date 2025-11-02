import socket
import threading
import time
import argparse
import json
from emulator import EMULATOR_PROXY, SENDER_ADDR, RECEIVER_ADDR
from utils import increment_seq, pack_packet, unpack_packet, now_ms, RELIABLE_CHANNEL, UNRELIABLE_CHANNEL
from metrics import SenderMetrics, format_sender_summary

# Timeout t beyond which reliable packet is dropped = 200ms
RETRANSMIT_TIMEOUT_MS = 200
RETRANSMIT_INTERVAL_MS = 20  # Time delta between each retransmission attempt
MAX_RETRANSMIT_ATTEMPTS = 10  # 10 attempts * 20ms = 200ms <= timeout t


class Sender:
    def __init__(self, src_socket_addr, dest_socket_addr):
        self.src_socket_addr = src_socket_addr
        self.dest_socket_addr = dest_socket_addr
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(src_socket_addr)
        self.sock.setblocking(False)

        self.seq_to_send = 0
        # sent_seq -> (sent_time, num retransmit attempts, payload)
        self.pending_acks = {}
        self.pending_acks_lock = threading.Lock()

        self.metrics = SenderMetrics()

        self.recv_ack_thread = threading.Thread(
            target=self._recv_ack, daemon=True)
        self.retransmit_thread = threading.Thread(
            target=self._retransmit, daemon=True)
        self.running_threads = True
        self.recv_ack_thread.start()
        self.retransmit_thread.start()

    def send(self, payload: str, is_reliable) -> int:
        ch = RELIABLE_CHANNEL if is_reliable else UNRELIABLE_CHANNEL
        seq = self.seq_to_send
        send_time = now_ms()
        packet = pack_packet(ch, seq, send_time, payload.encode('utf-8'))
        self.sock.sendto(packet, self.dest_socket_addr)
        self.metrics.update_on_send(ch, len(packet))
        if is_reliable:
            with self.pending_acks_lock:
                self.pending_acks[seq] = {
                    "packet": packet,
                    "sent_time": send_time,
                    "first_sent_time": send_time,
                    "attempts": 1
                }
        self.seq_to_send = increment_seq(seq)
        return seq

    def close(self):
        self.running_threads = False
        self.sock.close()

    def _recv_ack(self):
        while self.running_threads:
            try:
                data, _ = self.sock.recvfrom(65536)
            except BlockingIOError:
                time.sleep(0.001)
                continue
            try:
                ch, seq, ts, payload = unpack_packet(data)
            except Exception:
                continue

            if ch == UNRELIABLE_CHANNEL or not payload.startswith(b"ACK"):
                continue
            with self.pending_acks_lock:
                info = self.pending_acks.pop(seq, None)
            if info is not None:
                nowt = now_ms()
                # Compute reliable one-way latency from first send to ACK arrival, divided by 2
                rtt_from_first = nowt - \
                    info.get("first_sent_time", info["sent_time"])
                reliable_latency = rtt_from_first / 2.0
                self.metrics.update_on_reliable_latency(reliable_latency)

    def _retransmit(self):
        while self.running_threads:
            time.sleep(0.01)
            now = now_ms()
            to_retransmit = []
            with self.pending_acks_lock:
                for seq, info in list(self.pending_acks.items()):
                    # Not yet time to retransmit
                    if now - info["sent_time"] <= RETRANSMIT_INTERVAL_MS:
                        continue
                    # Retransmit if haven't exceeded max attempts
                    if info["attempts"] < MAX_RETRANSMIT_ATTEMPTS:
                        to_retransmit.append(seq)
                    else:
                        del self.pending_acks[seq]
                        # Drop reliable packet after timeout window (no metrics collected)
            for seq in to_retransmit:
                with self.pending_acks_lock:
                    # Retransmit packet, then update sent time and attempts info
                    info = self.pending_acks.get(seq)
                    if not info:
                        continue
                    self.sock.sendto(info["packet"], self.dest_socket_addr)
                    info["sent_time"] = now_ms()
                    info["attempts"] += 1
                    self.metrics.update_on_retransmit(RELIABLE_CHANNEL)
                    print(
                        f"[SENDER] Retransmit seq={seq} attempt={info['attempts']}")


if __name__ == '__main__':
    # Main sender logic with CLI
    parser = argparse.ArgumentParser()
    parser.add_argument("--direct", action="store_true",
                        help="Bypass emulator and send directly to receiver")
    parser.add_argument("--duration", type=float,
                        default=10.0, help="Run duration in seconds")
    parser.add_argument("--rate", type=float, default=10.0,
                        help="Packets per second (avg)")
    parser.add_argument("--metrics-json", type=str, default="",
                        help="Optional path to write sender metrics JSON summary")
    args = parser.parse_args()

    dest = RECEIVER_ADDR if args.direct else EMULATOR_PROXY
    sender = Sender(SENDER_ADDR, dest)
    start = time.time()

    # Alternate between reliable and unreliable for simplicity
    next_rel = True

    try:
        interval = 1.0 / max(0.1, args.rate)
        while time.time() - start < args.duration:
            is_reliable = next_rel
            next_rel = not next_rel
            msg = f"hello_{'R' if is_reliable else 'U'}"
            seq = sender.send(msg, is_reliable=is_reliable)
            print(f"[SENDER] Sent seq={seq} is_reliable={is_reliable}")
            time.sleep(interval)
    except KeyboardInterrupt:
        pass
    finally:
        sender.close()
        print()
        sender_summary = sender.metrics.summary()
        print(format_sender_summary(sender_summary))
        if args.metrics_json:
            try:
                with open(args.metrics_json, "w") as f:
                    json.dump(sender_summary, f, indent=2)
                print(f"[SENDER] Wrote metrics JSON to {args.metrics_json}")
            except Exception as e:
                print(f"[SENDER] Failed to write metrics JSON: {e}")
