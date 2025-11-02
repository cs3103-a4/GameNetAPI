### GameNetAPI

To test gameNetAPI:

1. First, run `python3 emulator.py`
2. Open a new terminal and run `python3 receiver.py`
3. Open a new terminal and run `python3 sender.py`

### Project structure

```
├─ emulator.py    # Intercepts packet transmission and introduces loss and delay
├─ receiver.py    # Manages reliable / unreliable buffers to receive packets
├─ sender.py      # Sends UDP packets with retransmission for reliable ones
└─ utils.py       # Helper functions for packing/unpacking packets, timestamps, etc.
```

- Refer to comments in each file for details on how they work
