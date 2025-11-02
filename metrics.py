RELIABLE, UNRELIABLE = 0, 1


def _pct(values, q):
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    if q == 50:
        m = n//2
        return float(s[m] if n % 2 else (s[m-1]+s[m])/2)
    idx = max(0, int((q/100.0) * (n-1)))
    return float(s[idx])


class ReceiverMetrics:
    def __init__(self):
        self.start_time_ms = self.end_time_ms = None
        self._stats = {ch: {"packets": 0, "bytes": 0, "latencies": [], "jitter": 0.0, "_last": None}
                       for ch in (RELIABLE, UNRELIABLE)}

    def start(self, now_ms): self.start_time_ms = now_ms
    def stop(self, now_ms): self.end_time_ms = now_ms

    @staticmethod
    def _wrap_diff_ms(arrival_ms, send_ts_u32):
        return float(((arrival_ms & 0xFFFFFFFF) - (send_ts_u32 & 0xFFFFFFFF)) & 0xFFFFFFFF)

    def update_on_receive(self, channel, payload_len, send_ts_ms, arrival_ms):
        st = self._stats[channel]
        st["packets"] += 1
        st["bytes"] += payload_len
        t = self._wrap_diff_ms(arrival_ms, send_ts_ms)
        st["latencies"].append(t)
        if st["_last"] is not None:
            d = abs(t - st["_last"])
            st["jitter"] += (d - st["jitter"]) / 16.0
        st["_last"] = t

    def summary(self):
        dur = (max(0, (self.end_time_ms - self.start_time_ms)) / 1000.0) if (
            self.start_time_ms is not None and self.end_time_ms is not None) else 0.0
        out = {}
        for ch, st in self._stats.items():
            l = st["latencies"]
            mean = float(sum(l)/len(l)) if l else 0.0
            out["reliable" if ch == RELIABLE else "unreliable"] = {
                "packets": st["packets"], "bytes": st["bytes"],
                "latency_mean_ms": mean, "latency_p50_ms": _pct(l, 50), "latency_p95_ms": _pct(l, 95),
                "jitter_ms": float(st["jitter"]), "throughput_Bps": (st["bytes"]/dur if dur > 0 else 0.0)
            }
        return out


class SenderMetrics:
    def __init__(self):
        self._stats = {ch: {"sent_packets": 0, "sent_bytes": 0, "retransmissions": 0, "dropped_reliable": 0, "rtts": []}
                       for ch in (RELIABLE, UNRELIABLE)}

    def update_on_send(self, channel, total_len):
        st = self._stats[channel]
        st["sent_packets"] += 1
        st["sent_bytes"] += total_len

    def update_on_retransmit(
        self, channel): self._stats[channel]["retransmissions"] += 1
    def update_on_ack(
        self, rtt_ms): self._stats[RELIABLE]["rtts"].append(float(rtt_ms))

    def update_on_drop(self): self._stats[RELIABLE]["dropped_reliable"] += 1

    def summary(self):
        out = {}
        for ch, st in self._stats.items():
            r = st["rtts"]
            mean = float(sum(r)/len(r)) if r else 0.0
            out["reliable" if ch == RELIABLE else "unreliable"] = {
                "sent_packets": st["sent_packets"], "sent_bytes": st["sent_bytes"],
                "retransmissions": st["retransmissions"], "dropped_reliable": st["dropped_reliable"],
                "rtt_mean_ms": mean, "rtt_p50_ms": _pct(r, 50), "rtt_p95_ms": _pct(r, 95)
            }
        return out


def format_receiver_summary(summary: dict) -> str:
    hdr = (
        "[RECEIVER] Metrics summary:\n"
        "  channel       packets(cnt)  bytes(B)  lat_mean(ms)  p50(ms)  p95(ms)  jitter(ms)  thr(B/s)"
    )

    def row(name, s):
        return (f"  {name:<11}{int(s.get('packets',0)):>14}{int(s.get('bytes',0)):>10}"
                f"{float(s.get('latency_mean_ms',0.0)):>14.2f}{float(s.get('latency_p50_ms',0.0)):>9.2f}"
                f"{float(s.get('latency_p95_ms',0.0)):>9.2f}{float(s.get('jitter_ms',0.0)):>11.3f}"
                f"{float(s.get('throughput_Bps',0.0)):>11.1f}")
    return "\n".join([hdr, row("reliable", summary.get("reliable", {})), row("unreliable", summary.get("unreliable", {}))])


def format_sender_summary(summary: dict) -> str:
    hdr = (
        "[SENDER] Metrics summary:\n"
        "  channel      sent_pkts(cnt)  sent_bytes(B)  retrans(cnt)  drops(cnt)  rtt_mean(ms)  p50(ms)  p95(ms)"
    )

    def row(name, s):
        return (f"  {name:<11}{int(s.get('sent_packets',0)):>16}{int(s.get('sent_bytes',0)):>15}"
                f"{int(s.get('retransmissions',0)):>13}{int(s.get('dropped_reliable',0)):>12}"
                f"{float(s.get('rtt_mean_ms',0.0)):>13.2f}{float(s.get('rtt_p50_ms',0.0)):>9.2f}"
                f"{float(s.get('rtt_p95_ms',0.0)):>9.2f}")
    return "\n".join([hdr, row("reliable", summary.get("reliable", {})), row("unreliable", summary.get("unreliable", {}))])
