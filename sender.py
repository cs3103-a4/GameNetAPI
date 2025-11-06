import socket
import threading
import time
import argparse
import json
import random
from emulator import EMULATOR_PROXY, SENDER_ADDR, RECEIVER_ADDR
from utils import increment_seq, pack_packet, unpack_packet, now_ms, RELIABLE_CHANNEL, UNRELIABLE_CHANNEL
from metrics import SenderMetrics, format_sender_summary

# Timeout t beyond which reliable packet is dropped = 200ms
RETRANSMIT_TIMEOUT_MS = 200
RETRANSMIT_INTERVAL_MS = 40  # Time delta between each retransmission attempt
MAX_RETRANSMIT_ATTEMPTS = 5  # 5 attempts * 40ms = 200ms <= timeout t

GAME_MESSAGES = {
    "reliable": [
        "PLAYER_JOIN:player1",
        "GAME_STATE:score_update:teamA-2,teamB-1",
        "PLAYER_LEVEL_UP:player2:level5"
    ],
    "unreliable": [
        "PLAYER_MOVE:player1:x=150,y=280",
        "PLAYER_ACTION:player2:jump",
        "OBJECT_UPDATE:ball:x=320,y=180"
    ]
}

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
        # print(f"seq={seq}, rel={is_reliable} SENT AT {send_time}ms")
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
            """
            NOTE: The initial approach below to record the e2e latency from when a packet was first
            sent, to when it finally receives the ACK is valid below. However, due to OS optimisations,
            if socket at localhost port X receives a packet sent from localhost port Y, then sends ACK 
            right after back to port Y, this ACK will always take between 0 and 1 ms (instead of the 
            usual 5-10ms) to reach the dst. This 'localhost short-circuit' optimisation renders the
            2nd leg (ACK packet)'s latency invalid to be included in our performance metrics, because
            it will underestimate the latency of the reliable channel by almost 50%.

            Therefore, the block of code below is commented out, as we will derive latency metrics all
            on the receiver's side instead, where e2e latency is from when a packet was first sent, to
            when it finally gets pushed to the receiver application. In other words, e2e latency of a
            packet = one-way network latency (from sender to receiver) + buffer latency (from receiver to
            application)
            """
            # if info is not None:
            #     nowt = now_ms()
            #     # Compute reliable one-way latency from first send to ACK arrival, divided by 2
            #     rtt_from_first = nowt - \
            #         info.get("first_sent_time", info["sent_time"])
            #     print(f"seq={seq}, ch={ch} RECEIVED ACK AT {nowt}. First sent time is {info.get("first_sent_time", info["sent_time"])}.")
            #     reliable_latency = rtt_from_first / 2.0
            #     self.metrics.update_on_reliable_latency(reliable_latency)

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

            # Choose a random game message based on channel type
            msg_type = "reliable" if is_reliable else "unreliable"
            msg = random.choice(GAME_MESSAGES[msg_type])

            seq = sender.send(msg, is_reliable=is_reliable)
            print(f"[SENDER] Sent seq={seq} is_reliable={is_reliable} msg={msg}")
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
