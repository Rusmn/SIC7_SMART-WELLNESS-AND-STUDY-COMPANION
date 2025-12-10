from transformers import CLIPProcessor, CLIPModel
from PIL import Image
import torch
import io
import logging

class ClothingEngine:
    def __init__(self):
        self.logger = logging.getLogger("uvicorn")
        model_id = "openai/clip-vit-base-patch32"
        try:
            self.model = CLIPModel.from_pretrained(model_id)
            self.processor = CLIPProcessor.from_pretrained(model_id)
            self.logger.info("ClothingEngine model loaded successfully.")
        except Exception as e:
            self.logger.error(f"Failed to load ClothingEngine model: {e}")

        self.candidate_labels = [
            "a photo of a person wearing a thin sleeveless tank top or singlet",
            "a photo of a person wearing a short-sleeve t-shirt",
            "a photo of a person wearing a long-sleeve formal shirt",
            "a photo of a person wearing a thick winter jacket or hoodie",
            "a photo of a person wearing a heavy wool sweater"
        ]

    def predict(self, image_bytes):
        try:
            image = Image.open(io.BytesIO(image_bytes))
            inputs = self.processor(text=self.candidate_labels, images=image, return_tensors="pt", padding=True)

            with torch.no_grad():
                outputs = self.model(**inputs)

            probs = outputs.logits_per_image.softmax(dim=1)
            predicted_index = probs.argmax().item()
            predicted_label = self.candidate_labels[predicted_index]
            score = probs[0][predicted_index].item()

            final_category = "Tebal"

            if "sleeveless" in predicted_label or "t-shirt" in predicted_label:
                final_category = "Tipis"
            elif "formal shirt" in predicted_label or "button-down" in predicted_label:
                final_category = "Sedang"
            else:
                final_category = "Tebal"

            return final_category, score

        except Exception as e:
            self.logger.error(f"Error in ClothingEngine predict: {e}")
            return None, 0.0