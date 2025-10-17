#!/usr/bin/env python3
import docker
import time
import os
import requests
from datetime import datetime

# === Configuration ===
BOT_TOKEN = ""
CHAT_ID = ""
LOG_DIR = os.path.expanduser("~/docker_monitor_logs")
INTERVAL = 300
THRESHOLD = 80
REPORT_HOUR = 17
REPORT_MIN = 59

os.makedirs(LOG_DIR, exist_ok=True)
client = docker.from_env()

def send_telegram(message: str):
    """Send message to Telegram."""
    url = f"https://api.telegram.org/bot${BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, data=payload, timeout=5)
    except requests.RequestException:
        pass

def fmt_bytes(num):
    """Format byte"""
    for unit in ['B', 'kB', 'MB', 'GB', 'TB']:
        if num < 1024:
            return f"{num:.1f}{unit}"
        num /= 1024
    return f"{num:.1f}PB"

def get_stats(container):
    """Get statistic Docker container"""
    try:
        stats = container.stats(stream=False)
        cpu_total = stats["cpu_stats"]["cpu_usage"]["total_usage"]
        cpu_system = stats["cpu_stats"].get("system_cpu_usage", 1)
        cores = len(stats["cpu_stats"]["cpu_usage"].get("percpu_usage", [])) or 1
        cpu_percent = (cpu_total/cpu_system) * 100 * cores

        mem_usage = stats["memory_stats"]["usage"]
        mem_limit = stats["memory_stats"]["limit"]

        # NET I/O
        net_rx, net_tx = 0, 0
        for iface in stats.get("networks", {}).values():
            net_rx += iface.get("rx_bytes", 0)
            net_tx += iface.get("tx_bytes", 0)

        # BLOCK I/O
        blk_read, blk_write = 0, 0
        for blk in stats.get("blkio_stats", {}).get("io_service_bytes_recursive", []):
            if blk.get("op") == "Read":
                blk_read += blk.get("value", 0)
            elif blk.get("op") == "Write":
                blk_write += blk.get("value", 0)

        return {
            "cpu": cpu_percent,
            "mem_usage": mem_usage,
            "mem_limit": mem_limit,
            "net_in": net_rx,
            "net_out": net_tx,
            "block_in": blk_read,
            "block_out": blk_write,
        }
    except Exception:
        return None

def log_stats():
    """Write daily log"""
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%Y-%m-%d %H:%M:%S")
    log_path = os.path.join(LOG_DIR, f"docker_{date_str}.log")

    with open(log_path, "a") as f:
        f.write(f"[{time_str}]\n")

        for c in client.containers.list():
            s = get_stats(c)
            if not s:
                continue

            cpu = s["cpu"]
            mem = f"{s['mem_usage']/(1024**2):.0f}MiB / {s['mem_limit']/(1024**3):.0f}GiB"
            net_in = fmt_bytes(s["net_in"])
            net_out = fmt_bytes(s["net_out"])
            block_in = fmt_bytes(s["block_in"])
            block_out = fmt_bytes(s["block_out"])

            f.write(f"{c.name} CPU={cpu:.1f} MEM={mem} NET_IN={net_in} NET_OUT={net_out} BLOCK_IN={block_in} BLOCK_OUT={block_out}\n")

            # Alert High CPU
            if cpu > THRESHOLD:
                alert = (
                    f"⚠️ *HIGH CPU ALERT*%0A🕒 {time_str}%0A🧩 Container: *{c.name}*"
                    f"%0A🔥 CPU: *{cpu:.1f}%*%0A💾 MEM: {mem}"
                    f"%0A🌐 NET I/O: {net_in} / {net_out}%0A📀 BLOCK I/O: {block_in} / {block_out}"
                )
                send_telegram(alert)

        f.write("---------------------------------------\n")

def generate_daily_report():
    """Make daily report & send to Telegram."""
    date_str = datetime.now().strftime("%Y-%m-%d")
    log_path = os.path.join(LOG_DIR, f"docker_{date_str}.log")
    if not os.path.exists(log_path):
        return

    stats = {}
    with open(log_path) as f:
        for line in f:
            if "CPU=" not in line:
                continue
            parts = line.split()
            name = parts[0]
            cpu = float(parts[1].split("=")[1])
            net_in = parts[3].split("=")[1]
            net_out = parts[4].split("=")[1]
            blk_in = parts[5].split("=")[1]
            blk_out = parts[6].split("=")[1]

            stats.setdefault(name, {"cpu": [], "net_in": 0, "net_out": 0, "blk_in": 0, "blk_out": 0})
            stats[name]["cpu"].append(cpu)

    report = f"*📊 Daily Docker Report ({date_str})*\n\n"
    for name, s in stats.items():
        avg_cpu = sum(s["cpu"]) / len(s["cpu"])
        report += (
            f"🧩 {name}\n"
            f"🔥 Avg CPU: {avg_cpu:.2f}%\n"
            f"🌐 Net I/O: IN {s['net_in']} | OUT {s['net_out']}\n"
            f"📀 Block I/O: IN {s['blk_in']} | OUT {s['blk_out']}\n\n"
        )

    send_telegram(report)

# === MAIN LOOP ===
last_report_date = None
print("🚀 Docker Monitor (Python) running...")

while True:
    now = datetime.now()
    log_stats()

    # Daily report 23:59
    if (
        now.hour == REPORT_HOUR
        and now.minute >= REPORT_MIN
        and last_report_date != now.date()
    ):
        generate_daily_report()
        last_report_date = now.date()

    time.sleep(INTERVAL)