import socket
import threading
import time
import random
from emulator import EMULATOR_PROXY, SENDER_ADDR
from utils import increment_seq, pack_packet, unpack_packet, now_ms, RELIABLE_CHANNEL, UNRELIABLE_CHANNEL

RETRANSMIT_TIMEOUT_MS = 200  # Timeout t beyond which reliable packet is dropped = 200ms
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
        self.pending_acks = {}  # sent_seq -> (sent_time, num retransmit attempts, payload)
        self.pending_acks_lock = threading.Lock()

        self.recv_ack_thread = threading.Thread(target=self._recv_ack, daemon=True)
        self.retransmit_thread = threading.Thread(target=self._retransmit, daemon=True)
        self.running_threads = True
        self.recv_ack_thread.start()
        self.retransmit_thread.start()

    def send(self, payload: str, is_reliable) -> int:
        ch = RELIABLE_CHANNEL if is_reliable else UNRELIABLE_CHANNEL
        seq = self.seq_to_send
        packet = pack_packet(ch, seq, now_ms(), payload.encode('utf-8'))
        self.sock.sendto(packet, self.dest_socket_addr)
        if is_reliable:
            with self.pending_acks_lock:
                self.pending_acks[seq] = {
                    "packet": packet,
                    "sent_time": now_ms(),
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
                self.pending_acks.pop(seq, None)

    def _retransmit(self):
        while self.running_threads:
            time.sleep(0.01)
            now = now_ms()
            to_retransmit = []
            with self.pending_acks_lock:
                for seq, info in list(self.pending_acks.items()):
                    if now - info["sent_time"] <= RETRANSMIT_INTERVAL_MS: # Not yet time to retransmit
                        continue
                    if info["attempts"] < MAX_RETRANSMIT_ATTEMPTS: # Retransmit if haven't exceeded max attempts
                        to_retransmit.append(seq)
                    else:
                        del self.pending_acks[seq]
            for seq in to_retransmit:
                with self.pending_acks_lock:
                    # Retransmit packet, then update sent time and attempts info
                    info = self.pending_acks.get(seq)
                    if not info: continue
                    self.sock.sendto(info["packet"], self.dest_socket_addr)
                    info["sent_time"] = now_ms()
                    info["attempts"] += 1
                    print(f"[SENDER] Retransmit seq={seq} attempt={info['attempts']}")

if __name__ == '__main__':
    # Main sender logic
    sender = Sender(SENDER_ADDR, EMULATOR_PROXY) # Change dst to RECEIVER_ADDR to skip emulator proxy
    start = time.time()

    try:
        while time.time() - start < 10:
            is_reliable = random.random() < 0.5
            msg = f"hello_{'R' if is_reliable else 'U'}"
            seq = sender.send(msg, is_reliable=is_reliable)
            print(f"[SENDER] Sent seq={seq} is_reliable={is_reliable}")
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        sender.close()
