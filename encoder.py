import csv
from reedsolo import RSCodec, ReedSolomonError

class Encoder:

    ALPHABET = "0123456789ABCDEFGHIJKLMNOPQ"

    DATA_DIGITS = 10
    DATA_BYTES = 6
    PARITY_BYTES = 4
    TOTAL_BYTES = 10
    TOTAL_SYMBOLS = 20
    DICTIONARY_SIZE = 30000

    def __init__(self, wordlist_file='durhack_word_list.csv'):
        # reedsolo uses GF(256) by default
        self.rs = RSCodec(self.PARITY_BYTES)
        self.wordlist_file = wordlist_file
        self.word_to_index = {}
        self.words = []
        self._load_words()

    def _load_words(self):
        """Load words from the CSV file and create word-to-index mapping."""
        with open(self.wordlist_file, 'r') as f:
            reader = csv.reader(f)
            next(reader)  # Skip header
            self.words = [row[0] for row in reader]
            self.word_to_index = {word: idx for idx, word in enumerate(self.words)}

    def get_word_indices(self, input_words):
        """Get indices for three input words.

        Args:
            input_words: List of three words

        Returns:
            List of (index, word) tuples

        Raises:
            ValueError: If word not found in wordlist or incorrect number of words
        """
        if len(input_words) != 3:
            raise ValueError("Exactly 3 words required")

        result = []
        for word in input_words:
            if word not in self.word_to_index:
                raise ValueError(f"Word '{word}' not found in wordlist")
            idx = self.word_to_index[word]
            result.append((idx, word))

        return result

    def int_to_base27(self, number, length):
        digits = [0] * length

        for i in range(length - 1, -1, -1):
            digits[i] = number % 27
            number //= 27

        if number:
            raise ValueError("Number exceeds base-27 capacity")

        return digits

    def base27_to_int(self, digits):
        number = 0

        for digit in digits:
            number = number * 27 + digit

        return number

    def bytes_to_base27(self, data):
        digits = []

        for byte in data:
            digits.append(byte // 27)
            digits.append(byte % 27)

        return ''.join(self.ALPHABET[d] for d in digits)

    def base27_to_bytes(self, symbols, uncertain_positions=None):
        if len(symbols) != self.TOTAL_SYMBOLS:
            raise ValueError("Expected exactly 20 visual symbols")

        uncertain_positions = set(uncertain_positions or [])

        received = []
        invalid_erasures = []
        soft_erasures = []

        for i in range(self.TOTAL_BYTES):

            pos1 = 2 * i
            pos2 = pos1 + 1

            # Decode the two base-27 digits
            try:
                d1 = self.ALPHABET.index(symbols[pos1])
                d2 = self.ALPHABET.index(symbols[pos2])

                byte_value = d1 * 27 + d2

                if byte_value > 255:
                    raise ValueError("Invalid byte")

                if (pos1 in uncertain_positions or
                        pos2 in uncertain_positions):
                    soft_erasures.append(i)

            except ValueError:
                # Mark this byte as an erasure
                byte_value = 0
                invalid_erasures.append(i)

            received.append(byte_value)

        # RSCodec(4) supports at most PARITY_BYTES (4) erasures
        erasures = (invalid_erasures + soft_erasures)[:self.PARITY_BYTES]
        return bytes(received), erasures

    def encode(self, input_words):

        if len(input_words) != 3:
            raise ValueError("Exactly 3 words required")

        # 1. Get dictionary indices
        word_data = self.get_word_indices(input_words)
        w1, w2, w3 = [idx for idx, word in word_data]

        if not all(0 <= w < self.DICTIONARY_SIZE
                   for w in (w1, w2, w3)):
            raise ValueError("Invalid dictionary index")

        # 2. Combine indices into one integer
        M = (
            w1 * self.DICTIONARY_SIZE ** 2
            + w2 * self.DICTIONARY_SIZE
            + w3
        )

        # 3. Convert to 10 base-27 digits
        data_digits = self.int_to_base27(
            M, self.DATA_DIGITS
        )

        # 4. Convert integer to 6 bytes
        data_bytes = M.to_bytes(
            self.DATA_BYTES, byteorder="big"
        )

        # 5. Reed-Solomon encoding
        encoded_bytes = self.rs.encode(data_bytes)

        # 6. Convert 10 bytes into 20 base-27 symbols
        result = self.bytes_to_base27(encoded_bytes)

        assert len(result) == self.TOTAL_SYMBOLS

        return result

    def decode(self, symbols, uncertain_positions=None):

        # 1. Convert visual symbols into bytes
        received, erasures = self.base27_to_bytes(
            symbols, uncertain_positions
        )

        # 2. Reed-Solomon error correction
        try:
            decoded = self.rs.decode(
                received,
                erase_pos=erasures
            )

            original_bytes = decoded[0]

        except ReedSolomonError as e:
            raise ValueError(
                "Unable to recover message: too many errors"
            ) from e

        # 3. Convert 6 bytes back to integer
        M = int.from_bytes(original_bytes, byteorder="big")

        # 4. Convert integer to three dictionary indices
        w1, remainder = divmod(
            M, self.DICTIONARY_SIZE ** 2
        )

        w2, w3 = divmod(
            remainder, self.DICTIONARY_SIZE
        )

        if not all(0 <= w < self.DICTIONARY_SIZE
                   for w in (w1, w2, w3)):
            raise ValueError("Decoded invalid dictionary indices")

        return w1, w2, w3
