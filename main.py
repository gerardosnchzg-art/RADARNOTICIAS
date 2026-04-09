import os
import asyncio
import httpx
from datetime import datetime
from telegram import Bot
from telegram.ext import Application, CommandHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler

TOKEN = os.environ.get("TELEGRAM_TOKEN", "8723033052:AAFu2ve6UpLT-MJO7Qq3G3sMp8Y_atmV_ZQ")
CHAT_ID = os.environ.get("CHAT_ID", "7360216132")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# Noticias ya enviadas (evitar duplicados)
sent_headlines = set()

async def fetch_news():
    """Llama a Claude con web search para detectar noticias de alto impacto."""
    today = datetime.now().strftime("%A %d de %B de %Y, %H:%M hrs")

    prompt = f"""Hoy es {today}.

Eres un editor de noticias políticas senior. Revisa las últimas noticias de la última hora en México, EEUU (impacto latino), Latinoamérica y el mundo.

Busca SOLO noticias de impacto 4 o 5 sobre 5:
- Decisiones de gobierno que afectan a mucha gente
- Crisis políticas o económicas relevantes  
- Hechos internacionales con impacto en México/Latinoamérica
- Noticias que van a generar mucha conversación hoy

Responde SOLO con JSON sin backticks:

{{
  "hay_urgentes": true,
  "noticias": [
    {{
      "titular": "Titular periodístico máximo 12 palabras",
      "region": "México|EEUU|Latinoamérica|Mundial",
      "impacto": 5,
      "por_que_importa": "Una oración explicando por qué es urgente postear esto"
    }}
  ]
}}

Si no hay noticias de impacto 4-5 en este momento, devuelve: {{"hay_urgentes": false, "noticias": []}}
Solo incluye noticias reales y verificadas de este momento."""

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            res = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_KEY,
                    "anthropic-version": "2023-06-01",
                    "anthropic-beta": "interleaved-thinking-2025-01-30",
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
                    if block.get("type") == "text" and len(block.get("text","").strip()) > 10:
                        raw = block["text"]
                        break

            import json, re
            match = re.search(r'\{[\s\S]*\}', raw)
            if not match:
                return None
            return json.loads(match.group(0))

    except Exception as e:
        print(f"Error fetching news: {e}")
        return None


async def check_and_notify(bot: Bot):
    """Revisa noticias y notifica si hay algo urgente."""
    print(f"[{datetime.now().strftime('%H:%M')}] Revisando noticias...")
    result = await fetch_news()

    if not result or not result.get("hay_urgentes"):
        print("Sin noticias urgentes.")
        return

    nuevas = []
    for n in result.get("noticias", []):
        titular = n.get("titular", "")
        if titular and titular not in sent_headlines:
            nuevas.append(n)
            sent_headlines.add(titular)

    if not nuevas:
        print("Noticias ya enviadas anteriormente.")
        return

    for n in nuevas:
        impacto = n.get("impacto", 4)
        estrellas = "🔴" * impacto
        region_flags = {"México": "🇲🇽", "EEUU": "🇺🇸", "Latinoamérica": "🌎", "Mundial": "🌍"}
        flag = region_flags.get(n.get("region", ""), "🌐")

        msg = (
            f"{estrellas} *NOTICIA DE ALTO IMPACTO*\n\n"
            f"{flag} *{n.get('titular', '')}*\n\n"
            f"📌 _{n.get('por_que_importa', '')}_\n\n"
            f"👉 Abre la herramienta y presiona *Escanear* para generar tu post."
        )

        await bot.send_message(
            chat_id=CHAT_ID,
            text=msg,
            parse_mode="Markdown"
        )
        print(f"Notificación enviada: {n.get('titular')}")
        await asyncio.sleep(1)


async def cmd_start(update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Hola Gerardo\\!* Soy tu Radar de Noticias\\.\n\n"
        "Te voy a avisar en cuanto detecte noticias de alto impacto que valgan la pena postear\\.\n\n"
        "Comandos disponibles:\n"
        "📡 /escanear — Revisar noticias ahora mismo\n"
        "ℹ️ /estado — Ver si el radar está activo",
        parse_mode="MarkdownV2"
    )

async def cmd_escanear(update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Escaneando noticias de alto impacto... un momento.")
    bot = context.bot
    result = await fetch_news()

    if not result or not result.get("hay_urgentes") or not result.get("noticias"):
        await update.message.reply_text("✅ Sin noticias de alto impacto en este momento. Te aviso cuando aparezca algo.")
        return

    for n in result.get("noticias", []):
        impacto = n.get("impacto", 4)
        estrellas = "🔴" * impacto
        region_flags = {"México": "🇲🇽", "EEUU": "🇺🇸", "Latinoamérica": "🌎", "Mundial": "🌍"}
        flag = region_flags.get(n.get("region", ""), "🌐")

        msg = (
            f"{estrellas} *NOTICIA DETECTADA*\n\n"
            f"{flag} *{n.get('titular', '')}*\n\n"
            f"📌 _{n.get('por_que_importa', '')}_\n\n"
            f"👉 Abre la herramienta y presiona *Escanear* para generar tu post."
        )
        await update.message.reply_text(msg, parse_mode="Markdown")
        await asyncio.sleep(0.5)

async def cmd_estado(update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅ *Radar activo*\n"
        "Revisando noticias cada 30 minutos.\n"
        "Solo te aviso cuando el impacto es 4 o 5 sobre 5.",
        parse_mode="Markdown"
    )


async def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("escanear", cmd_escanear))
    app.add_handler(CommandHandler("estado", cmd_estado))

    # Scheduler: revisa cada 30 minutos
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        check_and_notify,
        "interval",
        minutes=30,
        args=[app.bot],
        id="news_check"
    )
    scheduler.start()

    print("🚀 Bot iniciado. Revisando noticias cada 30 minutos...")

    # Enviar mensaje de inicio
    await app.bot.send_message(
        chat_id=CHAT_ID,
        text="🚀 *Radar de Noticias activado\\!*\n\nTe avisaré cuando detecte noticias de alto impacto\\. Usa /escanear para revisar ahora mismo\\.",
        parse_mode="MarkdownV2"
    )

    await app.run_polling(allowed_updates=["message"])


if __name__ == "__main__":
    asyncio.run(main())
