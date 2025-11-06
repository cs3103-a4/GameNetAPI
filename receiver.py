import time
import argparse
import json
import os
from emulator import EMULATOR_PROXY, RECEIVER_ADDR, SENDER_ADDR
from gameNetAPI import GameNetAPI
from utils import now_ms, RELIABLE_CHANNEL
from metrics import format_receiver_summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--direct", action="store_true",
                        help="Bypass emulator and receive ACKs directly to sender")
    parser.add_argument("--duration", type=float,
                        default=20.0, help="Run duration in seconds")
    parser.add_argument("--metrics-json", type=str, default="",
                        help="Optional path to write receiver metrics JSON summary")
    parser.add_argument("--pdr-from", type=str, default="",
                        help="Optional path to sender metrics JSON to compute PDR")
    args = parser.parse_args()

    # Main receiver logic
    print("[RECEIVER] listening...")
    dest = SENDER_ADDR if args.direct else EMULATOR_PROXY
    receiver = GameNetAPI(is_sender=False, src_socket_addr=RECEIVER_ADDR, dest_socket_addr=dest)
    recv = []
    start = time.time()

    try:
        while time.time() - start < args.duration:
            msg = receiver.recv(hard_timeout_ms = 1000)
            if msg:
                seq, ch, data = msg
                print(
                    f"[RECEIVER] got seq={seq} ch={'REL' if ch==RELIABLE_CHANNEL else 'UNREL'} data={data}")
                recv.append((seq, ch))
    except KeyboardInterrupt:
        pass
    finally:
        receiver.metrics.stop(now_ms())
        recv_summary = receiver.metrics.summary()
        print(format_receiver_summary(recv_summary))

        # Optional JSON export
        if args.metrics_json:
            try:
                with open(args.metrics_json, "w") as f:
                    json.dump(recv_summary, f, indent=2)
                print(f"[RECEIVER] Wrote metrics JSON to {args.metrics_json}")
            except Exception as e:
                print(f"[RECEIVER] Failed to write metrics JSON: {e}")

        # Optional PDR computation if sender metrics available
        if args.pdr_from and os.path.exists(args.pdr_from):
            try:
                with open(args.pdr_from, "r") as f:
                    sender_summary = json.load(f)

                def pdr(recv_pkts, sent_pkts):
                    return (100.0 * recv_pkts / sent_pkts) if sent_pkts > 0 else 0.0
                rel_pdr = pdr(recv_summary.get("reliable", {}).get("packets", 0),
                              sender_summary.get("reliable", {}).get("sent_packets", 0))
                unrel_pdr = pdr(recv_summary.get("unreliable", {}).get("packets", 0),
                                sender_summary.get("unreliable", {}).get("sent_packets", 0))
                print("\n[PDR] Packet Delivery Ratio (%):")
                print(f"  reliable   : {rel_pdr:.2f}%")
                print(f"  unreliable : {unrel_pdr:.2f}%")
            except Exception as e:
                print(
                    f"[RECEIVER] Failed to compute PDR from {args.pdr_from}: {e}")
        receiver.close()
