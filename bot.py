"""
Staff Target Bot — Funderland Group
------------------------------------
What it does, per venue group, every day:

  08:00  -> posts an empty target template for each staff member
  13:00  -> posts an empty target template for each staff member (afternoon set)
  17:00  -> replies to each morning template reminding staff to edit it
             with real results + a reference photo
  22:00  -> replies to each afternoon template with the same reminder

Telegram bots CANNOT edit a message that a human sent, so the 17:00/22:00
step is a REPLY reminder (tagging the staff member), not an auto-edit.
Staff still do the actual editing themselves in the app (long-press their
own message -> Edit).

SETUP
-----
1. pip install python-telegram-bot==21.4
2. Create a bot via @BotFather on Telegram, copy the token.
3. Add the bot to all 5 group chats as an admin (needs "Delete/Pin/Post"
   is not required, but it must be able to send messages).
4. Get each group's chat_id: add the bot, send any message in the group,
   then check https://api.telegram.org/bot<TOKEN>/getUpdates — the
   "chat":{"id": -100xxxxxxxxxx} value is what goes in config.json.
5. Fill in config.json with real chat_id values and real staff names.
6. Set the BOT_TOKEN environment variable (do not hardcode it in this file).
7. Run:  python bot.py
   Keep it running 24/7 (a small VPS, or a free host like Railway/Render).
"""

import json
import os
import logging
from datetime import time as dtime, date
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import Application, ContextTypes, CommandHandler

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO
)
log = logging.getLogger("staff_target_bot")

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
STATE_PATH = os.path.join(os.path.dirname(__file__), "state.json")
BOT_TOKEN = os.environ.get("BOT_TOKEN")

TEMPLATE = (
    "📋 របាយការណ៍គោលដៅប្រចាំថ្ងៃ — {date}\n"
    "{mentions}\n\n"
    "គ្រប់គ្នាសូមប្រកាសរបាយការណ៍ផ្ទាល់ខ្លួនរបស់អ្នកខាងក្រោម ដោយប្រើគំរូនេះ៖\n\n"
    "-ថ្ងៃទី: {date}\n"
    "-ឈ្មោះបុគ្គលិក: \n"
    "-សម្អាត: \n"
    "-បណ្ដុះបណ្ដាល: \n"
    "-លក់បន្ថែម: \n"
    "-មតិអតិថិជន: \n"
    "-តាមដាន: \n"
    "ចំណាំ៖ សូមចែករំលែកបញ្ជីតាមដានរបស់អ្នក ហើយធ្វើបច្ចុប្បន្នភាពដោយប្រើស្ថានភាព emoji ទាំងនេះ៖\n"
    "🔄 កំពុងដំណើរការ\n"
    "⏳ កំពុងរង់ចាំ\n"
    "✅ បានបញ្ចប់"
)

REMINDER = (
    "⏰ {mentions}\n"
    "សូមកែសម្រួលរបាយការណ៍គោលដៅរបស់អ្នកខាងលើ ដោយបញ្ចូលលទ្ធផលជាក់ស្តែងថ្ងៃនេះ "
    "ព្រមទាំងភ្ជាប់រូបភាពយោង 📸 ជាភស្តុតាង។"
)


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_state(state):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def today_str(tz):
    return date.today().strftime("%d,%m,%Y")


def mention_list(staff_list):
    """Builds a space-separated mention string. Staff with a telegram
    username get a real clickable/notifying @mention; staff without one
    just get their plain name listed."""
    parts = []
    for s in staff_list:
        if s.get("username"):
            parts.append(f"@{s['username']}")
        else:
            parts.append(s["name"])
    return " ".join(parts)


async def post_templates(context: ContextTypes.DEFAULT_TYPE, slot: str):
    """slot = 'morning' or 'afternoon'. Posts ONE template message per venue
    that mentions/tags every staff member in that group."""
    config = load_config()
    state = load_state()
    tz = ZoneInfo(config["timezone"])
    d = today_str(tz)

    for venue, info in config["venues"].items():
        chat_id = info["chat_id"]
        mentions = mention_list(info["staff"])
        text = TEMPLATE.format(date=d, mentions=mentions)
        try:
            msg = await context.bot.send_message(chat_id=chat_id, text=text)
            key = f"{d}_{slot}_{venue}"
            state[key] = {"chat_id": chat_id, "message_id": msg.message_id}
            log.info(f"Posted {slot} template for {venue}")
        except Exception as e:
            log.error(f"Failed to post {slot} template for {venue}: {e}")

    save_state(state)


async def send_reminders(context: ContextTypes.DEFAULT_TYPE, slot: str):
    """slot = 'morning' or 'afternoon' — which template to remind against.
    Sends ONE reminder per venue, replying to that venue's template and
    tagging every staff member again."""
    config = load_config()
    state = load_state()
    tz = ZoneInfo(config["timezone"])
    d = today_str(tz)

    for venue, info in config["venues"].items():
        key = f"{d}_{slot}_{venue}"
        entry = state.get(key)
        mentions = mention_list(info["staff"])
        text = REMINDER.format(mentions=mentions)
        try:
            if entry:
                await context.bot.send_message(
                    chat_id=entry["chat_id"],
                    text=text,
                    reply_to_message_id=entry["message_id"],
                )
            else:
                await context.bot.send_message(chat_id=info["chat_id"], text=text)
            log.info(f"Sent {slot} reminder for {venue}")
        except Exception as e:
            log.error(f"Failed reminder for {venue}: {e}")


# ---- Scheduled job wrappers ----

async def job_morning_post(context: ContextTypes.DEFAULT_TYPE):
    await post_templates(context, "morning")


async def job_afternoon_post(context: ContextTypes.DEFAULT_TYPE):
    await post_templates(context, "afternoon")


async def job_evening_reminder(context: ContextTypes.DEFAULT_TYPE):
    await send_reminders(context, "morning")


async def job_night_reminder(context: ContextTypes.DEFAULT_TYPE):
    await send_reminders(context, "afternoon")


# ---- Manual trigger commands (useful for testing without waiting for the clock) ----

async def cmd_test_morning(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await post_templates(context, "morning")
    await update.message.reply_text("Morning templates posted.")


async def cmd_test_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_reminders(context, "morning")
    await update.message.reply_text("Reminders sent.")


def parse_hhmm(s: str) -> dtime:
    h, m = s.split(":")
    return dtime(hour=int(h), minute=int(m))


def main():
    if not BOT_TOKEN:
        raise RuntimeError("Set the BOT_TOKEN environment variable before running.")

    config = load_config()
    tz = ZoneInfo(config["timezone"])
    sched = config["schedule"]

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("test_morning", cmd_test_morning))
    app.add_handler(CommandHandler("test_reminder", cmd_test_reminder))

    jq = app.job_queue
    jq.run_daily(job_morning_post, time=parse_hhmm(sched["morning_post"]).replace(tzinfo=tz))
    jq.run_daily(job_afternoon_post, time=parse_hhmm(sched["afternoon_post"]).replace(tzinfo=tz))
    jq.run_daily(job_evening_reminder, time=parse_hhmm(sched["evening_reminder"]).replace(tzinfo=tz))
    jq.run_daily(job_night_reminder, time=parse_hhmm(sched["night_reminder"]).replace(tzinfo=tz))

    log.info("Staff Target Bot started. Waiting for scheduled jobs...")
    app.run_polling()


if __name__ == "__main__":
    main()
