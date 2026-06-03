#!/bin/bash
set -e

echo "🐛 Starting Ollama..."
ollama serve &
OLLAMA_PID=$!

# Wait for Ollama to be ready
echo "⏳ Waiting for Ollama to be ready..."
until curl -s http://localhost:11434/api/tags > /dev/null 2>&1; do
    sleep 1
done
echo "✅ Ollama is ready."

# Pull model if not already cached
if ! ollama list | grep -q "llama3.2"; then
    echo "📦 Downloading llama3.2 model (this only happens once)..."
    ollama pull llama3.2
    echo "✅ Model downloaded."
else
    echo "✅ Model already cached, skipping download."
fi

echo "🌐 Starting Bug Game on port 5000..."
exec python app.py