import socket
import threading
import time
from collections import deque
from emulator import EMULATOR_PROXY, RECEIVER_ADDR
from utils import increment_seq, pack_packet, unpack_packet, now_ms, RELIABLE_CHANNEL, UNRELIABLE_CHANNEL

RETRANSMIT_TIMEOUT_MS = 200

class Receiver:
    def __init__(self, src_socket_addr, dest_socket_addr):
        self.src_socket_addr = src_socket_addr
        self.dest_socket_addr = dest_socket_addr
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(src_socket_addr)
        self.sock.setblocking(False)

        self.seq_to_recv = 0
        self.unreliable_buffer = deque()  # Unreliable packets buffer: FIFO queue of (recv_seq, payload)
        self.unreliable_seqs = set()  # To increment self.seq_to_recv if alr recv seq num
        self.reliable_buffer = {}  # Reliable packets buffer: {recv_seq -> (payload, timestamp)}
        self.last_missing_time = None

        self.unreliable_data_lock = threading.Lock()
        self.reliable_data_lock = threading.Lock()

        self.running_threads = True
        self.recv_thread = threading.Thread(target=self._recv_and_ack, daemon=True)
        self.recv_thread.start()

    def recv(self, block=False, timeout=None):
        start = time.time()
        while True:
            # Receive from reliable buffer first
            with self.reliable_data_lock:
                if self.seq_to_recv in self.reliable_buffer:
                    payload, ts = self.reliable_buffer.pop(self.seq_to_recv)
                    seq = self.seq_to_recv
                    self.seq_to_recv = increment_seq(seq)
                    self.last_missing_time = None
                    return seq, RELIABLE_CHANNEL, payload

                if (self.last_missing_time and 
                    (now_ms() - self.last_missing_time) > RETRANSMIT_TIMEOUT_MS):
                    print(f"[RECEIVER] skipping missing seq={self.seq_to_recv}")
                    self.seq_to_recv = increment_seq(self.seq_to_recv)
                    self.last_missing_time = now_ms()
            # Then receive from unreliable buffer
            with self.unreliable_data_lock:
                if self.unreliable_buffer:
                    if self.seq_to_recv in self.unreliable_seqs:
                        self.unreliable_seqs.remove(self.seq_to_recv)
                        self.seq_to_recv = increment_seq(self.seq_to_recv)
                    seq, payload = self.unreliable_buffer.popleft()
                    return seq, UNRELIABLE_CHANNEL, payload

            if not block:
                return None
            if timeout and time.time() - start > timeout:
                return None
            time.sleep(0.01)

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
            try:
                ch, seq, ts, payload = unpack_packet(data)
            except Exception:
                continue
            
            # If critical packet, store in reliable buffer and send ACK
            if ch == RELIABLE_CHANNEL:
                with self.reliable_data_lock:
                    self.reliable_buffer[seq] = (payload, now_ms())
                    if seq > self.seq_to_recv and self.last_missing_time is None:
                        self.last_missing_time = now_ms()
                
                ack = pack_packet(RELIABLE_CHANNEL, seq, now_ms(), b"ACK")
                self.sock.sendto(ack, self.dest_socket_addr)
            # Else simply push to unreliable buffer
            else:
                with self.unreliable_data_lock:
                    self.unreliable_buffer.append((seq, payload))
                    self.unreliable_seqs.add(seq)

# Main receiver logic
print("[RECEIVER] listening...")
receiver = Receiver(RECEIVER_ADDR, EMULATOR_PROXY) # Change dst to SENDER_ADDR to skip emulator proxy
recv = []
start_time = time.time()

try:
    while time.time() - start_time < 15:
        msg = receiver.recv(block=True, timeout=1)
        if msg:
            seq, ch, data = msg
            print(f"[RECEIVER] got seq={seq} ch={'REL' if ch==RELIABLE_CHANNEL else 'UNREL'} data={data}")
            recv.append((seq, ch))
except KeyboardInterrupt:
    pass
finally:
    # Reliable packets are denoted by their seqno, unreliable packets are denoted by a string
    # of comma-separated seqnos in between reliable packet seqnos based on the recv order
    result = []
    unrel_buffer = []

    for seq, ch in recv:
        if ch == UNRELIABLE_CHANNEL:
            unrel_buffer.append(str(seq))
        else:
            if unrel_buffer:
                result.append(",".join(unrel_buffer))
                unrel_buffer = []
            result.append(seq)

    # Flush trailing unreliables (if any)
    if unrel_buffer:
        result.append(",".join(unrel_buffer))

    print(f"[RECEIVER] RESULT: {result}")
    receiver.close()
