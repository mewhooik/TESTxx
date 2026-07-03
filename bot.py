import os
import re
import time
import shutil
import asyncio
import subprocess
from pyrogram import Client, filters
from pyrogram.types import Message

# Get credentials from environment
API_ID = int(os.environ.get("API_ID", "29136894"))
API_HASH = os.environ.get("API_HASH", "88f3d07b70de48ac1fc13866b0c9e562")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8097075190:AAHt7EPlitFrj_peJ7yPPZezd7Isk_B3xFk")

if not API_ID or not API_HASH or not BOT_TOKEN:
    print("WARNING: API_ID, API_HASH, or BOT_TOKEN missing in environment!")

app = Client(
    "clearkey_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

def format_size(bytes_count: float) -> str:
    if not bytes_count:
        return "0 B"
    suffixes = ["B", "KB", "MB", "GB"]
    import math
    i = int(math.floor(math.log(bytes_count, 1024)))
    p = math.pow(1024, i)
    s = round(bytes_count / p, 2)
    return f"{s} {suffixes[i]}"

async def run_command(cmd: list) -> tuple:
    loop = asyncio.get_event_loop()
    res = await loop.run_in_executor(
        None, lambda: subprocess.run(cmd, capture_output=True, text=True)
    )
    return res.returncode, res.stdout, res.stderr

@app.on_message(filters.command("start"))
async def start_cmd(client: Client, message: Message):
    await message.reply_text(
        "👋 Welcome! I am a Lite ClearKey Downloader Bot.\n\n"
        "Send me a link in the following format:\n"
        "`https://example.com/manifest.mpd*KID:KEY`"
    )

@app.on_message(filters.text & filters.private)
async def process_link(client: Client, message: Message):
    text = message.text.strip()
    if "*" not in text:
        await message.reply_text("❌ Invalid format. Please use: `url*KID:KEY`")
        return
        
    url, key_pair = text.split("*", 1)
    url = url.strip()
    key_pair = key_pair.strip()
    
    if ":" not in key_pair:
        await message.reply_text("❌ Key pair must be in `KID:KEY` format.")
        return
        
    status = await message.reply_text("⚡ Processing request...")
    
    # Setup temporary workspace
    task_id = str(int(time.time()))
    temp_dir = os.path.join(os.getcwd(), f"task_{task_id}")
    os.makedirs(temp_dir, exist_ok=True)
    
    try:
        # 1. Download encrypted streams using yt-dlp
        await status.edit_text("📥 Downloading encrypted video & audio streams using yt-dlp...")
        
        # Download best video (encrypted)
        video_enc = os.path.join(temp_dir, "video_enc.mp4")
        video_cmd = [
            "yt-dlp",
            "-f", "bestvideo",
            "--allow-unplayable-formats",
            "-o", video_enc,
            url
        ]
        rc_v, out_v, err_v = await run_command(video_cmd)
        if rc_v != 0 or not os.path.exists(video_enc):
            # Try downloading best single format in case separate video format is not found
            video_cmd_fallback = [
                "yt-dlp",
                "--allow-unplayable-formats",
                "-o", video_enc,
                url
            ]
            await run_command(video_cmd_fallback)
            
        # Download best audio (encrypted)
        audio_enc = os.path.join(temp_dir, "audio_enc.m4a")
        audio_cmd = [
            "yt-dlp",
            "-f", "bestaudio",
            "--allow-unplayable-formats",
            "-o", audio_enc,
            url
        ]
        rc_a, _, _ = await run_command(audio_cmd)
        
        # Determine if we have separate audio/video or just a single file
        has_audio = os.path.exists(audio_enc) and os.path.getsize(audio_enc) > 1024
        
        if not os.path.exists(video_enc):
            await status.edit_text("❌ Download failed. yt-dlp was unable to fetch the streams.")
            return

        # 2. Decrypt using mp4decrypt
        await status.edit_text("🔑 Decrypting streams using mp4decrypt...")
        video_dec = os.path.join(temp_dir, "video_dec.mp4")
        
        # Split key pair to pass to mp4decrypt
        kid, key = key_pair.split(":", 1)
        
        # Decrypt video
        dec_v_cmd = ["mp4decrypt", "--key", f"{kid}:{key}", video_enc, video_dec]
        rc_dv, _, err_dv = await run_command(dec_v_cmd)
        if rc_dv != 0 or not os.path.exists(video_dec) or os.path.getsize(video_dec) < 100:
            await status.edit_text(f"❌ Video decryption failed. Verify KID:KEY.\nError: {err_dv}")
            return
            
        # Decrypt audio if exists
        video_final = video_dec
        if has_audio:
            audio_dec = os.path.join(temp_dir, "audio_dec.m4a")
            dec_a_cmd = ["mp4decrypt", "--key", f"{kid}:{key}", audio_enc, audio_dec]
            rc_da, _, _ = await run_command(dec_a_cmd)
            
            if rc_da == 0 and os.path.exists(audio_dec) and os.path.getsize(audio_dec) > 100:
                # 3. Merge decrypted video and audio using ffmpeg
                await status.edit_text("🔄 Muxing decrypted streams using FFmpeg...")
                merged_output = os.path.join(temp_dir, "final_output.mp4")
                mux_cmd = [
                    "ffmpeg", "-y",
                    "-i", video_dec,
                    "-i", audio_dec,
                    "-c", "copy",
                    merged_output
                ]
                rc_m, _, _ = await run_command(mux_cmd)
                if rc_m == 0 and os.path.exists(merged_output):
                    video_final = merged_output

        # 4. Upload to Telegram
        await status.edit_text("☁️ Uploading final file to Telegram...")
        
        # Calculate size & name
        final_filename = f"Decrypted_Video_{task_id}.mp4"
        final_path = os.path.join(temp_dir, final_filename)
        os.rename(video_final, final_path)
        
        file_size = os.path.getsize(final_path)
        
        start_time = time.time()
        last_update = start_time
        
        async def progress(current, total):
            nonlocal last_update
            now = time.time()
            if now - last_update >= 5.0 or current == total:
                pct = (current / total) * 100 if total else 0.0
                speed = current / (now - start_time) if now - start_time > 0 else 0
                try:
                    await status.edit_text(
                        f"☁️ **Uploading final file…**\n"
                        f"├ ⚡️ Progress: {pct:.1f}%\n"
                        f"├ 📈 Size: {format_size(current)} of {format_size(total)}\n"
                        f"├ 🚀 Speed: {format_size(speed)}/s"
                    )
                except:
                    pass
                last_update = now

        await client.send_video(
            chat_id=message.chat.id,
            video=final_path,
            caption=f"🎥 **Decrypted Stream Output**\n\n• Link: `{url}`\n• Key: `{key_pair}`",
            supports_streaming=True,
            progress=progress
        )
        await status.delete()
        
    except Exception as e:
        await status.edit_text(f"❌ An error occurred: {e}")
    finally:
        # Cleanup
        try:
            shutil.rmtree(temp_dir)
        except:
            pass

if __name__ == "__main__":
    app.run()
