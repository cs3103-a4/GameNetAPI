from gameNetAPI import GameNetAPI
import time, random

api = GameNetAPI(('127.0.0.1', 12000), ('127.0.0.1', 11000), True)
start = time.time()

try:
    while time.time() - start < 10:
        is_reliable = random.random() < 0.5
        # is_reliable = False
        msg = f"hello_{'R' if is_reliable else 'U'}".encode()
        seq = api.send(msg, is_reliable=is_reliable)
        print(f"[SENDER] Sent seq={seq} is_reliable={is_reliable}")
        time.sleep(0.1)
except KeyboardInterrupt:
    pass
finally:
    api.close()
