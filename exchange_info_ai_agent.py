import sys
import os
import asyncio

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from telethon import TelegramClient

from utils.google_sheet_reader import fetch_channels_from_google_sheet
from utils.telegram_reader import extract_channel_username, fetch_latest_messages
from utils.ai_translator import translate_text_gemini
from utils.telegram_sender import send_telegram_message_html, send_photo_to_telegram_channel
from utils.json_writer import save_results, load_posted_messages


async def main():
    telegram_api_id = os.environ['TELEGRAM_API_ID']
    telegram_api_hash = os.environ['TELEGRAM_API_HASH']
    sheet_id = os.environ['GOOGLE_SHEET_ID']
    google_sheet_api_key = os.environ['GOOGLE_SHEET_API_KEY']

    posted_messages = load_posted_messages()
    result_output = []

    channels_data = fetch_channels_from_google_sheet(sheet_id, google_sheet_api_key)

    for entry in channels_data:
        channel_username = extract_channel_username(entry["channel_link"])
        print(f"\n📡 Processing channel: {channel_username} (Exchange: {entry.get('exchange_name')})")

        messages = await fetch_latest_messages(
            telegram_api_id,
            telegram_api_hash,
            channel_username
        )

        for msg in messages:
            original_text = msg["text"] or ""

            # Skip kalau dah pernah post text yang sama
            if original_text in posted_messages:
                print(f"⚠️ Skipping duplicate message ID {msg['id']} from {channel_username}")
                continue

            # ========== TRANSLATE + DEBUG ========== #
            print("\n=== DEBUG TELEGRAM MESSAGE ===")
            print("CHANNEL      :", channel_username)
            print("EXCHANGE     :", entry.get("exchange_name"))
            print("MESSAGE ID   :", msg["id"])
            print("ORIGINAL TEXT:", repr(original_text[:300]))
            print("LEN ORIGINAL :", len(original_text))

            try:
                translated = translate_text_gemini(original_text)
            except Exception as e:
                print(f"❌ translate_text_gemini error: {e}")
                translated = ""

            print("TRANSLATED   :", repr((translated or "")[:300]))
            print("LEN TRANS    :", len(translated or ""))
            print("================================\n")

            # 👉 GUARD PENTING:
            # Jangan hantar apa-apa kalau translation kosong
            if not translated or not translated.strip():
                print("❌ Translated text kosong (mungkin quota habis / error) – SKIP SEND untuk message ini.")
                result_output.append({
                    "exchange_name": entry["exchange_name"],
                    "channel_link": entry["channel_link"],
                    "original_text": original_text,
                    "translated_text": translated,
                    "referral_link": entry["referral_link"],
                    "date": msg["date"],
                    "message_id": msg["id"],
                    "note": "SKIPPED_EMPTY_TRANSLATION_OR_QUOTA",
                })
                continue
            # ========== END GUARD ========== #

            if msg["has_photo"]:
                image_path = f"photo_{msg['id']}.jpg"

                # Download photo dari source channel
                async with TelegramClient("telegram_session", telegram_api_id, telegram_api_hash) as client:
                    await client.download_media(msg["raw"], image_path)

                # Hantar photo + caption terjemahan
                send_photo_to_telegram_channel(
                    image_path,
                    translated,
                    exchange_name=entry["exchange_name"],
                    referral_link=entry["referral_link"]
                )

                # Buang file temp
                os.remove(image_path)
            else:
                # Hantar text-only message
                send_telegram_message_html(
                    translated_text=translated,
                    exchange_name=entry["exchange_name"],
                    referral_link=entry["referral_link"]
                )

            # Log apa yang betul-betul dipost
            result_output.append({
                "exchange_name": entry["exchange_name"],
                "channel_link": entry["channel_link"],
                "original_text": original_text,
                "translated_text": translated,
                "referral_link": entry["referral_link"],
                "date": msg["date"],
                "message_id": msg["id"],
            })

    if result_output:
        save_results(result_output)


if __name__ == "__main__":
    asyncio.run(main())
