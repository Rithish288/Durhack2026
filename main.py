from decoder import ArtworkDecoder
from encoder import Encoder
from artwork_generator import ArtworkGenerator

enc = Encoder()
encoded_msg = enc.encode(["planeness", "feasibility", "studying"])

generator = ArtworkGenerator()

generator.generate(
    encoded_msg,
    output_path='output/artwork.png'
)

print("ground truth: ", encoded_msg)

decoder = ArtworkDecoder()
output = decoder.decode_image("test/img.png", debug_warped_path="warped.png")

print(output)