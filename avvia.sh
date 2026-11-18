#!/bin/zsh
# Avvia l'interfaccia locale di anonym-data su http://localhost:8599
cd "$(dirname "$0")"
PORTA=8599
URL="http://localhost:$PORTA"

# se la porta e' occupata da un'istanza gia' avviata di questa app, apre solo il browser
PID=$(lsof -ti tcp:$PORTA -sTCP:LISTEN 2>/dev/null | head -1)
if [[ -n "$PID" ]]; then
  if ps -o command= -p "$PID" | grep -q "streamlit run app.py"; then
    echo "anonym-data e' gia' in esecuzione: apro $URL"
    open "$URL"
    exit 0
  fi
  echo "La porta $PORTA e' occupata da un altro programma:"
  ps -o pid=,command= -p "$PID"
  echo "Chiudilo oppure cambia la porta in .streamlit/config.toml."
  read -k1 "?Premi un tasto per chiudere."
  exit 1
fi

export STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
exec .venv/bin/streamlit run app.py --server.headless=false --server.port=$PORTA
