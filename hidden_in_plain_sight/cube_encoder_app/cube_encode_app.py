"""CUBE ENCODE app (sender's computer): three words -> scrambled cube -> export two images.

usage: python cube_encode_app.py [words.csv] [port]     -> opens http://127.0.0.1:8771
Pairs with cube_decode_app.py on the other computer. Needs flask + kociemba (see requirements.txt).
"""
import cube_app

if __name__ == "__main__":
    cube_app.main("encode")
