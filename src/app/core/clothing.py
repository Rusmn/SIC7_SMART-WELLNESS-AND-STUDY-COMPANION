from transformers import CLIPProcessor, CLIPModel
from PIL import Image
import torch
import io
import logging

logger = logging.getLogger("uvicorn")

class ClothingEngine:
    def __init__(self):
        # Load Model sekali saja saat init
        model_id = "openai/clip-vit-base-patch32"
        try:
            self.model = CLIPModel.from_pretrained(model_id)
            self.processor = CLIPProcessor.from_pretrained(model_id)
            logger.info("ClothingEngine model loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load ClothingEngine model: {e}")

        # Prompt Definisi Pakaian
        self.candidate_labels = [
            "a photo of a person wearing a thin sleeveless tank top or singlet",
            "a photo of a person wearing a short-sleeve t-shirt",
            "a photo of a person wearing a long-sleeve formal shirt",
            "a photo of a person wearing a thick winter jacket or hoodie",
            "a photo of a person wearing a heavy wool sweater"
        ]

    def predict(self, image_bytes) -> str:
        try:
            image = Image.open(io.BytesIO(image_bytes))
            
            # Preprocessing & Inferensi
            inputs = self.processor(text=self.candidate_labels, images=image, return_tensors="pt", padding=True)
            with torch.no_grad():
                outputs = self.model(**inputs)
            
            # Ambil label dengan probabilitas tertinggi
            probs = outputs.logits_per_image.softmax(dim=1)
            predicted_index = probs.argmax().item()
            predicted_label = self.candidate_labels[predicted_index]
            
            # Mapping ke 3 Kategori Utama
            if "sleeveless" in predicted_label or "t-shirt" in predicted_label:
                return "Tipis"
            elif "formal shirt" in predicted_label or "button-down" in predicted_label:
                return "Sedang"
            else:
                return "Tebal"
                
        except Exception as e:
            logger.error(f"Error in ClothingEngine predict: {e}")
            return "Sedang" # Fallback default