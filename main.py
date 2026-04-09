import os
import asyncio
import httpx
import json
import re
from datetime import datetime
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler

TOKEN = os.environ.get("TELEGRAM_TOKEN", "8723033052:AAFu2ve6UpLT-MJO7Qq3G3sMp8Y_atmV_ZQ")
CHAT_ID = os.environ.get("CHAT_ID", "7360216132")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

sent_headlines = set()

async def fetch_news():
    today = datetime.now().strftime("%A %d de %B de %Y, %H:%M hrs")
    prompt = f"""Hoy es {today}.

Eres el editor de una página de noticias de Instagram enfocada en Querétaro, México. Tu trabajo es detectar las noticias más relevantes e impactantes para publicar.

PRIORIDAD DE NOTICIAS:
1. QUERÉTARO (prioridad máxima): política estatal, seguridad, obras públicas, economía local, gobierno municipal, sucesos importantes en el estado
2. NACIONAL: noticias de México que afecten directamente a Querétaro o sean de impacto muy alto (4-5/5)
3. INTERNACIONAL: solo si el impacto es máximo (5/5) y relevante para la audiencia queretana

Busca noticias de las últimas horas. Solo incluye noticias con impacto 4 o 5 sobre 5.

Responde SOLO con JSON sin backticks:
{{
  "hay_urgentes": true,
  "noticias": [
    {{
      "titular": "Titular periodístico máximo 12 palabras",
      "region": "Querétaro|Nacional|Internacional",
      "categoria": "Política|Seguridad|Economía|Obras|Sociedad|Internacional",
      "impacto": 5,
      "por_que_importa": "Una oración explicando por qué es importante para los queretanos"
    }}
  ]
}}

Si no hay noticias de impacto 4-5, devuelve: {{"hay_urgentes": false, "noticias": []}}"""

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            res = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_KEY,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 1000,
                    "tools": [{"type": "web_search_20250305", "name": "web_search"}],
                    "messages": [{"role": "user", "content": prompt}]
                }
            )
            data = res.json()
            raw = ""
            if data.get("content"):
                for block in reversed(data["content"]):
                    if block.get("type") == "text" and len(block.get("text", "").strip()) > 10:
                        raw = block["text"]
                        break
            match = re.search(r'\{[\s\S]*\}', raw)
            if not match:
                return None
            return json.loads(match.group(0))
    except Exception as e:
        print(f"Error: {e}")
        return None


async def send_news(bot: Bot, noticias: list):
    region_flags = {"Querétaro": "🔵⚪", "Nacional": "🇲🇽", "Internacional": "🌍"}
    region_icons = {"Querétaro": "📍", "Nacional": "🇲🇽", "Internacional": "🌐"}
    for n in noticias:
        titular = n.get("titular", "")
        if titular in sent_headlines:
            continue
        sent_headlines.add(titular)
        impacto = n.get("impacto", 4)
        region = n.get("region", "")
        icon = region_icons.get(region, "📌")
        estrellas = "🔴" * impacto
        msg = (
            f"{estrellas} NOTICIA DE ALTO IMPACTO\n\n"
            f"{icon} [{region}] {titular}\n\n"
            f"📌 {n.get('por_que_importa', '')}\n\n"
            f"👉 Abre la herramienta y presiona Escanear para generar tu post."
        )
        await bot.send_message(chat_id=CHAT_ID, text=msg)
        await asyncio.sleep(1)


async def check_and_notify(bot: Bot):
    print(f"[{datetime.now().strftime('%H:%M')}] Revisando noticias de Querétaro...")
    result = await fetch_news()
    if not result or not result.get("hay_urgentes"):
        print("Sin noticias urgentes.")
        return
    nuevas = [n for n in result.get("noticias", []) if n.get("titular") not in sent_headlines]
    if nuevas:
        await send_news(bot, nuevas)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Hola Gerardo! Soy tu Radar de Noticias de Querétaro.\n\n"
        "Monitoreo noticias de:\n"
        "📍 Querétaro (prioridad)\n"
        "🇲🇽 Nacional (cuando afecta a Qro)\n"
        "🌍 Internacional (solo impacto máximo)\n\n"
        "Comandos:\n"
        "📡 /escanear — Revisar noticias ahora\n"
        "ℹ️ /estado — Ver si el radar está activo"
    )


async def cmd_escanear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Buscando noticias de alto impacto para Querétaro...")
    result = await fetch_news()
    if not result or not result.get("hay_urgentes") or not result.get("noticias"):
        await update.message.reply_text("✅ Sin noticias de alto impacto en este momento.")
        return
    await send_news(context.bot, result.get("noticias", []))


async def cmd_estado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅ Radar activo — Enfoque: Querétaro\n"
        "Revisando noticias cada 30 minutos.\n"
        "Te aviso cuando el impacto es 4 o 5 sobre 5."
    )


async def post_init(app: Application):
    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_and_notify, "interval", minutes=30, args=[app.bot], id="news_check")
    scheduler.start()
    print("🚀 Scheduler iniciado — Enfoque Querétaro.")
    await app.bot.send_message(
        chat_id=CHAT_ID,
        text="📍 Radar de Noticias Querétaro activado!\n\nMonitoreando noticias locales, nacionales e internacionales con enfoque en Querétaro. Usa /escanear para revisar ahora mismo."
    )


def main():
    app = Application.builder().token(TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("escanear", cmd_escanear))
    app.add_handler(CommandHandler("estado", cmd_estado))
    print("🤖 Bot Querétaro iniciado...")
    app.run_polling(allowed_updates=["message"])


if __name__ == "__main__":
    main()
