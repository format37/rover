### Ollama configuration
To access from net:
```
sudo systemctl edit --full ollama.service
```
Add:
```
[Service]
Environment=OLLAMA_HOST=0.0.0.0
```
Save and restart
```
sudo systemctl daemon-reload
sudo systemctl restart ollama.service
```
