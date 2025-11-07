#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate comparison charts from collected metrics.
Works with both automated (emulator) and manual (Clumsy) experiment runs.

Usage:
    python3 generate_charts.py

Expects metrics files in metrics/ directory (as per the new format):
    - sender_direct.json, receiver_direct.json
    - sender_low.json, receiver_low.json
    - sender_high.json, receiver_high.json
    - sender_jitter.json, receiver_jitter.json
"""

import json
import os
import sys
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import numpy as np

# Fix encoding for Windows console
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except (AttributeError, TypeError):
        # Handle cases where reconfigure is not available (e.g. in some IDEs)
        pass

# Scenarios to plot (Situations)
# User requested these remain unchanged
SITUATIONS = ["direct", "low", "high", "jitter"]
SITUATION_LABELS = {
    "direct": "Direct",
    "low": "Low Loss",
    "high": "High Loss",
    "jitter": "High Jitter"
}

# Channel names
CHANNELS = ["reliable", "unreliable"]


def load_metrics():
    """Load all metrics files into a nested dictionary."""
    metrics = {}
    
    for situation in SITUATIONS:
        sender_path = f"metrics/sender_{situation}.json"
        receiver_path = f"metrics/receiver_{situation}.json"
        
        if not os.path.exists(sender_path) or not os.path.exists(receiver_path):
            print(f"[!] Warning: Missing metrics for {situation}")
            continue
        
        try:
            with open(sender_path, 'r', encoding='utf-8') as f:
                sender_data = json.load(f)
            with open(receiver_path, 'r', encoding='utf-8') as f:
                receiver_data = json.load(f)
            
            metrics[situation] = {
                "sender": sender_data,
                "receiver": receiver_data
            }
        except json.JSONDecodeError as e:
            print(f"[X] Error: Failed to parse JSON for {situation}. File may be corrupt.")
            print(f"  {e}")
        except IOError as e:
            print(f"[X] Error: Could not read metrics file for {situation}.")
            print(f"  {e}")
    
    return metrics


def compute_pdr(metrics, situation, channel):
    """Compute Packet Delivery Ratio for a situation and channel."""
    try:
        sent = metrics[situation]["sender"][channel]["sent_packets"]
        received = metrics[situation]["receiver"][channel]["packets"]
        return (received / sent * 100.0) if sent > 0 else 0.0
    except (KeyError, ZeroDivisionError, TypeError):
        return 0.0


def plot_latency_avg_p95_comparison(metrics):
    """Generate latency comparison chart (Avg and p95)."""
    fig, ax = plt.subplots(figsize=(12, 7))
    
    x = np.arange(len(SITUATIONS))
    width = 0.2
    
    # Collect data
    reliable_avg = []
    reliable_p95 = []
    unreliable_avg = []
    unreliable_p95 = []
    
    for situation in SITUATIONS:
        if situation not in metrics:
            reliable_avg.append(0)
            reliable_p95.append(0)
            unreliable_avg.append(0)
            unreliable_p95.append(0)
            continue
        
        # NEW FORMAT: All latency metrics now come from the RECEIVER
        try:
            rel_avg = metrics[situation]["receiver"]["reliable"]["latency_avg_ms"]
            rel_p95 = metrics[situation]["receiver"]["reliable"]["latency_p95_ms"]
            unrel_avg = metrics[situation]["receiver"]["unreliable"]["latency_avg_ms"]
            unrel_p95 = metrics[situation]["receiver"]["unreliable"]["latency_p95_ms"]
            
            reliable_avg.append(rel_avg if rel_avg is not None else 0)
            reliable_p95.append(rel_p95 if rel_p95 is not None else 0)
            unreliable_avg.append(unrel_avg if unrel_avg is not None else 0)
            unreliable_p95.append(unrel_p95 if unrel_p95 is not None else 0)
        except KeyError:
            print(f"[!] Warning: Missing latency data for {situation}")
            reliable_avg.append(0)
            reliable_p95.append(0)
            unreliable_avg.append(0)
            unreliable_p95.append(0)

    
    # Plot bars
    ax.bar(x - 1.5*width, reliable_avg, width, label='Reliable Avg', color='#2E86AB', alpha=0.9)
    ax.bar(x - 0.5*width, reliable_p95, width, label='Reliable p95', color='#2E86AB', alpha=0.5)
    ax.bar(x + 0.5*width, unreliable_avg, width, label='Unreliable Avg', color='#A23B72', alpha=0.9)
    ax.bar(x + 1.5*width, unreliable_p95, width, label='Unreliable p95', color='#A23B72', alpha=0.5)
    
    ax.set_xlabel('Network Condition', fontsize=12, fontweight='bold')
    ax.set_ylabel('Latency (ms)', fontsize=12, fontweight='bold')
    ax.set_title('Latency Comparison Across Network Conditions (Avg & p95)', fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels([SITUATION_LABELS.get(s, s) for s in SITUATIONS])
    ax.legend(loc='upper left')
    ax.grid(axis='y', alpha=0.3)
    ax.set_yscale('log') # Latency often varies by orders of magnitude
    ax.set_ylabel('Latency (ms) - Log Scale', fontsize=12, fontweight='bold')
    
    plt.tight_layout()
    plt.savefig('charts/latency_avg_p95_comparison.png', dpi=300, bbox_inches='tight')
    plt.close()
    print("[OK] Generated: charts/latency_avg_p95_comparison.png")


def plot_latency_tail_comparison(metrics):
    """(NEW) Generate tail latency comparison chart (p99 and Max)."""
    fig, ax = plt.subplots(figsize=(12, 7))
    
    x = np.arange(len(SITUATIONS))
    width = 0.2
    
    # Collect data
    reliable_p99 = []
    reliable_max = []
    unreliable_p99 = []
    unreliable_max = []
    
    for situation in SITUATIONS:
        if situation not in metrics:
            reliable_p99.append(0)
            reliable_max.append(0)
            unreliable_p99.append(0)
            unreliable_max.append(0)
            continue
        
        try:
            rel_p99 = metrics[situation]["receiver"]["reliable"]["latency_p99_ms"]
            rel_max = metrics[situation]["receiver"]["reliable"]["latency_max_ms"]
            unrel_p99 = metrics[situation]["receiver"]["unreliable"]["latency_p99_ms"]
            unrel_max = metrics[situation]["receiver"]["unreliable"]["latency_max_ms"]
            
            reliable_p99.append(rel_p99 if rel_p99 is not None else 0)
            reliable_max.append(rel_max if rel_max is not None else 0)
            unreliable_p99.append(unrel_p99 if unrel_p99 is not None else 0)
            unreliable_max.append(unrel_max if unrel_max is not None else 0)
        except KeyError:
            print(f"[!] Warning: Missing tail latency data for {situation}")
            reliable_p99.append(0)
            reliable_max.append(0)
            unreliable_p99.append(0)
            unreliable_max.append(0)
    
    # Plot bars
    ax.bar(x - 1.5*width, reliable_p99, width, label='Reliable p99', color='#1E6091', alpha=0.9)
    ax.bar(x - 0.5*width, reliable_max, width, label='Reliable Max', color='#1E6091', alpha=0.5)
    ax.bar(x + 0.5*width, unreliable_p99, width, label='Unreliable p99', color='#720026', alpha=0.9)
    ax.bar(x + 1.5*width, unreliable_max, width, label='Unreliable Max', color='#720026', alpha=0.5)
    
    ax.set_xlabel('Network Condition', fontsize=12, fontweight='bold')
    ax.set_ylabel('Latency (ms) - Log Scale', fontsize=12, fontweight='bold')
    ax.set_title('Tail Latency Comparison Across Network Conditions (p99 & Max)', fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels([SITUATION_LABELS.get(s, s) for s in SITUATIONS])
    ax.legend(loc='upper left')
    ax.grid(axis='y', alpha=0.3)
    ax.set_yscale('log')
    
    plt.tight_layout()
    plt.savefig('charts/latency_tail_comparison.png', dpi=300, bbox_inches='tight')
    plt.close()
    print("[OK] Generated: charts/latency_tail_comparison.png")


def plot_jitter_comparison(metrics):
    """(UPDATED) Generate jitter comparison chart for both channels."""
    fig, ax = plt.subplots(figsize=(10, 6))
    
    x = np.arange(len(SITUATIONS))
    width = 0.35
    
    # Collect jitter data (from receiver)
    reliable_jitter = []
    unreliable_jitter = []

    for situation in SITUATIONS:
        if situation not in metrics:
            reliable_jitter.append(0)
            unreliable_jitter.append(0)
            continue
        
        try:
            rel_jit = metrics[situation]["receiver"]["reliable"]["jitter_ms"]
            unrel_jit = metrics[situation]["receiver"]["unreliable"]["jitter_ms"]
            reliable_jitter.append(rel_jit if rel_jit is not None else 0)
            unreliable_jitter.append(unrel_jit if unrel_jit is not None else 0)
        except KeyError:
            print(f"[!] Warning: Missing jitter data for {situation}")
            reliable_jitter.append(0)
            unreliable_jitter.append(0)
    
    # Plot bars
    ax.bar(x - width/2, reliable_jitter, width, label='Reliable', color='#2E86AB', alpha=0.8)
    ax.bar(x + width/2, unreliable_jitter, width, label='Unreliable', color='#A23B72', alpha=0.8)
    
    ax.set_xlabel('Network Condition', fontsize=12, fontweight='bold')
    ax.set_ylabel('Jitter (ms)', fontsize=12, fontweight='bold')
    ax.set_title('Jitter Comparison (RFC 3550)', fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels([SITUATION_LABELS.get(s, s) for s in SITUATIONS])
    ax.legend()
    ax.grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig('charts/jitter_comparison.png', dpi=300, bbox_inches='tight')
    plt.close()
    print("[OK] Generated: charts/jitter_comparison.png")


def plot_throughput_comparison(metrics):
    """(UNCHANGED) Generate throughput comparison chart."""
    fig, ax = plt.subplots(figsize=(10, 6))
    
    x = np.arange(len(SITUATIONS))
    width = 0.35
    
    # Collect throughput data (from receiver)
    reliable_throughput = []
    unreliable_throughput = []
    
    for situation in SITUATIONS:
        if situation not in metrics:
            reliable_throughput.append(0)
            unreliable_throughput.append(0)
            continue
        
        try:
            rel_thr = metrics[situation]["receiver"]["reliable"]["throughput_Bps"]
            unrel_thr = metrics[situation]["receiver"]["unreliable"]["throughput_Bps"]
            reliable_throughput.append(rel_thr if rel_thr is not None else 0)
            unreliable_throughput.append(unrel_thr if unrel_thr is not None else 0)
        except KeyError:
            print(f"[!] Warning: Missing throughput data for {situation}")
            reliable_throughput.append(0)
            unreliable_throughput.append(0)
    
    # Plot bars
    ax.bar(x - width/2, reliable_throughput, width, label='Reliable', color='#2E86AB', alpha=0.8)
    ax.bar(x + width/2, unreliable_throughput, width, label='Unreliable', color='#A23B72', alpha=0.8)
    
    ax.set_xlabel('Network Condition', fontsize=12, fontweight='bold')
    ax.set_ylabel('Throughput (Bytes/sec)', fontsize=12, fontweight='bold')
    ax.set_title('Throughput Comparison Across Network Conditions', fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels([SITUATION_LABELS.get(s, s) for s in SITUATIONS])
    ax.legend()
    ax.grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig('charts/throughput_comparison.png', dpi=300, bbox_inches='tight')
    plt.close()
    print("[OK] Generated: charts/throughput_comparison.png")


def plot_buffer_comparison(metrics):
    """(NEW) Generate buffer occupancy comparison chart (Avg & p95)."""
    fig, ax = plt.subplots(figsize=(12, 7))
    
    x = np.arange(len(SITUATIONS))
    width = 0.2
    
    # Collect data
    reliable_avg = []
    reliable_p95 = []
    unreliable_avg = []
    unreliable_p95 = []
    
    for situation in SITUATIONS:
        if situation not in metrics:
            reliable_avg.append(0)
            reliable_p95.append(0)
            unreliable_avg.append(0)
            unreliable_p95.append(0)
            continue
        
        try:
            rel_avg = metrics[situation]["receiver"]["reliable"]["buffer_avg_ms"]
            rel_p95 = metrics[situation]["receiver"]["reliable"]["buffer_p95_ms"]
            unrel_avg = metrics[situation]["receiver"]["unreliable"]["buffer_avg_ms"]
            unrel_p95 = metrics[situation]["receiver"]["unreliable"]["buffer_p95_ms"]
            
            reliable_avg.append(rel_avg if rel_avg is not None else 0)
            reliable_p95.append(rel_p95 if rel_p95 is not None else 0)
            unreliable_avg.append(unrel_avg if unrel_avg is not None else 0)
            unreliable_p95.append(unrel_p95 if unrel_p95 is not None else 0)
        except KeyError:
            print(f"[!] Warning: Missing buffer data for {situation}")
            reliable_avg.append(0)
            reliable_p95.append(0)
            unreliable_avg.append(0)
            unreliable_p95.append(0)

    # Plot bars
    ax.bar(x - 1.5*width, reliable_avg, width, label='Reliable Avg', color='#007F5F', alpha=0.9)
    ax.bar(x - 0.5*width, reliable_p95, width, label='Reliable p95', color='#007F5F', alpha=0.5)
    ax.bar(x + 0.5*width, unreliable_avg, width, label='Unreliable Avg', color='#E07A5F', alpha=0.9)
    ax.bar(x + 1.5*width, unreliable_p95, width, label='Unreliable p95', color='#E07A5F', alpha=0.5)
    
    ax.set_xlabel('Network Condition', fontsize=12, fontweight='bold')
    ax.set_ylabel('Buffer (ms)', fontsize=12, fontweight='bold')
    ax.set_title('Receiver Buffer Occupancy Comparison (Avg & p95)', fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels([SITUATION_LABELS.get(s, s) for s in SITUATIONS])
    ax.legend(loc='upper left')
    ax.grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig('charts/buffer_comparison.png', dpi=300, bbox_inches='tight')
    plt.close()
    print("[OK] Generated: charts/buffer_comparison.png")


def plot_pdr_comparison(metrics):
    """(UNCHANGED) Generate Packet Delivery Ratio comparison chart."""
    fig, ax = plt.subplots(figsize=(10, 6))
    
    x = np.arange(len(SITUATIONS))
    width = 0.35
    
    # Compute PDR for each situation
    reliable_pdr = []
    unreliable_pdr = []
    
    for situation in SITUATIONS:
        if situation not in metrics:
            reliable_pdr.append(0)
            unreliable_pdr.append(0)
            continue
        
        reliable_pdr.append(compute_pdr(metrics, situation, "reliable"))
        unreliable_pdr.append(compute_pdr(metrics, situation, "unreliable"))
    
    # Plot bars
    ax.bar(x - width/2, reliable_pdr, width, label='Reliable', color='#06A77D', alpha=0.8)
    ax.bar(x + width/2, unreliable_pdr, width, label='Unreliable', color='#D62246', alpha=0.8)
    
    # Add horizontal line at 100%
    ax.axhline(y=100, color='gray', linestyle='--', alpha=0.5, linewidth=1)
    
    ax.set_xlabel('Network Condition', fontsize=12, fontweight='bold')
    ax.set_ylabel('Packet Delivery Ratio (%)', fontsize=12, fontweight='bold')
    ax.set_title('Packet Delivery Ratio (PDR) Comparison', fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels([SITUATION_LABELS.get(s, s) for s in SITUATIONS])
    ax.set_ylim([0, 105])
    ax.legend()
    ax.grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig('charts/pdr_comparison.png', dpi=300, bbox_inches='tight')
    plt.close()
    print("[OK] Generated: charts/pdr_comparison.png")


def plot_retransmissions(metrics):
    """(UNCHANGED) Generate retransmissions chart (reliable channel only)."""
    fig, ax = plt.subplots(figsize=(10, 6))
    
    x = np.arange(len(SITUATIONS))
    width = 0.5
    
    # Collect retransmission data
    retransmissions = []
    
    for situation in SITUATIONS:
        if situation not in metrics:
            retransmissions.append(0)
            continue
        
        try:
            retrans = metrics[situation]["sender"]["reliable"]["retransmissions"]
            retransmissions.append(retrans if retrans is not None else 0)
        except KeyError:
            print(f"[!] Warning: Missing retransmission data for {situation}")
            retransmissions.append(0)
            
    # Plot bars
    bars = ax.bar(x, retransmissions, width, color='#C73E1D', alpha=0.8)
    
    # Add value labels on bars
    for bar in bars:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
                f'{int(height)}',
                ha='center', va='bottom', fontweight='bold')
    
    ax.set_xlabel('Network Condition', fontsize=12, fontweight='bold')
    ax.set_ylabel('Retransmission Count', fontsize=12, fontweight='bold')
    ax.set_title('Retransmissions (Reliable Channel)', fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels([SITUATION_LABELS.get(s, s) for s in SITUATIONS])
    ax.grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig('charts/retransmissions.png', dpi=300, bbox_inches='tight')
    plt.close()
    print("[OK] Generated: charts/retransmissions.png")


def plot_reliability_latency_tradeoff(metrics):
    """(UPDATED) Generate reliability vs latency trade-off scatter plot."""
    fig, ax = plt.subplots(figsize=(10, 8))
    
    # Collect data for both channels
    for channel, color, marker in [("reliable", '#2E86AB', 'o'), ("unreliable", '#A23B72', 's')]:
        latencies = []
        pdrs = []
        labels = []
        
        for situation in SITUATIONS:
            if situation not in metrics:
                continue
            
            try:
                # Get latency (avg) - UPDATED from p50 and sender-based
                lat = metrics[situation]["receiver"][channel]["latency_avg_ms"]
                
                if lat is None or lat == 0:
                    continue
                
                # Get PDR
                pdr = compute_pdr(metrics, situation, channel)
                
                latencies.append(lat)
                pdrs.append(pdr)
                labels.append(SITUATION_LABELS.get(situation, situation))
            except KeyError:
                print(f"[!] Warning: Missing data for {situation} in trade-off plot")
                continue
        
        # Plot scatter
        ax.scatter(latencies, pdrs, s=200, alpha=0.7, color=color, 
                  marker=marker, label=channel.capitalize(), edgecolors='black', linewidth=1.5)
        
        # Add labels
        for i, label in enumerate(labels):
            ax.annotate(label, (latencies[i], pdrs[i]), 
                       xytext=(8, 8), textcoords='offset points',
                       fontsize=9, alpha=0.8)
    
    ax.set_xlabel('Latency Avg (ms)', fontsize=12, fontweight='bold')
    ax.set_ylabel('Packet Delivery Ratio (%)', fontsize=12, fontweight='bold')
    ax.set_title('Reliability vs Latency Trade-off', fontsize=14, fontweight='bold')
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.3)
    ax.set_ylim([0, 105])
    
    plt.tight_layout()
    plt.savefig('charts/reliability_latency_tradeoff.png', dpi=300, bbox_inches='tight')
    plt.close()
    print("[OK] Generated: charts/reliability_latency_tradeoff.png")


def generate_summary_table(metrics):
    """(UPDATED) Generate and print a summary table of all metrics."""
    print("\n" + "="*132)
    print("METRICS SUMMARY TABLE")
    print("="*132)
    
    header = f"{'Situation':<12} {'Channel':<10} {'Sent':<8} {'Recv':<8} {'PDR%':<8} " \
             f"{'Avg(ms)':<10} {'p95(ms)':<10} {'Jitter':<10} {'BufAvg(ms)':<11} {'Thr(B/s)':<12} {'Retrans':<8}"
    print(header)
    print("-"*132)
    
    for situation in SITUATIONS:
        if situation not in metrics:
            continue
        
        for channel in CHANNELS:
            try:
                sender = metrics[situation]["sender"][channel]
                receiver = metrics[situation]["receiver"][channel]
                
                sent = sender.get("sent_packets")
                recv = receiver.get("packets")
                pdr = compute_pdr(metrics, situation, channel)
                
                # UPDATED: All latency from receiver, use Avg instead of p50
                avg = receiver.get("latency_avg_ms")
                p95 = receiver.get("latency_p95_ms")
                
                jitter = receiver.get("jitter_ms")
                buf_avg = receiver.get("buffer_avg_ms") # NEWLY ADDED
                throughput = receiver.get("throughput_Bps")
                retrans = sender.get("retransmissions")
                
                # Format values
                sent_str = f"{sent}" if sent is not None else "N/A"
                recv_str = f"{recv}" if recv is not None else "N/A"
                retrans_str = f"{retrans}" if retrans is not None else "N/A"
                avg_str = f"{avg:.2f}" if avg is not None else "N/A"
                p95_str = f"{p95:.2f}" if p95 is not None else "N/A"
                jitter_str = f"{jitter:.3f}" if jitter is not None else "N/A"
                buf_avg_str = f"{buf_avg:.2f}" if buf_avg is not None else "N/A"
                thr_str = f"{throughput:.1f}" if throughput is not None else "N/A"
                
                row = f"{SITUATION_LABELS.get(situation, situation):<12} {channel:<10} {sent_str:<8} {recv_str:<8} " \
                      f"{pdr:<8.2f} {avg_str:<10} {p95_str:<10} {jitter_str:<10} {buf_avg_str:<11} " \
                      f"{thr_str:<12} {retrans_str:<8}"
                print(row)
            except KeyError as e:
                print(f"[!] Warning: Missing key {e} for {situation}/{channel} in summary table")
    
    print("="*132 + "\n")


def main():
    """Main function to generate all charts."""
    print("\n" + "="*70)
    print("CHART GENERATION")
    print("="*70 + "\n")
    
    # Ensure output directory exists
    Path("charts").mkdir(exist_ok=True)
    
    # Load metrics
    print("Loading metrics from metrics/ directory...")
    metrics = load_metrics()
    
    if not metrics:
        print("[X] Error: No metrics files found in metrics/ directory")
        print("  Make sure you've run experiments and metrics files are named correctly")
        print("  (e.g., sender_high.json, receiver_high.json)")
        return
    
    print(f"[OK] Loaded metrics for {len(metrics)} situation(s)\n")
    
    # Generate all charts
    print("Generating charts...")
    try:
        plot_latency_avg_p95_comparison(metrics)
        plot_latency_tail_comparison(metrics) # NEW
        plot_jitter_comparison(metrics)
        plot_throughput_comparison(metrics)
        plot_buffer_comparison(metrics) # NEW
        plot_pdr_comparison(metrics)
        plot_retransmissions(metrics)
        plot_reliability_latency_tradeoff(metrics)
        
        print("\n[OK] All charts generated successfully in charts/ directory")
        
        # Print summary table
        generate_summary_table(metrics)
        
        print("Next steps:")
        print("1. Review charts in the charts/ directory")
        print("2. Include them in your technical report")
        print("3. Discuss trade-offs and observations")
        print()
    except Exception as e:
        print(f"\n[X] An error occurred during chart generation: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()