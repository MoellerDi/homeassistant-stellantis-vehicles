"""Custom PKCS#1 OAEP decryption.

This is a thin variant of pycryptodome's ``PKCS1OAEP_Cipher``: it
re-implements ``decrypt`` so it deliberately skips the strict "leading
byte must be 0" check that the stock implementation performs. That
check is normally there as an extra correctness guard, but checking it
separately (before the rest of the padding is validated) can leak
timing information that an attacker can use to decrypt ciphertexts
without knowing the private key (a "Manger's attack"). Folding that
byte into the same constant-time comparison as everything else, like
this implementation does, avoids that.

This is needed here because InWebo's server-side RSA/OAEP
implementation does not always produce a leading zero byte, so the
stock pycryptodome check would reject otherwise-valid responses.
"""
import Crypto
from Crypto import Random
from Crypto.Cipher.PKCS1_OAEP import PKCS1OAEP_Cipher
from Crypto.Util.number import ceil_div, bytes_to_long, long_to_bytes
from Crypto.Util.py3compat import bord
from Crypto.Util.strxor import strxor


class NonStrictOAEPCipher(PKCS1OAEP_Cipher):
    # pylint: disable=too-many-locals,invalid-name
    def decrypt(self, ciphertext):
        """Decrypt a message with PKCS#1 OAEP.

        :param ciphertext: The encrypted message.
        :type ciphertext: bytes/bytearray/memoryview

        :returns: The original message (plaintext).
        :rtype: bytes

        :raises ValueError:
            if the ciphertext has the wrong length, or if decryption
            fails the integrity check (in which case, the decryption
            key is probably wrong).
        :raises TypeError:
            if the RSA key has no private half (i.e. you are trying
            to decrypt using a public key).
        """

        # See section 7.1.2 of RFC3447 for the numbered steps below.
        modulus_bits = Crypto.Util.number.size(self._key.n)
        modulus_len_bytes = ceil_div(modulus_bits, 8)  # convert from bits to bytes
        hash_len = self._hashObj.digest_size

        # Step 1b and 1c: the ciphertext must be exactly one RSA block long.
        if len(ciphertext) != modulus_len_bytes:
            raise ValueError("Ciphertext with incorrect length.")

        # Step 2a (OS2IP): ciphertext bytes -> integer.
        ciphertext_int = bytes_to_long(ciphertext)
        # Step 2b (RSADP): raw RSA decryption (modular exponentiation).
        # plaintext_int = self._key._decrypt(ciphertext_int)
        plaintext_int = pow(ciphertext_int, self._key.e, self._key.n)

        # Step 2c (I2OSP): integer -> fixed-length "encoded message" bytes.
        encoded_message = long_to_bytes(plaintext_int, modulus_len_bytes)

        # Step 3a: hash of the (empty, here) OAEP label.
        label_hash = self._hashObj.new(self._label).digest()

        # Step 3b: split the encoded message into its three parts.
        leading_byte = encoded_message[0]
        # This leading byte is supposed to always be 0, but it is
        # intentionally NOT checked in isolation here, to avoid timing
        # side-channel attacks such as Manger's
        # (http://dl.acm.org/citation.cfm?id=704143). It is instead
        # folded into the constant-time validity check performed below.
        masked_seed = encoded_message[1:hash_len + 1]
        masked_data_block = encoded_message[hash_len + 1:]

        # Step 3c: recompute the mask that was XORed onto the seed.
        seed_mask = self._mgf(masked_data_block, hash_len)
        # Step 3d: unmask the seed.
        seed = strxor(masked_seed, seed_mask)
        # Step 3e: recompute the mask that was XORed onto the data block.
        data_block_mask = self._mgf(seed, modulus_len_bytes - hash_len - 1)
        # Step 3f: unmask the data block.
        data_block = strxor(masked_data_block, data_block_mask)

        # Step 3g: the data block is [label_hash | zero padding | 0x01 | message].
        # Locate the 0x01 separator, then compare everything in
        # constant time (accumulating into a single "invalid" flag
        # rather than branching/returning early) so that no timing
        # information about *where* validation failed is leaked.
        separator_pos = data_block[hash_len:].find(b'\x01')
        label_hash_from_block = data_block[:hash_len]
        is_invalid = bord(leading_byte) | int(separator_pos < 0)
        label_hash_diff = strxor(label_hash_from_block, label_hash)
        for byte in label_hash_diff:
            is_invalid |= bord(byte)
        for byte in data_block[hash_len:separator_pos]:
            is_invalid |= bord(byte)
        if is_invalid != 0:
            raise ValueError("Incorrect decryption.")

        # Step 4: everything after the 0x01 separator is the plaintext.
        return data_block[hash_len + separator_pos + 1:]


def new(key, hash_algo=None, mgfunc=None, label=b'', rand_func=None):
    """Build a NonStrictOAEPCipher for ``key`` (construction mirrors
    ``Crypto.Cipher.PKCS1_OAEP.new``)."""
    if rand_func is None:
        rand_func = Random.get_random_bytes
    return NonStrictOAEPCipher(key, hash_algo, mgfunc, label, rand_func)


# Fixed "random" seed used only by unit tests, so OAEP encryption
# output is reproducible instead of different on every run.
def fixed_test_seed(length):
    if length == 32:
        return b'\xf56\xccL`\x8a\x97l\nX0\xf4\x11\x9a\x0e\xce\x99K^\xe6\xcbU\xf3W+It"\xf5\x84\x1d\xe6'
    return None
