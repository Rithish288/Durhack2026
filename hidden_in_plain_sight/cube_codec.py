"""cube_codec.py - 3 words <-> cube state.

  3 words -> 45 bits (15 bits each, index into the sorted word list; same as codec.py)
  45 bits + 16-bit check (SHA-256 of the data) = 61-bit payload
  payload -> cube state via cube.int_to_facelets (mixed radix over the legal states)

The check bits mean a misread cube is refused rather than decoded into wrong words.
"""
import hashlib

import codec
import cube

BITS_PER_WORD = codec.BITS_PER_WORD   # 15
N_WORDS = codec.N_WORDS               # 3
DATA_BITS = BITS_PER_WORD * N_WORDS   # 45
CHECK_BITS = 16
PAYLOAD_BITS = DATA_BITS + CHECK_BITS # 61


def words_to_bits(words, wordlist):
    if len(words) != N_WORDS:
        raise ValueError(f"need exactly {N_WORDS} words")
    index = {w: i for i, w in enumerate(wordlist)}
    value = 0
    for w in words:
        w = w.strip().lower()
        if w not in index:
            raise ValueError(f"word not in list: {w!r}")
        value = (value << BITS_PER_WORD) | index[w]
    return value


def bits_to_words(value, wordlist):
    mask = (1 << BITS_PER_WORD) - 1
    words = []
    for i in range(N_WORDS):
        idx = (value >> (BITS_PER_WORD * (N_WORDS - 1 - i))) & mask
        if idx >= len(wordlist):
            raise ValueError(f"decoded index {idx} outside word list")
        words.append(wordlist[idx])
    return words


def checksum(data):
    h = hashlib.sha256(data.to_bytes(8, "big")).digest()
    return int.from_bytes(h[:2], "big") & ((1 << CHECK_BITS) - 1)


def bits_to_payload(data):
    return (data << CHECK_BITS) | checksum(data)


def payload_to_bits(payload):
    if payload >= 1 << PAYLOAD_BITS:
        raise ValueError("not an encoded cube (payload out of range)")
    data, chk = payload >> CHECK_BITS, payload & ((1 << CHECK_BITS) - 1)
    if chk != checksum(data):
        raise ValueError("not an encoded cube (check bits do not match)")
    return data


def words_to_state(words, wordlist):
    """-> (facelets, data_bits_int)"""
    data = words_to_bits(words, wordlist)
    return cube.int_to_facelets(bits_to_payload(data)), data


def state_to_words(facelets, wordlist):
    """-> (words, data_bits_int). Raises ValueError for an illegal or non-encoded cube."""
    payload = cube.facelets_to_int(facelets)
    data = payload_to_bits(payload)
    return bits_to_words(data, wordlist), data
