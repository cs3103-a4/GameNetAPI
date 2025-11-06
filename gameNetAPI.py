from collections import deque
import socket
import threading
import time

from metrics import ReceiverMetrics, SenderMetrics
from utils import RELIABLE_CHANNEL, UNRELIABLE_CHANNEL, increment_seq, now_ms, pack_packet, unpack_packet

# Timeout t beyond which reliable packet is dropped = 200ms
RETRANSMIT_TIMEOUT_MS = 200
RETRANSMIT_INTERVAL_MS = 40  # Time delta between each retransmission attempt
MAX_RETRANSMIT_ATTEMPTS = 5  # 5 attempts * 40ms = 200ms <= timeout t


class GameNetAPI:
    def __init__(self, is_sender, src_socket_addr, dest_socket_addr):
        if is_sender:
            self.sock = GameNetAPI.Sender(src_socket_addr, dest_socket_addr)
        else:
            self.sock = GameNetAPI.Receiver(src_socket_addr, dest_socket_addr)
    
    def __getattr__(self, name):
        # Delegate attribute access to self.sock
        return getattr(self.sock, name)

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

        def recv(self, hard_timeout_ms):
            start = now_ms()
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
                # Return if no new arrivals (hard timeout)
                if now - start >= hard_timeout_ms:
                    return None

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
