"""
Memory Monitor for BioShock Infinite (32-bit)
Monitors the game's virtual memory usage in real-time.
Logs peak usage to help identify which levels approach the 4GB limit.

Usage: python tools/memory_monitor.py
  - Automatically attaches to BioShockInfinite.exe when it starts
  - Logs memory stats every 2 seconds
  - Saves peak readings to tools/memory_log.txt
"""

import subprocess
import time
import sys
import os
from datetime import datetime

PROCESS_NAME = "BioShockInfinite"
MAX_ADDRESS_SPACE_MB = 4096  # 4GB for 32-bit with LAA


def get_process_memory(name):
    """Get memory stats via PowerShell Get-Process (works cross-bitness).
    Returns dict with memory values in MB, or None if process not found.
    """
    try:
        ps_cmd = (
            f"$p = Get-Process -Name '{name}' -ErrorAction SilentlyContinue; "
            f"if ($p) {{ "
            f"Write-Output \"$($p.Id)|$($p.PrivateMemorySize64)|$($p.WorkingSet64)|"
            f"$($p.PeakWorkingSet64)|$($p.VirtualMemorySize64)|$($p.PeakVirtualMemorySize64)|"
            f"$($p.PagedMemorySize64)\" "
            f"}} else {{ Write-Output 'NONE' }}"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=5
        )
        output = result.stdout.strip()
        if not output or output == "NONE":
            return None

        parts = output.split("|")
        if len(parts) < 7:
            return None

        mb = 1024 * 1024
        private = int(parts[1]) / mb
        virtual = int(parts[4]) / mb

        return {
            "pid": int(parts[0]),
            "private_mb": private,
            "working_set_mb": int(parts[2]) / mb,
            "peak_working_set_mb": int(parts[3]) / mb,
            "virtual_mb": virtual,
            "peak_virtual_mb": int(parts[5]) / mb,
            "paged_mb": int(parts[6]) / mb,
            "free_mb": MAX_ADDRESS_SPACE_MB - virtual,
        }
    except Exception as e:
        return None


def main():
    log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memory_log.txt")
    poll_interval = 2.0

    print("=" * 65)
    print("  BioShock Infinite Memory Monitor")
    print("  4GB address space limit (LAA enabled)")
    print("=" * 65)
    print(f"\nWaiting for {PROCESS_NAME}...")

    attached = False
    peak_private = 0
    peak_virtual = 0
    sample_count = 0

    with open(log_path, "a") as log:
        log.write(f"\n{'='*60}\n")
        log.write(f"Session: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        log.write(f"{'='*60}\n")
        log.flush()

        while True:
            try:
                info = get_process_memory(PROCESS_NAME)

                if info is None:
                    if attached:
                        # Process just exited
                        print(f"\n\nProcess exited.")
                        print(f"  Peak private: {peak_private:.0f} MB")
                        print(f"  Peak virtual: {peak_virtual:.0f} MB")
                        log.write(f"\nProcess exited. Peak private: {peak_private:.0f} MB, "
                                  f"Peak virtual: {peak_virtual:.0f} MB\n")
                        log.flush()
                        attached = False
                        peak_private = 0
                        peak_virtual = 0
                        sample_count = 0
                        print(f"\nWaiting for {PROCESS_NAME}...")
                    time.sleep(2)
                    continue

                if not attached:
                    attached = True
                    print(f"\nAttached to PID {info['pid']}\n")
                    log.write(f"Attached to PID {info['pid']}\n")
                    log.flush()

                # Track peaks
                peak_private = max(peak_private, info["private_mb"])
                peak_virtual = max(peak_virtual, info["virtual_mb"])
                sample_count += 1

                # Progress bar
                bar_len = 30
                used_pct = min(info["virtual_mb"] / MAX_ADDRESS_SPACE_MB, 1.0)
                bar_fill = int(bar_len * used_pct)
                bar = "#" * bar_fill + "-" * (bar_len - bar_fill)

                free = info["free_mb"]
                status = ""
                if free < 200:
                    status = " ** CRITICAL **"
                elif free < 500:
                    status = " * LOW *"

                line = (
                    f"\r[{bar}] "
                    f"Virtual: {info['virtual_mb']:.0f} MB | "
                    f"Private: {info['private_mb']:.0f} MB | "
                    f"WorkSet: {info['working_set_mb']:.0f} MB | "
                    f"Free: {free:.0f} MB{status}    "
                )
                sys.stdout.write(line)
                sys.stdout.flush()

                # Log periodically
                if sample_count % 5 == 0:
                    log.write(
                        f"{datetime.now().strftime('%H:%M:%S')} | "
                        f"Virtual: {info['virtual_mb']:.0f} MB | "
                        f"Private: {info['private_mb']:.0f} MB | "
                        f"WorkSet: {info['working_set_mb']:.0f} MB | "
                        f"Free: {free:.0f} MB{status}\n"
                    )
                    log.flush()

                time.sleep(poll_interval)

            except KeyboardInterrupt:
                print(f"\n\nStopped.")
                print(f"  Peak private: {peak_private:.0f} MB")
                print(f"  Peak virtual: {peak_virtual:.0f} MB")
                log.write(f"\nManual stop. Peak private: {peak_private:.0f} MB, "
                          f"Peak virtual: {peak_virtual:.0f} MB\n")
                break


if __name__ == "__main__":
    main()
