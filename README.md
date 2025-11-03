# GameNetAPI

To test gameNetAPI:

1. First, run `python emulator.py` (optional if using `--direct`)
2. Open a new terminal and run `python receiver.py [--direct] [--duration 20]`
3. Open a new terminal and run `python sender.py [--direct] [--duration 10] [--rate 10]`

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

- Receiver side (one-way): latency p50/p95 (unreliable only), RFC3550 jitter, throughput, packets/bytes
- Sender side: sent packets/bytes and retransmissions; latency p50/p95 for reliable only
- Packet Delivery Ratio (PDR): combine sender sent counts with receiver received counts

At the end of a run, sender and receiver print a metrics summary per channel.

### Latency definitions

- Reliable (reported by sender): latency = (ACK_time − first_send_time) / 2
  - Captures half of (forward + reverse + any retransmit wait). Unreliable has no ACKs, so this is NA on sender for the unreliable channel.
- Unreliable (reported by receiver): latency = arrival_time − send_time
  - Captures forward path only at first arrival. Reliable is NA on receiver since we standardize reliable latency at the sender.

## Example experiment scenarios

Below are ready-to-run commands to produce summaries for different network conditions. Use three terminals: one for the emulator (A), one for the receiver (B), and one for the sender (C). Keep receiver duration slightly longer so it can read the sender's JSON and print PDR.

### Baseline (no emulator)

Receiver (Terminal B)

```bash
python receiver.py --direct --duration 8 --metrics-json metrics/receiver_direct.json --pdr-from metrics/sender_direct.json
```

Sender (Terminal C)

```bash
python sender.py --direct --duration 6 --rate 20 --metrics-json metrics/sender_direct.json
```

### Low loss (<2%), modest latency

Emulator (Terminal A)

```bash
python emulator.py --loss 0.01 --delay 20 --jitter 5 --quiet
```

Receiver (Terminal B)

```bash
python receiver.py --duration 12 --metrics-json metrics/receiver_low.json --pdr-from metrics/sender_low.json
```

Sender (Terminal C)

```bash
python sender.py --duration 10 --rate 20 --metrics-json metrics/sender_low.json
```

### Moderate jitter, no loss

Emulator (Terminal A)

```bash
python emulator.py --loss 0.00 --delay 20 --jitter 50 --quiet
```

Receiver (Terminal B)

```bash
python receiver.py --duration 12 --metrics-json metrics/receiver_jitter.json --pdr-from metrics/sender_jitter.json
```

Sender (Terminal C)

```bash
python sender.py --duration 10 --rate 20 --metrics-json metrics/sender_jitter.json
```

### High loss (>10%), noticeable impact

Emulator (Terminal A)

```bash
python emulator.py --loss 0.11 --delay 10 --quiet 
```

Receiver (Terminal B)
(Note: run terminal C immediately after running terminal B, or seqno will be autoincremented if it receives nothing)

```bash
python3 receiver.py --duration 15 --metrics-json metrics/receiver_high.json --pdr-from metrics/sender_high.json
```

Sender (Terminal C)

```bash
python sender.py --duration 10 --rate 10 --metrics-json metrics/sender_high.json
```

### Options

Emulator

- `--loss` in [0..1], `--delay` ms, `--jitter` ms; add `--quiet` to reduce logs.
