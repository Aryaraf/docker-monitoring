#!/bin/bash
# docker_monitor_pro_v2.sh
# Docker Monitoring + Telegram Alerts + Daily Report (CPU, MEM, NET I/O, BLOCK I/O)

BOT_TOKEN=""
CHAT_ID=""

LOG_DIR="$HOME/docker_monitor_logs"
INTERVAL=300         
THRESHOLD=80      
REPORT_HOUR=16
REPORT_MIN=59
LAST_DAILY=""

mkdir -p "$LOG_DIR"

send_telegram() {
  local MESSAGE="$1"
  curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
    -d chat_id="${CHAT_ID}" \
    -d parse_mode="Markdown" \
    -d text="$MESSAGE" > /dev/null
}

calc_average() {
  awk '/CPU=/{cpu[$1]+=$2; count[$1]++} /NET_IN=/{net_in[$1]+=$3} /NET_OUT=/{net_out[$1]+=$4} /BLOCK_IN=/{block_in[$1]+=$5} /BLOCK_OUT=/{block_out[$1]+=$6}
  END {
    for (c in cpu)
      printf "%s %.2f %.2f %.2f %.2f %.2f\n", c, cpu[c]/count[c], net_in[c], net_out[c], block_in[c], block_out[c]
  }' "$1"
}

while true; do
  TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
  DATE=$(date '+%Y-%m-%d')
  LOG_FILE="$LOG_DIR/docker_${DATE}.log"

  echo "[$TIMESTAMP]" >> "$LOG_FILE"

  docker ps --format '{{.Names}}' | while read -r container; do
    STATS=$(docker stats --no-stream --format "{{.CPUPerc}} {{.MemUsage}} {{.NetIO}} {{.BlockIO}}" "$container" 2>/dev/null)

    CPU=$(echo "$STATS" | awk '{print $1}' | tr -d '%')
    MEM=$(echo "$STATS" | awk '{print $2" "$3}')
    NET_IN=$(echo "$STATS" | awk '{print $4}')
    NET_OUT=$(echo "$STATS" | awk '{print $5}')
    BLOCK_IN=$(echo "$STATS" | awk '{print $6}')
    BLOCK_OUT=$(echo "$STATS" | awk '{print $7}')

    echo "$container CPU=$CPU MEM=$MEM NET_IN=$NET_IN NET_OUT=$NET_OUT BLOCK_IN=$BLOCK_IN BLOCK_OUT=$BLOCK_OUT" >> "$LOG_FILE"

    # === ALERTS ===
    if (( $(echo "$CPU > $THRESHOLD" | bc -l) )); then
      MESSAGE="⚠️ *HIGH CPU ALERT*%0A🕒 $TIMESTAMP%0A🧩 Container: *$container*%0A🔥 CPU: *${CPU}%*%0A💾 Memory: ${MEM}%0A🌐 Net I/O: ${NET_IN} / ${NET_OUT}%0A📀 Block I/O: ${BLOCK_IN} / ${BLOCK_OUT}"
      send_telegram "$MESSAGE"
    fi
  done

  echo "---------------------------------------" >> "$LOG_FILE"

  HOUR=$(date +%H)
  MIN=$(date +%M)

  # === DAILY REPORT ===
  if [[ "$HOUR" -eq "$REPORT_HOUR" && "$MIN" -ge "$REPORT_MIN" && "$LAST_DAILY" != "$DATE" ]]; then
    REPORT=$(calc_average "$LOG_FILE" | awk -v d="$(date '+%Y-%m-%d')" \
      'BEGIN {printf "*📊 Daily Docker Report (%s)*\n\n", d}
       {printf "🧩 %s\n🔥 Avg CPU: %.2f%%\n🌐 Net I/O: IN %.2f | OUT %.2f\n📀 Block I/O: IN %.2f | OUT %.2f\n\n", $1, $2, $3, $4, $5, $6}')

    if [ -n "$REPORT" ]; then
      send_telegram "$REPORT"
      LAST_DAILY="$DATE"
    fi
  fi

  sleep $INTERVAL
done
