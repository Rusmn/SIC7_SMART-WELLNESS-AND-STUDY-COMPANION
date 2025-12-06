from transformers import pipeline
from PIL import Image
import io
import logging

class EmotionEngine:
    def __init__(self):
        self.logger = logging.getLogger("uvicorn")
        self.classifier = pipeline("image-classification", model="dima806/facial_emotions_image_detection")

    def predict(self, image_bytes):
        try:
            image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            preds = self.classifier(image)
            top = max(preds, key=lambda x: x['score'])
            return top['label'], top['score']
        except Exception:
            return None, 0.0