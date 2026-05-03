# Deployment Guide

Deploy the English Practice bot on a VPS with Docker.

## Prerequisites

- A VPS (Ubuntu/Debian recommended, ~$5/mo is enough)
- Docker and Docker Compose installed
- Telegram bot token from [@BotFather](https://t.me/BotFather)
- `data/seed.db` file (generated locally with `uv run scripts/database/populate.py`)

## Quick Start

```bash
# 1. Copy seed database from your LOCAL machine
scp ./data/seed.db root@45.129.186.187:/opt/english-practice/data/production.db

# 2. SSH into the VPS and set up
ssh root@45.129.186.187
git clone <your-repo-url> /opt/english-practice
cd /opt/english-practice

# 3. Create directories and configure
mkdir -p data logs
cp .env.example .env
nano .env

# 4. Start the bot
docker compose up -d

# 5. Check logs
docker compose logs -f
```

## Setup

### 1. Server Preparation

```bash
# Update system
sudo apt update && sudo apt upgrade -y && sudo apt autoremove -y

# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# Log out and back in

# Install Docker Compose plugin
sudo apt-get install -y docker-compose-plugin
```

### 2. Copy Seed Database

Run this on your **local** machine:

```bash
scp ./data/seed.db root@45.129.186.187:/opt/english-practice/data/production.db
```

### 3. Clone and Configure

```bash
git clone <your-repo-url> /opt/english-practice
cd /opt/english-practice

# Create directories for persistent data
mkdir -p data logs

# Configure environment
cp .env.example .env
nano .env
```

### Required Environment Variables

| Variable                 | Description                              | Required |
| ------------------------ | ---------------------------------------- | -------- |
| `TELEGRAM_BOT_TOKEN`     | Token from @BotFather                    | Yes      |
| `TELEGRAM_ADMIN_USER_ID` | Your Telegram user ID                    | Yes      |
| `LLM__PROVIDER`          | LLM provider (dashscope/gemini/openrouter) | Yes      |
| `OPENROUTER_API_KEY`     | OpenRouter API key                       | Yes*     |
| `ENVIRONMENT`            | Set to `production`                      | Yes      |
| `DATABASE_PATH`          | Path to SQLite database                  | Yes      |

*\*Required for your chosen provider — use `DASHSCOPE_API_KEY` or `GEMINI_API_KEY` instead if using those providers.*

### 4. Start the Bot

```bash
docker compose up -d
```

## Updates

```bash
cd /opt/english-practice
git pull
docker compose build --no-cache
docker compose up -d
```

## Manage

```bash
# View logs
docker compose logs -f

# Stop
docker compose down

# Restart
docker compose restart

# Rebuild and restart after code changes
docker compose build && docker compose up -d
```
