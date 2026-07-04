import os
import re
import time
import shutil
import asyncio
import subprocess
from pyrogram import Client, filters
from pyrogram.types import Message

# Get credentials from environment
API_ID = 29136894
API_HASH = "88f3d07b70de48ac1fc13866b0c9e562"
BOT_TOKEN = "8097075190:AAHt7EPlitFrj_peJ7yPPZezd7Isk_B3xFk"

if not all([API_ID, API_HASH, BOT_TOKEN]):
    raise ValueError("API_ID, API_HASH, and BOT_TOKEN must be set in environment variables!")

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

async def run_command(cmd: list, timeout: int = 300) -> tuple:
    """Run command with timeout to prevent hanging"""
    try:
        loop = asyncio.get_event_loop()
        res = await loop.run_in_executor(
            None, 
            lambda: subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        )
        return res.returncode, res.stdout, res.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out"
    except Exception as e:
        return -1, "", str(e)

@app.on_message(filters.command("start"))
async def start_cmd(client: Client, message: Message):
    await message.reply_text(
        "👋 **Welcome to Lite ClearKey Downloader Bot**\n\n"
        "Send me a link in the following format:\n"
        "`https://example.com/manifest.mpd*KID:KEY`\n\n"
        "⚠️ Note: Max file size supported is 2GB."
    )

@app.on_message(filters.text & filters.private)
async def process_link(client: Client, message: Message):
    text = message.text.strip()
    
    # Validate format
    if "*" not in text:
        await message.reply_text("❌ Invalid format. Please use: `url*KID:KEY`")
        return
        
    parts = text.split("*", 1)
    if len(parts) != 2:
        await message.reply_text("❌ Invalid format. Only one '*' allowed.")
        return
        
    url, key_pair = parts
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
        kid, key = key_pair.split(":", 1)
        
        # 1. Download encrypted streams using yt-dlp
        await status.edit_text("📥 Downloading encrypted streams...")
        
        video_enc = os.path.join(temp_dir, "video_enc.mp4")
        audio_enc = os.path.join(temp_dir, "audio_enc.m4a")
        
        # Try downloading best video and audio separately
        # Note: For some MPDs, yt-dlp might need specific headers or cookies
        video_cmd = [
            "yt-dlp",
            "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]",
            "--allow-unplayable-formats",
            "--no-playlist",
            "-o", os.path.join(temp_dir, "%(format_id)s.%(ext)s"),
            url
        ]
        
        rc_v, out_v, err_v = await run_command(video_cmd, timeout=600)
        
        # Check what files were downloaded
        downloaded_files = [f for f in os.listdir(temp_dir) if f.endswith(('.mp4', '.m4a', '.webm'))]
        
        if not downloaded_files:
            await status.edit_text("❌ Download failed. yt-dlp could not fetch streams.\nCheck if the URL is accessible.")
            return

        # Identify video and audio files
        video_file = None
        audio_file = None
        
        for f in downloaded_files:
            path = os.path.join(temp_dir, f)
            size = os.path.getsize(path)
            if size < 1024: # Skip tiny files
                continue
            if 'video' in f.lower() or f.endswith('.mp4'):
                video_file = path
            elif 'audio' in f.lower() or f.endswith('.m4a'):
                audio_file = path
        
        # Fallback: If only one file found, treat it as video
        if not video_file and downloaded_files:
            video_file = os.path.join(temp_dir, downloaded_files[0])
            
        if not video_file:
            await status.edit_text("❌ No valid video file found after download.")
            return

        # 2. Decrypt using mp4decrypt
        await status.edit_text("🔑 Decrypting streams...")
        
        video_dec = os.path.join(temp_dir, "video_dec.mp4")
        dec_v_cmd = ["mp4decrypt", "--key", f"{kid}:{key}", video_file, video_dec]
        rc_dv, _, err_dv = await run_command(dec_v_cmd, timeout=300)
        
        if rc_dv != 0 or not os.path.exists(video_dec) or os.path.getsize(video_dec) < 100:
            await status.edit_text(f"❌ Video decryption failed.\nError: {err_dv[:200]}")
            return
            
        final_video = video_dec
        
        # Decrypt audio if available
        if audio_file:
            audio_dec = os.path.join(temp_dir, "audio_dec.m4a")
            dec_a_cmd = ["mp4decrypt", "--key", f"{kid}:{key}", audio_file, audio_dec]
            rc_da, _, _ = await run_command(dec_a_cmd, timeout=300)
            
            if rc_da == 0 and os.path.exists(audio_dec) and os.path.getsize(audio_dec) > 100:
                # 3. Merge decrypted video and audio
                await status.edit_text("🔄 Muxing streams...")
                merged_output = os.path.join(temp_dir, "final_output.mp4")
                mux_cmd = [
                    "ffmpeg", "-y",
                    "-i", video_dec,
                    "-i", audio_dec,
                    "-c", "copy",
                    "-movflags", "+faststart",
                    merged_output
                ]
                rc_m, _, err_m = await run_command(mux_cmd, timeout=300)
                if rc_m == 0 and os.path.exists(merged_output):
                    final_video = merged_output

        # Check file size before upload (Telegram limit: 2GB)
        file_size = os.path.getsize(final_video)
        if file_size > 2 * 1024 * 1024 * 1024:
            await status.edit_text(f"❌ File too large ({format_size(file_size)}). Telegram bot limit is 2GB.")
            return

        # 4. Upload to Telegram
        await status.edit_text("☁️ Uploading to Telegram...")
        
        final_filename = f"Decrypted_{task_id}.mp4"
        final_path = os.path.join(temp_dir, final_filename)
        if final_video != final_path:
            os.rename(final_video, final_path)
        
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
                        f"☁️ **Uploading…**\n"
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
            caption=f"🎥 **Decrypted Output**\n\n• Key: `{key_pair}`",
            supports_streaming=True,
            progress=progress
        )
        await status.delete()
        
    except Exception as e:
        await status.edit_text(f"❌ Error: {str(e)[:500]}")
    finally:
        # Cleanup
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except:
            pass

if __name__ == "__main__":
    app.run()
