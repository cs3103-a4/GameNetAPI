from collections import deque
import socket
import threading
import time
from utils import pack_packet, unpack_packet, now_ms

RETRANSMIT_MS = 100
SKIP_TIMEOUT_MS = 200
MAX_RETRANSMIT_ATTEMPTS = 20
RELIABLE_CHANNEL = 0
UNRELIABLE_CHANNEL = 1

"""
gameNetAPI is an interface for sender and receiver applications to send packets to each other
on top of a hybrid transport layer protocol, aka H-UDP, that offers both reliable and unreliable
packet delivery, such as for transmitting critical game state reliably and non-critical updates
unreliably but with lower latency.

@param src_socket_addr: (ip addr, port num) of src host
@param dest_socket_addr: (ip addr, port num) of dest host
@param is_sender: True if src is sender, False if src is receiver
"""
class GameNetAPI:
    def __init__(self, src_socket_addr, dest_socket_addr, is_sender):
        """
        1. Store basic info and setup socket to send/recv packets
        """
        self.is_sender = is_sender
        self.src_socket_addr = src_socket_addr
        self.dest_socket_addr = dest_socket_addr
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(src_socket_addr)
        self.sock.setblocking(False) # Set non-blocking socket so threads won't sleep

        """
        2. Setup resources needed for reliable recv
        - Seq num of received packets
        - Buffer to recv all incoming packets
        - Reliable buffer to store critical packets
        - Thead for receiver to buffer received packets and send ACKs if reliable 
          (combined with recv_or_send_ack_thread in step 3)
          --> Need mutex lock to protect unreliable buffer, unreliable seq, reliable buffer, 
              and last_missing_time since these resources are accessed concurrently in primary 
              thread and recv_or_send_ack_thread
        """
        self.seq_to_recv = 0
        self.unreliable_buffer = deque()  # Unreliable packets buffer: FIFO queue of (recv_seq, payload)
        self.unreliable_seqs = set()  # Set of seq nums in unreliable buffer so we can increment self.seq_to_recv
        self.reliable_buffer = {}  # Reliable packets buffer: {recv_seq -> (payload, timestamp)}
        self.last_missing_time = None

        self.unreliable_data_lock = threading.Lock() # Mutex lock for unreliable_buffer and unreliable_seqs
        self.reliable_data_lock = threading.Lock() # Mutex lock for reliable_buffer and last_missing_time

        """
        3. Setup resources needed for reliable send
        - Seq num of sent packets
        - Reliability mechanism: sender needs to listen for receiver ACKs, else retransmit if 
          timeout
          --> Need 2 more concurrent threads, 1 for sender to receive ACKs / receiver to send 
              ACKs, 1 for sender to retransmit if timeout
          --> Need to keep track of pending_acks for reliable packets sent, with mutex lock for
              protection against concurrent thread access
        """
        self.seq_to_send = 0
        self.pending_acks = {}  # sent_seq -> (sent_time, num retransmit attempts, payload)
        self.pending_acks_lock = threading.Lock()

        self.running_threads = True
        self.recv_or_send_ack_thread = threading.Thread(target=self._recv_or_send_ack, daemon=True)
        self.retransmit_thread = threading.Thread(target=self._retransmit, daemon=True)
        self.recv_or_send_ack_thread.start()
        self.retransmit_thread.start()

    def send(self, payload: bytes, is_reliable) -> int:
        if not self.is_sender:
            print("[gameNetAPI] Error: only sender can send packets")
            return -1
        
        ch = RELIABLE_CHANNEL if is_reliable else UNRELIABLE_CHANNEL
        seq = self.seq_to_send
        packet = pack_packet(ch, seq, now_ms(), payload)
        self.sock.sendto(packet, self.dest_socket_addr)
        if is_reliable:
            # Track packets which require ACK in reliable send
            with self.pending_acks_lock:
                self.pending_acks[seq] = {
                    "packet": packet,
                    "sent_time": now_ms(),
                    "attempts": 1
                }
        self.seq_to_send = self._increment_seq(seq)
        return seq

    def recv(self, block=False, timeout=None) -> int:
        """
        Returns (payload, channel_type, recv_seq) in-order for reliable packets.
        Unreliable packets returned immediately (unordered).
        If reliable_only=True, returns only reliable packets.
        """
        if self.is_sender:
            print("[gameNetAPI] Error: only receiver can recv packets")
            return -1

        start = time.time()
        while True:
            with self.reliable_data_lock:
                # 1. Check if next expected packet is in reliable buffer
                if self.seq_to_recv in self.reliable_buffer:
                    payload, ts = self.reliable_buffer.pop(self.seq_to_recv)
                    seq = self.seq_to_recv
                    self.seq_to_recv = self._increment_seq(seq)
                    self.last_missing_time = None
                    return seq, RELIABLE_CHANNEL, payload

                # 2. Skip reliable missing seq after timeout
                if self.last_missing_time and (now_ms() - self.last_missing_time) > SKIP_TIMEOUT_MS:
                    print(f"[gameNetAPI] skipping (reliable) missing seq={self.seq_to_recv}")
                    self.seq_to_recv = self._increment_seq(self.seq_to_recv) 
                    self.last_missing_time = now_ms()

            with self.unreliable_data_lock:
                # 3. Check for any unreliable packets
                if self.unreliable_buffer:
                    if self.seq_to_recv in self.unreliable_seqs:
                        self.unreliable_seqs.remove(self.seq_to_recv)
                        self.seq_to_recv = self._increment_seq(self.seq_to_recv)
                    return self.unreliable_buffer.popleft()

            # 4. Timeout or blocking behavior
            if not block:
                return None
            if timeout and time.time() - start > timeout:
                return None
            time.sleep(0.01)

    def close(self):
        self.running_threads = False
        self.sock.close()
    
    def _increment_seq(self, seq_to_send):
        # & 0xFFFF prevents 16-bit integer overflow (wraps back to 0)
        return (seq_to_send + 1) & 0xFFFF

    def _recv_or_send_ack(self):
        while self.running_threads:
            try:
                data, _ = self.sock.recvfrom(65536)
            except BlockingIOError:
                time.sleep(0.001)
                continue
            try:
                ch, seq, ts, payload = unpack_packet(data)
            except Exception: # Skip if data is corrupted
                continue
            
            # Sender recvs ACK from receiver if reliable channel
            if self.is_sender:
                if ch == UNRELIABLE_CHANNEL or not payload.startswith(b"ACK"): continue
                with self.pending_acks_lock:
                    self.pending_acks.pop(seq, None)
            # Receiver stores packet in buffer, then sends ACK to sender if reliable channel
            else:
                if ch == RELIABLE_CHANNEL:
                    with self.reliable_data_lock:
                        # Add packet to reliable buffer
                        self.reliable_buffer[seq] = (payload, now_ms())
                        # Mark time if missing gap
                        if seq > self.seq_to_recv and self.last_missing_time is None:
                            self.last_missing_time = now_ms()
                        
                    ack = pack_packet(RELIABLE_CHANNEL, seq, now_ms(), b"ACK")
                    self.sock.sendto(ack, self.dest_socket_addr)

                else:
                    # Add packet to unreliable buffer and visited set
                    with self.unreliable_data_lock:
                        self.unreliable_buffer.append((seq, UNRELIABLE_CHANNEL, payload))
                        self.unreliable_seqs.add(seq)
                
    def _retransmit(self):
        while self.running_threads:
            time.sleep(0.01)
            now = now_ms()
            to_retransmit = []
            with self.pending_acks_lock:
                for seq, info in list(self.pending_acks.items()):
                    if now - info["sent_time"] > RETRANSMIT_MS:
                        if info["attempts"] < MAX_RETRANSMIT_ATTEMPTS:
                            to_retransmit.append(seq)
                        else:
                            del self.pending_acks[seq]
            for seq in to_retransmit:
                with self.pending_acks_lock:
                    info = self.pending_acks.get(seq)
                    if not info:
                        continue
                    self.sock.sendto(info["packet"], self.dest_socket_addr)
                    info["sent_time"] = now_ms()
                    info["attempts"] += 1
                    print(f"[gameNetAPI] Retransmit seq={seq} attempt={info['attempts']}")
