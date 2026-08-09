# Agente de Pesagem (Windows)

Lê o peso da balança pela porta serial (ex.: **FT232R USB UART** → COMx) e envia para o servidor.

## Uso rápido

1. Edite `config.json`:
   - `servidor_url`: URL do servidor (ex. `http://192.168.0.125` ou `http://127.0.0.1`)
   - `api_key`: mesma chave do servidor (`saogeraldo-pesagem-2025`)
   - `porta_com`: `AUTO` ou `COM3`, `COM4`, etc.
   - `baudrate`: geralmente `9600`
   - `modo_simulacao`: `true` para testar sem balança

2. Gere o `.exe`:
   ```bat
   build_exe.bat
   ```
   Saída: `dist\AgentePesagem.exe` + `config.json`

3. No PC da balança, rode `AgentePesagem.exe` (mantenha `config.json` na mesma pasta).

## Teste sem balança

No `config.json` defina `"modo_simulacao": true` e execute:

```bat
..\..\.venv\Scripts\python.exe agente_pesagem.py
```

(ou o `.exe` gerado)

## Endpoint

`POST /api/pesagem/leituras` com header `X-API-Key`.
