# GameNetAPI

To test gameNetAPI:

1. First, run `python3 emulator.py` (optional if using `--direct`)
2. Open a new terminal and run `python3 receiver.py [--direct] [--duration 20]`
3. Open a new terminal and run `python3 sender.py [--direct] [--duration 10] [--rate 10]`

## Project structure

```text
├─ emulator.py    # Intercepts packet transmission and introduces loss and delay
├─ receiver.py    # Manages reliable / unreliable buffers to receive packets
├─ sender.py      # Sends UDP packets with retransmission for reliable ones
└─ utils.py       # Helper functions for packing/unpacking packets, timestamps, etc.
```

- Refer to comments in each file for details on how they work

## Metrics

This project collects per-channel metrics:

- Receiver side (one-way): latency p50/p95, RFC3550 jitter, throughput, packets/bytes
- Sender side: sent packets/bytes and retransmissions
- Packet Delivery Ratio (PDR): combine sender sent counts with receiver received counts

At the end of a run, sender and receiver print a metrics summary per channel.

## Example experiment scenarios

Below are ready-to-run commands to produce summaries for different network conditions. Use three terminals: one for the emulator (A), one for the receiver (B), and one for the sender (C). Keep receiver duration slightly longer so it can read the sender's JSON and print PDR.

### Baseline (no emulator)

Receiver (Terminal B)

```bash
python3 receiver.py --direct --duration 8 --metrics-json receiver_direct.json --pdr-from sender_direct.json
```

Sender (Terminal C)

```bash
python3 sender.py --direct --duration 6 --rate 20 --metrics-json sender_direct.json
```

### Low loss (<2%), modest latency

Emulator (Terminal A)

```bash
python3 emulator.py --loss 0.01 --delay 20 --jitter 5 --quiet
```

Receiver (Terminal B)

```bash
python3 receiver.py --duration 12 --metrics-json receiver_low.json --pdr-from sender_low.json
```

Sender (Terminal C)

```bash
python3 sender.py --duration 10 --rate 20 --metrics-json sender_low.json
```

### Moderate jitter, no loss

Emulator (Terminal A)

```bash
python3 emulator.py --loss 0.00 --delay 20 --jitter 50 --quiet
```

Receiver (Terminal B)

```bash
python3 receiver.py --duration 12 --metrics-json receiver_jitter.json --pdr-from sender_jitter.json
```

Sender (Terminal C)

```bash
python3 sender.py --duration 10 --rate 20 --metrics-json sender_jitter.json
```

### High loss (>10%), noticeable impact

Emulator (Terminal A)

```bash
python3 emulator.py --loss 0.15 --delay 30 --jitter 20 --quiet
```

Receiver (Terminal B)

```bash
python3 receiver.py --duration 12 --metrics-json receiver_high.json --pdr-from sender_high.json
```

Sender (Terminal C)

```bash
python3 sender.py --duration 10 --rate 20 --metrics-json sender_high.json
```

### Options

Emulator

- `--loss` in [0..1], `--delay` ms, `--jitter` ms; add `--quiet` to reduce logs.
