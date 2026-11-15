import csv
import base64
import os
import random
import tempfile

from flask import Flask, jsonify, request
from flask_cors import CORS

from artwork_generator import ArtworkGenerator
from decoder import ArtworkDecoder
from encoder import Encoder


app = Flask(__name__)
CORS(app)


def load_words(path):
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader, None)
        return [row[0].strip() for row in reader if row and row[0].strip()]


@app.post("/api/generate")
def generate_artwork():
    csv_file = request.files.get("csv")
    if csv_file is None or not csv_file.filename:
        return jsonify({"error": "Please upload a CSV word list."}), 400

    raw_words = request.form.getlist("words")
    words = [word.strip() for word in raw_words if word.strip()]
    if len(words) not in (0, 3):
        return jsonify({"error": "Enter either zero words or exactly three words."}), 400

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = os.path.join(temp_dir, "words.csv")
            output_path = os.path.join(temp_dir, "artwork.png")
            csv_file.save(csv_path)
            available_words = load_words(csv_path)

            if len(available_words) < 3:
                raise ValueError("The CSV must contain at least three words.")
            invalid_words = [word for word in words if word not in available_words]
            if invalid_words:
                raise ValueError(
                    f"Word(s) not found in dictionary: {', '.join(invalid_words)}"
                )
            selected_words = words or random.sample(available_words, 3)

            encoder = Encoder(wordlist_file=csv_path)
            encoded_message = encoder.encode(selected_words)
            ArtworkGenerator().generate(encoded_message, output_path=output_path)

            with open(output_path, "rb") as artwork:
                image_data = base64.b64encode(artwork.read()).decode("ascii")

        return jsonify({
            "words": selected_words,
            "image": f"data:image/png;base64,{image_data}",
        })
    except (OSError, UnicodeDecodeError, csv.Error, ValueError) as error:
        return jsonify({"error": str(error)}), 400


@app.post("/api/decode")
def decode_artwork():
    image_file = request.files.get("image")
    if image_file is None or not image_file.filename:
        return jsonify({"error": "Please upload an artwork image."}), 400

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = os.path.join(temp_dir, "artwork.png")
            image_file.save(image_path)

            dictionary_file = request.files.get("csv")
            if dictionary_file is not None and dictionary_file.filename:
                wordlist_path = os.path.join(temp_dir, "words.csv")
                dictionary_file.save(wordlist_path)
            else:
                wordlist_path = os.path.abspath("durhack_word_list.csv")

            decoded = ArtworkDecoder(wordlist_file=wordlist_path).decode_image(image_path)

        return jsonify({
            "words": list(decoded["words"]),
            "symbols": decoded["symbols"],
        })
    except (OSError, UnicodeDecodeError, ValueError) as error:
        return jsonify({"error": str(error)}), 400


if __name__ == "__main__":
    app.run(debug=True, port=5000)
