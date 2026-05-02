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
    prompt = f"""Hoy es {today}. Usa la herramienta de busqueda web para encontrar noticias REALES publicadas HOY.

Busca: noticias Queretaro hoy y noticias Mexico hoy y revisa los resultados.

Selecciona solo noticias de impacto 4 o 5 sobre 5 publicadas en las ultimas 24 horas:
1. QUERETARO: politica estatal, seguridad, obras, economia local
2. NACIONAL: que afecten a Queretaro o sean muy importantes
3. INTERNACIONAL: solo impacto maximo 5/5

IMPORTANTE: Solo incluye noticias que encontraste en la busqueda web, no de tu conocimiento previo.

Responde SOLO con JSON sin backticks:
{{"hay_urgentes": true, "noticias": [{{"titular": "Titular maximo 12 palabras", "region": "Queretaro|Nacional|Internacional", "impacto": 5, "por_que_importa": "Por que es urgente postear esto"}}]}}

Si no encuentras noticias relevantes de hoy: {{"hay_urgentes": false, "noticias": []}}"""

    try:
        async with httpx.AsyncClient(timeout=90) as client:
            res = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_KEY,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 2000,
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
    region_flags = {"Queretaro": "📍", "Nacional": "🇲🇽", "Internacional": "🌍"}
    for n in noticias:
        titular = n.get("titular", "")
        if titular in sent_headlines:
            continue
        sent_headlines.add(titular)
        impacto = n.get("impacto", 4)
        flag = region_flags.get(n.get("region", ""), "🌐")
        msg = (
            f"{'🔴' * impacto} NOTICIA DE ALTO IMPACTO\n\n"
            f"{flag} {titular}\n\n"
            f"📌 {n.get('por_que_importa', '')}\n\n"
            f"👉 Abre la herramienta y presiona Escanear para generar tu post."
        )
        await bot.send_message(chat_id=CHAT_ID, text=msg)
        await asyncio.sleep(1)


async def check_and_notify(bot: Bot):
    print(f"[{datetime.now().strftime('%H:%M')}] Revisando noticias...")
    result = await fetch_news()
    if not result or not result.get("hay_urgentes"):
        print("Sin noticias urgentes.")
        return
    nuevas = [n for n in result.get("noticias", []) if n.get("titular") not in sent_headlines]
    if nuevas:
        await send_news(bot, nuevas)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hola Gerardo! Soy tu Radar de Noticias de Queretaro.\n\n"
        "Comandos:\n"
        "/escanear - Buscar noticias ahora\n"
        "/estado - Ver si el radar esta activo"
    )

async def cmd_escanear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Buscando noticias en tiempo real... esto tarda unos segundos.")
    result = await fetch_news()
    if not result or not result.get("hay_urgentes") or not result.get("noticias"):
        await update.message.reply_text("Sin noticias de alto impacto en este momento.")
        return
    await send_news(context.bot, result.get("noticias", []))

async def cmd_estado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    await update.message.reply_text(
        f"Radar activo - {now}\n"
        "Revisando cada 30 minutos con busqueda web en tiempo real."
    )

async def post_init(app: Application):
    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_and_notify, "interval", minutes=30, args=[app.bot], id="news_check")
    scheduler.start()
    print("Scheduler iniciado.")
    await app.bot.send_message(
        chat_id=CHAT_ID,
        text=f"Radar reiniciado ({datetime.now().strftime('%d/%m/%Y %H:%M')}). Ahora busca noticias en tiempo real. Usa /escanear para probar."
    )

def main():
    app = Application.builder().token(TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("escanear", cmd_escanear))
    app.add_handler(CommandHandler("estado", cmd_estado))
    print("Bot iniciado...")
    app.run_polling(allowed_updates=["message"])

if __name__ == "__main__":
    main()
