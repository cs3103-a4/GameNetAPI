#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate comparison charts from collected metrics.
Works with both automated (emulator) and manual (Clumsy) experiment runs.

Usage:
    python3 generate_charts_manual.py

Expects metrics files in metrics/ directory:
    - baseline_sender.json, baseline_receiver.json
    - lowloss_sender.json, lowloss_receiver.json
    - highloss_sender.json, highloss_receiver.json
    - highjitter_sender.json, highjitter_receiver.json
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
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# Scenarios to plot
SCENARIOS = ["direct", "low", "high", "jitter"]
SCENARIO_LABELS = {
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
    
    for scenario in SCENARIOS:
        sender_path = f"metrics/sender_{scenario}.json"
        receiver_path = f"metrics/receiver_{scenario}.json"
        
        if not os.path.exists(sender_path) or not os.path.exists(receiver_path):
            print(f"[!] Warning: Missing metrics for {scenario}")
            continue
        
        with open(sender_path, 'r') as f:
            sender_data = json.load(f)
        with open(receiver_path, 'r') as f:
            receiver_data = json.load(f)
        
        metrics[scenario] = {
            "sender": sender_data,
            "receiver": receiver_data
        }
    
    return metrics


def compute_pdr(metrics, scenario, channel):
    """Compute Packet Delivery Ratio for a scenario and channel."""
    try:
        sent = metrics[scenario]["sender"][channel]["sent_packets"]
        received = metrics[scenario]["receiver"][channel]["packets"]
        return (received / sent * 100.0) if sent > 0 else 0.0
    except (KeyError, ZeroDivisionError):
        return 0.0


def plot_latency_comparison(metrics):
    """Generate latency comparison chart (p50 and p95)."""
    fig, ax = plt.subplots(figsize=(12, 6))
    
    x = np.arange(len(SCENARIOS))
    width = 0.2
    
    # Collect data
    reliable_p50 = []
    reliable_p95 = []
    unreliable_p50 = []
    unreliable_p95 = []
    
    for scenario in SCENARIOS:
        if scenario not in metrics:
            reliable_p50.append(0)
            reliable_p95.append(0)
            unreliable_p50.append(0)
            unreliable_p95.append(0)
            continue
        
        # Reliable latency from sender (ACK-based)
        rel_p50 = metrics[scenario]["sender"]["reliable"]["latency_p50_ms"]
        rel_p95 = metrics[scenario]["sender"]["reliable"]["latency_p95_ms"]
        reliable_p50.append(rel_p50 if rel_p50 is not None else 0)
        reliable_p95.append(rel_p95 if rel_p95 is not None else 0)
        
        # Unreliable latency from receiver (one-way)
        unrel_p50 = metrics[scenario]["receiver"]["unreliable"]["latency_p50_ms"]
        unrel_p95 = metrics[scenario]["receiver"]["unreliable"]["latency_p95_ms"]
        unreliable_p50.append(unrel_p50 if unrel_p50 is not None else 0)
        unreliable_p95.append(unrel_p95 if unrel_p95 is not None else 0)
    
    # Plot bars
    ax.bar(x - 1.5*width, reliable_p50, width, label='Reliable p50', color='#2E86AB', alpha=0.8)
    ax.bar(x - 0.5*width, reliable_p95, width, label='Reliable p95', color='#2E86AB', alpha=0.5)
    ax.bar(x + 0.5*width, unreliable_p50, width, label='Unreliable p50', color='#A23B72', alpha=0.8)
    ax.bar(x + 1.5*width, unreliable_p95, width, label='Unreliable p95', color='#A23B72', alpha=0.5)
    
    ax.set_xlabel('Network Condition', fontsize=12, fontweight='bold')
    ax.set_ylabel('Latency (ms)', fontsize=12, fontweight='bold')
    ax.set_title('Latency Comparison Across Network Conditions', fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels([SCENARIO_LABELS[s] for s in SCENARIOS])
    ax.legend(loc='upper left')
    ax.grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig('charts/latency_comparison.png', dpi=300, bbox_inches='tight')
    plt.close()
    print("[OK] Generated: charts/latency_comparison.png")


def plot_jitter_comparison(metrics):
    """Generate jitter comparison chart."""
    fig, ax = plt.subplots(figsize=(10, 6))
    
    x = np.arange(len(SCENARIOS))
    width = 0.35
    
    # Collect jitter data (unreliable channel only, from receiver)
    unreliable_jitter = []
    
    for scenario in SCENARIOS:
        if scenario not in metrics:
            unreliable_jitter.append(0)
            continue
        
        jitter = metrics[scenario]["receiver"]["unreliable"]["jitter_ms"]
        unreliable_jitter.append(jitter if jitter is not None else 0)
    
    # Plot bars
    ax.bar(x, unreliable_jitter, width, label='Unreliable Channel', color='#F18F01', alpha=0.8)
    
    ax.set_xlabel('Network Condition', fontsize=12, fontweight='bold')
    ax.set_ylabel('Jitter (ms)', fontsize=12, fontweight='bold')
    ax.set_title('Jitter Comparison (RFC 3550)', fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels([SCENARIO_LABELS[s] for s in SCENARIOS])
    ax.legend()
    ax.grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig('charts/jitter_comparison.png', dpi=300, bbox_inches='tight')
    plt.close()
    print("[OK] Generated: charts/jitter_comparison.png")


def plot_throughput_comparison(metrics):
    """Generate throughput comparison chart."""
    fig, ax = plt.subplots(figsize=(10, 6))
    
    x = np.arange(len(SCENARIOS))
    width = 0.35
    
    # Collect throughput data (from receiver)
    reliable_throughput = []
    unreliable_throughput = []
    
    for scenario in SCENARIOS:
        if scenario not in metrics:
            reliable_throughput.append(0)
            unreliable_throughput.append(0)
            continue
        
        rel_thr = metrics[scenario]["receiver"]["reliable"]["throughput_Bps"]
        unrel_thr = metrics[scenario]["receiver"]["unreliable"]["throughput_Bps"]
        reliable_throughput.append(rel_thr)
        unreliable_throughput.append(unrel_thr)
    
    # Plot bars
    ax.bar(x - width/2, reliable_throughput, width, label='Reliable', color='#2E86AB', alpha=0.8)
    ax.bar(x + width/2, unreliable_throughput, width, label='Unreliable', color='#A23B72', alpha=0.8)
    
    ax.set_xlabel('Network Condition', fontsize=12, fontweight='bold')
    ax.set_ylabel('Throughput (Bytes/sec)', fontsize=12, fontweight='bold')
    ax.set_title('Throughput Comparison Across Network Conditions', fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels([SCENARIO_LABELS[s] for s in SCENARIOS])
    ax.legend()
    ax.grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig('charts/throughput_comparison.png', dpi=300, bbox_inches='tight')
    plt.close()
    print("[OK] Generated: charts/throughput_comparison.png")


def plot_pdr_comparison(metrics):
    """Generate Packet Delivery Ratio comparison chart."""
    fig, ax = plt.subplots(figsize=(10, 6))
    
    x = np.arange(len(SCENARIOS))
    width = 0.35
    
    # Compute PDR for each scenario
    reliable_pdr = []
    unreliable_pdr = []
    
    for scenario in SCENARIOS:
        if scenario not in metrics:
            reliable_pdr.append(0)
            unreliable_pdr.append(0)
            continue
        
        reliable_pdr.append(compute_pdr(metrics, scenario, "reliable"))
        unreliable_pdr.append(compute_pdr(metrics, scenario, "unreliable"))
    
    # Plot bars
    ax.bar(x - width/2, reliable_pdr, width, label='Reliable', color='#06A77D', alpha=0.8)
    ax.bar(x + width/2, unreliable_pdr, width, label='Unreliable', color='#D62246', alpha=0.8)
    
    # Add horizontal line at 100%
    ax.axhline(y=100, color='gray', linestyle='--', alpha=0.5, linewidth=1)
    
    ax.set_xlabel('Network Condition', fontsize=12, fontweight='bold')
    ax.set_ylabel('Packet Delivery Ratio (%)', fontsize=12, fontweight='bold')
    ax.set_title('Packet Delivery Ratio (PDR) Comparison', fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels([SCENARIO_LABELS[s] for s in SCENARIOS])
    ax.set_ylim([0, 105])
    ax.legend()
    ax.grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig('charts/pdr_comparison.png', dpi=300, bbox_inches='tight')
    plt.close()
    print("[OK] Generated: charts/pdr_comparison.png")


def plot_retransmissions(metrics):
    """Generate retransmissions chart (reliable channel only)."""
    fig, ax = plt.subplots(figsize=(10, 6))
    
    x = np.arange(len(SCENARIOS))
    width = 0.5
    
    # Collect retransmission data
    retransmissions = []
    
    for scenario in SCENARIOS:
        if scenario not in metrics:
            retransmissions.append(0)
            continue
        
        retrans = metrics[scenario]["sender"]["reliable"]["retransmissions"]
        retransmissions.append(retrans)
    
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
    ax.set_xticklabels([SCENARIO_LABELS[s] for s in SCENARIOS])
    ax.grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig('charts/retransmissions.png', dpi=300, bbox_inches='tight')
    plt.close()
    print("[OK] Generated: charts/retransmissions.png")


def plot_reliability_latency_tradeoff(metrics):
    """Generate reliability vs latency trade-off scatter plot."""
    fig, ax = plt.subplots(figsize=(10, 8))
    
    # Collect data for both channels
    for channel, color, marker in [("reliable", '#2E86AB', 'o'), ("unreliable", '#A23B72', 's')]:
        latencies = []
        pdrs = []
        labels = []
        
        for scenario in SCENARIOS:
            if scenario not in metrics:
                continue
            
            # Get latency (p50)
            if channel == "reliable":
                lat = metrics[scenario]["sender"][channel]["latency_p50_ms"]
            else:
                lat = metrics[scenario]["receiver"][channel]["latency_p50_ms"]
            
            if lat is None or lat == 0:
                continue
            
            # Get PDR
            pdr = compute_pdr(metrics, scenario, channel)
            
            latencies.append(lat)
            pdrs.append(pdr)
            labels.append(SCENARIO_LABELS[scenario])
        
        # Plot scatter
        ax.scatter(latencies, pdrs, s=200, alpha=0.7, color=color, 
                  marker=marker, label=channel.capitalize(), edgecolors='black', linewidth=1.5)
        
        # Add labels
        for i, label in enumerate(labels):
            ax.annotate(label, (latencies[i], pdrs[i]), 
                       xytext=(8, 8), textcoords='offset points',
                       fontsize=9, alpha=0.8)
    
    ax.set_xlabel('Latency p50 (ms)', fontsize=12, fontweight='bold')
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
    """Generate and print a summary table of all metrics."""
    print("\n" + "="*120)
    print("METRICS SUMMARY TABLE")
    print("="*120)
    
    header = f"{'Scenario':<12} {'Channel':<10} {'Sent':<8} {'Recv':<8} {'PDR%':<8} " \
             f"{'p50(ms)':<10} {'p95(ms)':<10} {'Jitter':<10} {'Thr(B/s)':<12} {'Retrans':<8}"
    print(header)
    print("-"*120)
    
    for scenario in SCENARIOS:
        if scenario not in metrics:
            continue
        
        for channel in CHANNELS:
            sender = metrics[scenario]["sender"][channel]
            receiver = metrics[scenario]["receiver"][channel]
            
            sent = sender["sent_packets"]
            recv = receiver["packets"]
            pdr = compute_pdr(metrics, scenario, channel)
            
            # Get latency based on channel
            if channel == "reliable":
                p50 = sender["latency_p50_ms"]
                p95 = sender["latency_p95_ms"]
            else:
                p50 = receiver["latency_p50_ms"]
                p95 = receiver["latency_p95_ms"]
            
            jitter = receiver["jitter_ms"]
            throughput = receiver["throughput_Bps"]
            retrans = sender["retransmissions"]
            
            # Format values
            p50_str = f"{p50:.2f}" if p50 is not None else "N/A"
            p95_str = f"{p95:.2f}" if p95 is not None else "N/A"
            jitter_str = f"{jitter:.3f}" if jitter is not None else "N/A"
            
            row = f"{SCENARIO_LABELS[scenario]:<12} {channel:<10} {sent:<8} {recv:<8} " \
                  f"{pdr:<8.2f} {p50_str:<10} {p95_str:<10} {jitter_str:<10} " \
                  f"{throughput:<12.1f} {retrans:<8}"
            print(row)
    
    print("="*120 + "\n")


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
        print("  Make sure you've run experiments first!")
        return
    
    print(f"[OK] Loaded metrics for {len(metrics)} scenario(s)\n")
    
    # Generate all charts
    print("Generating charts...")
    plot_latency_comparison(metrics)
    plot_jitter_comparison(metrics)
    plot_throughput_comparison(metrics)
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


if __name__ == "__main__":
    main()