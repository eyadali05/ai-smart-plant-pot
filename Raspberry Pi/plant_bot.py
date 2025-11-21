#!/usr/bin/env python3
import os
import serial
import time
import asyncio
import subprocess
from datetime import datetime
from pathlib import Path
import numpy as np
from PIL import Image
import tensorflow as tf
from tensorflow.lite.python.interpreter import Interpreter
from telegram import Update, InputFile
from telegram.ext import Application, CommandHandler, ContextTypes

# ============================================================
# CONFIG
# ============================================================
TOKEN = ":)"
BASE = Path("your own dir/plantbot")
MODEL_PATH = BASE / "plant_classifier_fp16.tflite"
LABELS_PATH = BASE / "labels.txt"
PHOTOS_DIR = BASE / "photos"
PHOTOS_DIR.mkdir(exist_ok=True)

IMG_SIZE = 224
SERIAL_PORT = "your arduino's serial port"
BAUD = 115200
# ============================================================

# ------------------------------------------------------------
# Arduino Serial Setup
# ------------------------------------------------------------
ser = None
try:
    ser = serial.Serial(SERIAL_PORT, BAUD, timeout=2)
    print(f"✅ Connected to Arduino at {SERIAL_PORT}")
    time.sleep(2)
except Exception as e:
    print(f"⚠️ Arduino not connected: {e}")

# ------------------------------------------------------------
# Load Labels
# ------------------------------------------------------------
classes = [ln.strip() for ln in open(LABELS_PATH) if ln.strip()]
print(f"✅ Loaded {len(classes)} classes")

# ------------------------------------------------------------
# Capture photo safely
# ------------------------------------------------------------
def capture_photo() -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_path = PHOTOS_DIR / f"raw_{timestamp}.jpg"
    resized_path = PHOTOS_DIR / f"plant_{timestamp}_224.jpg"

    cmd = [
        "rpicam-still",
        "-o", str(raw_path),
        "--width", "1296",
        "--height", "972",
        "--awb", "auto",
        "--brightness", "0.55",
        "--contrast", "1.0",
        "--saturation", "1.0",
        "--timeout", "2500",
        "--nopreview"
    ]
    print(f"📸 Capturing to {raw_path}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        raise RuntimeError("Camera capture failed (timeout or hardware issue)")

    img = Image.open(raw_path).convert("RGB").resize((IMG_SIZE, IMG_SIZE))
    img.save(resized_path)
    raw_path.unlink(missing_ok=True)
    print(f"✅ Saved resized image: {resized_path}")
    return resized_path

# ------------------------------------------------------------
# Classify image
# ------------------------------------------------------------
def classify_image(path: Path):
    print(f"🔍 Classifying {path}")
    img = Image.open(path).convert("RGB").resize((IMG_SIZE, IMG_SIZE))
    arr = np.array(img)

    interpreter = Interpreter(model_path=str(MODEL_PATH))
    interpreter.allocate_tensors()
    in_det = interpreter.get_input_details()[0]
    out_det = interpreter.get_output_details()[0]
    dtype = in_det["dtype"]
    print(f"📊 Model input dtype: {dtype}")

    if dtype == np.uint8:
        arr = np.expand_dims(arr.astype(np.uint8), 0)
    else:
        arr = np.expand_dims(arr.astype(np.float32), 0)
        from tensorflow.keras.applications.mobilenet_v3 import preprocess_input
        arr = preprocess_input(arr)

    interpreter.set_tensor(in_det["index"], arr)
    interpreter.invoke()
    out = interpreter.get_tensor(out_det["index"])[0]

    top_idx = np.argsort(out)[-3:][::-1]
    preds = [(classes[i], float(out[i])) for i in top_idx]

    print("✅ Predictions:")
    for n, p in preds:
        print(f"  - {n}: {p*100:.2f}%")
    return preds

# ------------------------------------------------------------
# Escape for Telegram MarkdownV2
# ------------------------------------------------------------
def esc(t: str) -> str:
    for ch in r"_*[]()~`>#+-=|{}.!%":
        t = t.replace(ch, "\\" + ch)
    return t

# ============================================================
# Telegram Command Handlers
# ============================================================

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = "🌿 *Welcome to PlantBot\\!*\\nUse /scan to identify your plant 🌱\\nUse /status to check sensor readings\\nUse /water to manually water the plant 💧"
    await update.message.reply_text(text, parse_mode="MarkdownV2")


async def scan(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.reply_text("📸 Capturing image, please wait...")
        photo_path = capture_photo()
        preds = classify_image(photo_path)

        caption = "🔍 *Top 3 predictions:*\n"
        for n, p in preds:
            caption += f"• {esc(n)} — {esc(f'{p*100:.2f}%')}\n"
        caption += f"\n🌱 *Most likely:* {esc(preds[0][0])}"

        with open(photo_path, "rb") as f:
            await update.message.reply_photo(photo=InputFile(f), caption=caption, parse_mode="MarkdownV2")

    except RuntimeError as e:
        await update.message.reply_text(f"❌ Camera error: {e}")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {e}")

# ------------------------------------------------------------
# /status command
# ------------------------------------------------------------
async def status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ser or not ser.is_open:
        await update.message.reply_text("⚠️ Arduino not connected.")
        return

    ser.reset_input_buffer()
    ser.write(b"STATUS\n")
    await update.message.reply_text("📟 Requesting plant status...")

    await asyncio.sleep(1)
    reply = ser.read_all().decode(errors="ignore").strip()
    if not reply:
        reply = "⚠️ No response from Arduino."
    await update.message.reply_text(f"📊 {reply}")

# ------------------------------------------------------------
# /water command
# ------------------------------------------------------------
async def water(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ser or not ser.is_open:
        await update.message.reply_text("⚠️ Arduino not connected.")
        return

    ser.reset_input_buffer()
    ser.write(b"PUMP\n")
    await update.message.reply_text("💧 Watering started...")

    await asyncio.sleep(4)
    reply = ser.read_all().decode(errors="ignore").strip()

    if "ACK:PUMP_DONE" in reply:
        await update.message.reply_text("✅ Watering complete!")
    elif reply:
        await update.message.reply_text(f"📟 {reply}")
    else:
        await update.message.reply_text("✅ Done (no serial response).")

# ------------------------------------------------------------
# Main entry
# ------------------------------------------------------------
def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("scan", scan))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("water", water))
    print("🤖 PlantBot is running... use /scan, /status, /water in Telegram")
    app.run_polling()

if __name__ == "__main__":
    main()
