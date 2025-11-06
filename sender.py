import time
import argparse
import json
import random
from emulator import EMULATOR_PROXY, SENDER_ADDR, RECEIVER_ADDR
from gameNetAPI import GameNetAPI
from metrics import format_sender_summary


GAME_MESSAGES = {
    "reliable": [
        "PLAYER_JOIN:player1",
        "GAME_STATE:score_update:teamA-2,teamB-1",
        "PLAYER_LEVEL_UP:player2:level5"
    ],
    "unreliable": [
        "PLAYER_MOVE:player1:x=150,y=280",
        "PLAYER_ACTION:player2:jump",
        "OBJECT_UPDATE:ball:x=320,y=180"
    ]
}

if __name__ == '__main__':
    # Main sender logic with CLI
    parser = argparse.ArgumentParser()
    parser.add_argument("--direct", action="store_true",
                        help="Bypass emulator and send directly to receiver")
    parser.add_argument("--duration", type=float,
                        default=10.0, help="Run duration in seconds")
    parser.add_argument("--rate", type=float, default=10.0,
                        help="Packets per second (avg)")
    parser.add_argument("--metrics-json", type=str, default="",
                        help="Optional path to write sender metrics JSON summary")
    args = parser.parse_args()

    dest = RECEIVER_ADDR if args.direct else EMULATOR_PROXY
    sender = GameNetAPI(is_sender=True, src_socket_addr=SENDER_ADDR, dest_socket_addr=dest)
    start = time.time()

    # Alternate between reliable and unreliable for simplicity
    next_rel = True

    try:
        interval = 1.0 / max(0.1, args.rate)
        while time.time() - start < args.duration:
            is_reliable = next_rel
            next_rel = not next_rel

            # Choose a random game message based on channel type
            msg_type = "reliable" if is_reliable else "unreliable"
            msg = random.choice(GAME_MESSAGES[msg_type])

            seq = sender.send(msg, is_reliable=is_reliable)
            print(f"[SENDER] Sent seq={seq} is_reliable={is_reliable} msg={msg}")
            time.sleep(interval)
    except KeyboardInterrupt:
        pass
    finally:
        sender.close()
        print()
        sender_summary = sender.metrics.summary()
        print(format_sender_summary(sender_summary))
        if args.metrics_json:
            try:
                with open(args.metrics_json, "w") as f:
                    json.dump(sender_summary, f, indent=2)
                print(f"[SENDER] Wrote metrics JSON to {args.metrics_json}")
            except Exception as e:
                print(f"[SENDER] Failed to write metrics JSON: {e}")
