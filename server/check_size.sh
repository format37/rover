ls -lR ./sessions/ | awk '/^-/ {sum += $5} END {printf "%.2f MB\n", sum/1024/1024}'
