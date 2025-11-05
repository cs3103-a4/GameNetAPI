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


def _min(values):
    return float(min(values)) if values else 0.0


def _max(values):
    return float(max(values)) if values else 0.0


def _avg(values):
    return float(sum(values) / len(values)) if values else 0.0


class ReceiverMetrics:
    def __init__(self):
        self.start_time_ms = self.end_time_ms = None
        self._stats = {ch: {"packets": 0, "bytes": 0, "latencies": [], "jitter": 0.0, "_last": None}
                       for ch in (RELIABLE, UNRELIABLE)}

    def start(self, now_ms): self.start_time_ms = now_ms
    def stop(self, now_ms): self.end_time_ms = now_ms


    def update_on_receive(self, channel, payload_len, send_ts_ms, arrival_ms):
        st = self._stats[channel]
        st["packets"] += 1
        st["bytes"] += payload_len
        # Only record latency/jitter for UNRELIABLE on receiver side (reliable will be NA)
        if channel == UNRELIABLE:
            t = arrival_ms - send_ts_ms
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
            name = "reliable" if ch == RELIABLE else "unreliable"
            if ch == RELIABLE:
                out[name] = {
                    "packets": st["packets"], "bytes": st["bytes"],
                    "latency_min_ms": None, "latency_avg_ms": None,
                    "latency_p95_ms": None, "latency_p99_ms": None, "latency_max_ms": None,
                    "jitter_ms": None,
                    "throughput_Bps": (st["bytes"]/dur if dur > 0 else 0.0)
                }
            else:
                out[name] = {
                    "packets": st["packets"], "bytes": st["bytes"],
                    "latency_min_ms": _min(l), "latency_avg_ms": _avg(l),
                    "latency_p95_ms": _pct(l, 95), "latency_p99_ms": _pct(l, 99), "latency_max_ms": _max(l),
                    "jitter_ms": float(st["jitter"]),
                    "throughput_Bps": (st["bytes"]/dur if dur > 0 else 0.0)
                }
        return out


class SenderMetrics:
    def __init__(self):
        self._stats = {ch: {"sent_packets": 0, "sent_bytes": 0, "retransmissions": 0, "reliable_latencies": [], "jitter": 0.0, "_last": None}
                       for ch in (RELIABLE, UNRELIABLE)}

    def update_on_send(self, channel, total_len):
        st = self._stats[channel]
        st["sent_packets"] += 1
        st["sent_bytes"] += total_len

    def update_on_retransmit(
        self, channel): self._stats[channel]["retransmissions"] += 1

    def update_on_ack(
            self, rtt_ms):
        # RTT collection removed from metrics (no-op)
        return

    def update_on_reliable_latency(self, latency_ms: float):
        # Record reliable one-way latency estimate (computed at sender as (ACK_time - first_send)/2)
        st = self._stats[RELIABLE]
        latency = float(latency_ms)
        st["reliable_latencies"].append(latency)
        # Calculate jitter for reliable channel
        if st["_last"] is not None:
            d = abs(latency - st["_last"])
            st["jitter"] += (d - st["jitter"]) / 16.0
        st["_last"] = latency

    # Dropped packet counting removed from metrics (no-op kept for compatibility)
    def update_on_drop(self):
        return

    def summary(self):
        out = {}
        for ch, st in self._stats.items():
            name = "reliable" if ch == RELIABLE else "unreliable"
            o = st.get("reliable_latencies", [])
            out[name] = {
                "sent_packets": st["sent_packets"],
                "sent_bytes": st["sent_bytes"],
                "retransmissions": st["retransmissions"],
                # Reliable one-way latency (sender-estimated) as min/avg/p95/p99/max; NA for unreliable
                "latency_min_ms": _min(o) if ch == RELIABLE else None,
                "latency_avg_ms": _avg(o) if ch == RELIABLE else None,
                "latency_p95_ms": _pct(o, 95) if ch == RELIABLE else None,
                "latency_p99_ms": _pct(o, 99) if ch == RELIABLE else None,
                "latency_max_ms": _max(o) if ch == RELIABLE else None,
                # Jitter for reliable channel (sender side); NA for unreliable
                "jitter_ms": float(st["jitter"]) if ch == RELIABLE else None,
            }
        return out


def format_receiver_summary(summary: dict) -> str:
    hdr = (
        "[RECEIVER] Metrics summary:\n"
        "  channel       packets(cnt)  bytes(B)  min(ms)  avg(ms)  p95(ms)  p99(ms)  max(ms)  jitter(ms)  thr(B/s)"
    )

    def fmt_float(v, width, prec):
        if v is None:
            return f"{'NA':>{width}}"
        return f"{float(v):>{width}.{prec}f}"

    def row(name, s):
        return (f"  {name:<11}{int(s.get('packets',0)):>14}{int(s.get('bytes',0)):>10}"
                f"{fmt_float(s.get('latency_min_ms'),9,2)}{fmt_float(s.get('latency_avg_ms'),9,2)}"
                f"{fmt_float(s.get('latency_p95_ms'),9,2)}{fmt_float(s.get('latency_p99_ms'),9,2)}"
                f"{fmt_float(s.get('latency_max_ms'),9,2)}"
                f"{fmt_float(s.get('jitter_ms'),11,3)}{float(s.get('throughput_Bps',0.0)):>11.1f}")
    return "\n".join([hdr, row("reliable", summary.get("reliable", {})), row("unreliable", summary.get("unreliable", {}))])


def format_sender_summary(summary: dict) -> str:
    hdr = (
        "[SENDER] Metrics summary:\n"
        "  channel      sent_pkts(cnt)  sent_bytes(B)  retrans(cnt)  min(ms)  avg(ms)  p95(ms)  p99(ms)  max(ms)  jitter(ms)"
    )

    def fmt_float(v, width, prec):
        if v is None:
            return f"{'NA':>{width}}"
        return f"{float(v):>{width}.{prec}f}"

    def row(name, s):
        return (f"  {name:<11}{int(s.get('sent_packets',0)):>16}{int(s.get('sent_bytes',0)):>15}"
                f"{int(s.get('retransmissions',0)):>13}{fmt_float(s.get('latency_min_ms'),9,2)}"
                f"{fmt_float(s.get('latency_avg_ms'),9,2)}{fmt_float(s.get('latency_p95_ms'),9,2)}"
                f"{fmt_float(s.get('latency_p99_ms'),9,2)}{fmt_float(s.get('latency_max_ms'),9,2)}"
                f"{fmt_float(s.get('jitter_ms'),11,3)}")
    return "\n".join([hdr, row("reliable", summary.get("reliable", {})), row("unreliable", summary.get("unreliable", {}))])
