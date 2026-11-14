"""CUBE DECODE app (receiver's computer): load the two images -> watch the solve -> read the three words.

usage: python cube_decode_app.py [words.csv] [port]     -> opens http://127.0.0.1:8772
Pairs with cube_encode_app.py on the other computer. Needs flask + kociemba + opencv (see requirements.txt).
"""
import cube_app

if __name__ == "__main__":
    cube_app.main("decode")
