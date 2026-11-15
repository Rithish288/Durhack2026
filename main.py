from decoder import ArtworkDecoder
from encoder import Encoder
from artwork_generator import ArtworkGenerator
import csv
import random

def load_words(path):
    with open(path, newline="", encoding="utf-8") as f:
        return [cell.strip() for row in csv.reader(f) for cell in row if cell.strip()]

words = load_words("durhack_word_list.csv")
picks = random.sample(words, 3)
enc = Encoder()
encoded_msg = enc.encode(picks)
print(picks)

generator = ArtworkGenerator()

generator.generate(
    encoded_msg,
    output_path='output/artwork.png'
)