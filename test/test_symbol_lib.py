from PIL import Image
from symbol_library import SymbolLibrary

library = SymbolLibrary()

# Create a blank image
image = Image.new("RGB", (900, 900), (30, 30, 30))

# Draw all 27 symbols in a 3x9 grid
for digit in range(27):

    row = digit // 9
    col = digit % 9

    x = 80 + col * 90
    y = 200 + row * 250

    library.draw_symbol(
        image,
        centre=(x, y),
        digit=digit,
        size=60
    )

image.save("symbol_test.png")
