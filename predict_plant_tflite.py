import argparse
import numpy as np
import tensorflow as tf
from PIL import Image, ImageEnhance

# --------------------------------------------------------
# 🔧 Argument parser
# --------------------------------------------------------
parser = argparse.ArgumentParser(description="Plant species classifier (TFLite)")
parser.add_argument("--model", type=str, required=True, help="Path to .tflite model file")
parser.add_argument("--image", type=str, required=True, help="Path to input image")
parser.add_argument("--labels", type=str, default="models/labels.txt", help="Path to labels.txt file")
parser.add_argument("--prefer", type=str, default=None, help="Optional class name to boost confidence for (e.g. 'kalanchoe')")
parser.add_argument("--boost", type=float, default=0.25, help="Boost factor for the preferred class (e.g. 0.25 = +25%)")
parser.add_argument("--temp", type=float, default=1.0, help="Temperature scaling for output smoothing (0.7–1.5 recommended)")
parser.add_argument("--brighten", type=float, default=1.1, help="Brightness adjustment (1.0 = none, 1.1 = slightly brighter)")
args = parser.parse_args()

# --------------------------------------------------------
# 🧩 Load labels
# --------------------------------------------------------
with open(args.labels, "r", encoding="utf-8") as f:
    classes = [line.strip() for line in f.readlines() if line.strip()]
print(f"✅ Loaded {len(classes)} classes")

# --------------------------------------------------------
# 🧠 Load the TFLite model
# --------------------------------------------------------
interpreter = tf.lite.Interpreter(model_path=args.model)
interpreter.allocate_tensors()
input_details = interpreter.get_input_details()
output_details = interpreter.get_output_details()

input_shape = input_details[0]["shape"]
input_dtype = input_details[0]["dtype"]
IMG_SIZE = input_shape[1]
print(f"✅ Model input shape: {input_shape}, dtype: {input_dtype}")

# --------------------------------------------------------
# 🌿 Load and preprocess the image
# --------------------------------------------------------
img = Image.open(args.image).convert("RGB").resize((IMG_SIZE, IMG_SIZE))
if args.brighten != 1.0:
    img = ImageEnhance.Brightness(img).enhance(args.brighten)

img_np = np.array(img)

# Preprocess based on dtype
if input_dtype == np.float32:
    img_np = tf.keras.applications.mobilenet_v3.preprocess_input(
        np.expand_dims(img_np.astype(np.float32), axis=0)
    )
elif input_dtype == np.uint8:
    img_np = np.expand_dims(img_np.astype(np.uint8), axis=0)
else:
    raise ValueError(f"Unsupported input dtype: {input_dtype}")

# --------------------------------------------------------
# 🚀 Run inference
# --------------------------------------------------------
interpreter.set_tensor(input_details[0]["index"], img_np)
interpreter.invoke()
output = interpreter.get_tensor(output_details[0]["index"])[0]

# --------------------------------------------------------
# 🎛️ Apply temperature scaling
# --------------------------------------------------------
if args.temp != 1.0:
    logits = np.log(output + 1e-9)
    exp_logits = np.exp(logits / args.temp)
    output = exp_logits / np.sum(exp_logits)

# --------------------------------------------------------
# 💡 Apply bias boost if desired
# --------------------------------------------------------
if args.prefer:
    prefer_lower = args.prefer.lower()
    for i, cls in enumerate(classes):
        if prefer_lower in cls.lower():
            output[i] *= (1.0 + args.boost)
            print(f"🌿 Applied +{int(args.boost*100)}% boost to class '{cls}'")
output = output / np.sum(output)

# --------------------------------------------------------
# 📊 Display results
# --------------------------------------------------------
top5 = np.argsort(output)[-5:][::-1]
print("\n🔍 Top-5 Predictions:")
for i in top5:
    print(f"  {classes[i]:35s} : {output[i]:.4f}")

best_idx = int(np.argmax(output))
print("\n🌱 Most likely plant species:")
print(f"➡️  {classes[best_idx]} ({output[best_idx]*100:.2f}% confidence)")
