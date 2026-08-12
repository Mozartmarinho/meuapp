# Control iD — São Geraldo Acesso

## Configuração

Credenciais por equipamento (Hub de Equipamentos):
- **IP**, **Usuário do dispositivo** (padrão `admin`), **Senha do dispositivo**
- Botão **Puxar Device ID** (login + `system_information` / resposta do login)

Variáveis de ambiente (opcionais):

| Variável | Padrão | Uso |
|----------|--------|-----|
| `CONTROLID_DEFAULT_USER` | `admin` | Login se `usuario_disp` vazio |
| `CONTROLID_DEFAULT_PASSWORD` | `admin` | Senha se `senha_disp` vazia |
| `CONTROLID_SERVER_HOST` | host da requisição | IP/hostname anunciado aos devices (monitor) |
| `CONTROLID_SERVER_PORT` | `PORT` ou `80` | Porta do servidor São Geraldo |
| `CONTROLID_MONITOR_PATH` | `acesso/controlid/notifications` | Path do monitor no device |
| `CONTROLID_TIMEOUT` | `12` | Timeout HTTP (s) |
| `CONTROLID_SESSION_TTL` | `480` | Cache de sessão (s) |

Fluxo **Configurar Servidor** grava no device:

```json
POST /set_configuration.fcgi
{ "monitor": { "hostname": "...", "port": "...", "path": "acesso/controlid/notifications", ... } }
```

Callbacks recebidos (sem login de usuário web):

- `POST /acesso/controlid/notifications/device_is_alive`
- `POST /acesso/controlid/notifications/dao` (insere `access_logs` em `acesso_eventos`)
- `door` / `secbox` / `catra_event` / `operation_mode` (atualizam `online`/`last_alive`)

O firewall/rede deve permitir que o **device** alcance o servidor São Geraldo nesses paths.

## Implementado (núcleo)

- Cliente `controlid_client.py`: login, session cache, `set_system_time`, monitor, `load_objects` (access_logs), push user/card/foto, probe, puxar device_id
- Hub Equipamentos: CRUD + senha/usuário + testar conexão + configurar servidor + data/hora + reiniciar conexão + puxar ID
- Sincronizar Offline: coleta real de `access_logs`
- Operações: envio real de pessoas (users + cartão + foto JPEG)

## Gaps restantes (parity Sollus)

1. **Modo online Enterprise** (`new_user_identified` com grant/deny no servidor) — lógica em `.pyd` Sollus; aqui o monitor é standalone (device decide, servidor recebe eventos).
2. **Access rules / horários / grupos → device** (`user_access_rules`, regras de giro avançadas).
3. **Biometrias digitais** (templates) — UI ainda tem flag, backend não envia.
4. **QR codes** no push (campo existe em pessoa; create_objects qrcodes ainda não ligado na Operações).
5. **Backup fotos/digitais do device → local** (Operações Sollus).
6. **Explorar/remover users no device** (tela Operações Sollus).
7. **Status das Portas / liberar porta** (`doors_state` / `execute_actions` — helper existe, UI/rota dedicada não).
8. **iDBlock giros** (`access_events` catra + reconciliação).
9. **Henry / Evo** (outros fabricantes no Sollus).
10. **Limpeza remota no device** ainda parcial (banco local ok; destroy no device stub).
11. Mapa `eventos_origem_map` do Sollus (dedupe por id offline) — hoje dedupe por pessoa+data+status+direction.

## Teste rápido

1. Cadastre IP + senha do iDFace no Hub.
2. **Testar Conexão** → deve marcar online e preencher device_id se o login retornar.
3. **Atualizar Data/Hora** / **Configurar Servidor** (use o IP LAN do servidor São Geraldo).
4. **Sincronizar Offline** → coletar no intervalo desejado.
5. **Operações** → selecionar pessoas → Enviar para equipamentos.
