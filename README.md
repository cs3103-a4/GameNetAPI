### GameNetAPI

To test gameNetAPI:

1. First, run `python3 emulator.py`
2. Open a new terminal and run `python3 receiver.py`
3. Open a new terminal and run `python3 sender.py`

### Project structure

```
├─ emulator.py    # Intercepts packet transmission and introduces loss and delay
├─ gameNetAPI.py  # Core H-UDP implementation (reliable + unreliable transport)
├─ receiver.py    # Receives packets via GameNetAPI
├─ sender.py      # Sends packets via GameNetAPI
└─ utils.py       # Helper functions for packing/unpacking packets, timestamps, etc.
```

- Refer to comments in each file for details on how they work
