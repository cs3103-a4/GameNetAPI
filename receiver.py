from gameNetAPI import UNRELIABLE_CHANNEL, GameNetAPI
import time

api = GameNetAPI(('127.0.0.1', 12001), ('127.0.0.1', 11000), False)
print("[RECEIVER] listening...")
recv = []
start_time = time.time()

try:
    while time.time() - start_time < 15:
        msg = api.recv(block=True, timeout=1)
        if msg:
            seq, ch, data = msg
            print(f"[RECEIVER] got seq={seq} ch={'REL' if ch==UNRELIABLE_CHANNEL else 'UNREL'} data={data}")
            recv.append((seq, ch))
except KeyboardInterrupt:
    pass
finally:
    result = []
    unrel_buffer = []

    for seq, ch in recv:
        if ch == 1:
            unrel_buffer.append(str(seq))
        else:
            # Flush previous unreliables (if any)
            if unrel_buffer:
                result.append(",".join(unrel_buffer))
                unrel_buffer = []
            # Add the reliable seqno
            result.append(seq)

    # Flush trailing unreliables (if any)
    if unrel_buffer:
        result.append(",".join(unrel_buffer))

    print(f"[RECEIVER] RESULT: {result}")
    api.close()
