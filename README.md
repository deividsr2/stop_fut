# StopFut ⚽ - Adedonha / Stop do Futebol no AWS Emulator

Projeto completo de **Adedonha do Futebol (StopFut)** inspirado no [StopotS](https://stopots.com/pt), executado localmente utilizando a infraestrutura oficial do **AWS Emulator** (Amazon S3 + Amazon DynamoDB + Python API + Agente Validador Inteligente com VAR).

---

## 🏗️ Arquitetura do Projeto

* **Infraestrutura Cloud Local**: [AWS Emulator Oficial](https://docs.aws.amazon.com/emulator/latest/userguide/getting-started.html) rodando via Docker na porta `9297`.
* **Banco de Dados (DynamoDB)**: Tabela `stopfut_database` com mais de **35.000 registros**:
  * 796 clubes mundiais (Brasileirão Séries A e B, gigantes europeus e sul-americanos).
  * 50.000+ atletas com posições técnicas detalhadas (Laterais, Zagueiros, Goleiros, Volantes, Meias, Centroavantes, Pontas).
  * Histórico de passagens e transferências de carreira entre clubes.
  * Estádios e técnicos mundiais.
* **Agente Validador Inteligente (VAR 3.0)**:
  * Nível 1: Consulta direta no DynamoDB com desnormalização e resolução de apelidos (`PLAYER_ALIASES` e `CLUB_ALIASES`).
  * Nível 2: Busca fuzzy fonética e ortográfica (`difflib`).
  * Nível 3: VAR Online em tempo real via Wikipedia Esportes com **auto-aprendizado** (armazena novos craques automaticamente no DynamoDB).
* **Frontend**: UI temática de futebol estilo StopotS (roleta de sorteio de letras, cronômetro de 60s, botão STOP, modal de avaliação lance a lance do VAR).
* **Storage / Deploy (Amazon S3)**: Bucket `stopfut-web` com *Static Website Hosting* habilitado no AWS Emulator.

---

## 🎮 Categorias Dinâmicas do Jogo

Em cada rodada de 60 segundos, o sistema sorteia **1 letra** e **5 categorias balanceadas**:

1. **Clube / Time de Futebol** (Nacional ou Internacional)
2. **3 Setores / Categorias Variadas**:
   * 🛡️ **Linha Defensiva**: Zagueiros, Laterais Esquerdos e Direitos
   * 🧠 **Meiuca**: Volantes, Meias Centrais e Meias-Atacantes
   * 🎯 **Ataque**: Centroavantes, Pontas e Segundos Atacantes
   * 🧤 **Goleiro / Guarda-Redes**
   * 🔒 **Volante / Cão de Guarda**
   * ⭐ **Craque / Jogador Livre**
   * 🏟️ **Estádio / Arena**
   * 👔 **Técnico / Treinador**
3. **1 Pergunta DESAFIO (Dificuldade Máxima)**:
   * Clube x Posição Específica (ex: *Lateral Esquerdo do São Paulo*, *Atacante do Real Madrid*, *Volante do Corinthians*, *Goleiro do Grêmio*, *Meia do Palmeiras*, etc.)

---

## 🚀 Como Executar em Qualquer Máquina

### Pré-requisitos
* **Python 3.10+**
* **Docker Desktop** (para subir o AWS Emulator)
* **Git**

### Passo a Passo

1. **Clonar o Repositório**:
   ```bash
   git clone https://github.com/deividsr2/stop_fut.git
   cd stop_fut
   ```

2. **Iniciar o Docker Desktop e o AWS Emulator**:
   No Windows (PowerShell):
   ```powershell
   .\start-emulator.ps1
   ```
   Ou via Docker Compose:
   ```bash
   docker compose up -d --build
   ```

3. **Popular o Banco de Dados no DynamoDB** (Executar uma única vez):
   ```bash
   python stop_fut/backend/build_database.py
   python stop_fut/backend/import_global_transfermarkt.py
   ```

4. **Fazer o Deploy do Frontend no Amazon S3 Local**:
   ```bash
   python stop_fut/deploy_s3.py
   ```

5. **Iniciar o Servidor do Jogo**:
   ```bash
   python stop_fut/backend/server.py
   ```
   Acesse no navegador: **http://localhost:8080**

---

## 📂 Estrutura de Diretórios

```
aws_local/
├── docker-compose.yml              # Configuração do container do AWS Emulator
├── Dockerfile                      # Imagem Amazon Linux com aws-emulator RPM
├── start-emulator.ps1              # Inicializador do AWS Emulator
├── env-setup.ps1                   # Exportador de variáveis AWS para terminal
├── test_emulator.py                # Testes automatizados STS, S3, DynamoDB, SQS
├── stop_fut/
│   ├── deploy_s3.py                # Deploy automatizado do frontend no bucket S3
│   ├── backend/
│   │   ├── server.py               # API REST (Round, Categorias, Validação)
│   │   ├── agent_validator.py      # Agente Árbitro / VAR com 3 níveis de validação
│   │   ├── build_database.py       # Base inicial de clubes, estádios e atletas BR
│   │   ├── import_global_transfermarkt.py # Importador global de 50k atletas e transferências
│   │   └── import_transfermarkt.py # Importador complementar
│   └── frontend/
│       ├── index.html              # Interface do jogo estilo StopotS
│       ├── style.css               # Tema estádio de futebol e placar
│       └── app.js                  # Lógica do jogo, sorteio, cronômetro e chamada à API
```

---

## 📜 Licença
Projeto para fins de desenvolvimento, estudos e entretenimento esportivo.
Criado com [Google Antigravity](https://deepmind.google/).
