"""Client for InWebo's OTP (One-Time Password) activation/authentication
protocol, as used by PSA (Peugeot/Citroen/DS) connected-car apps.

This reimplements, in Python, the relevant parts of InWebo's mobile SDK:
registering ("activating") a new virtual OTP device against an account,
then generating time/counter-independent OTP codes from the keys that
activation produced.
"""
import hashlib
import logging
import pickle
from secrets import token_hex, token_bytes
from math import ceil
from collections import defaultdict
from xml.etree import cElementTree as ElT

import requests
from Crypto.Cipher import AES
from Crypto.PublicKey import RSA
from Crypto.Hash import SHA256

from . import oaep
from .load import IWData

# pylint: disable=invalid-name
CONFIG_NAME = "otp.bin"
TIMEOUT_IN_S = 10

logger = logging.getLogger(__name__)


def xml_element_to_dict(element):
    """Recursively convert an ElementTree element into a plain dict,
    the same shape python-xmltodict would produce (tag -> value/attrs/
    children), which is what the rest of this module expects to work
    with instead of ElementTree objects directly."""
    result = {element.tag: {} if element.attrib else None}
    children = list(element)
    if children:
        children_by_tag = defaultdict(list)
        for child_dict in map(xml_element_to_dict, children):
            for tag, value in child_dict.items():
                children_by_tag[tag].append(value)
        result = {element.tag: {tag: values[0] if len(values) == 1 else values
                                 for tag, values in children_by_tag.items()}}
    if element.attrib:
        result[element.tag].update(('@' + k, v) for k, v in element.attrib.items())
    if element.text:
        text = element.text.strip()
        if children or element.attrib:
            if text:
                result[element.tag]['#text'] = text
        else:
            result[element.tag] = text
    return result


BASE36_DIGITS = ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l", "m", "n", "o", "p", "q", "r", "s", "t",
                  "u", "v", "w", "x", "y", "z", "0", "1", "2", "3", "4", "5", "6", "7", "8", "9"]


def number_to_base36(number):
    """Encode an integer as a base-36 string using InWebo's own digit
    order (letters a-z first, then digits 0-9)."""
    base = 36
    if number == 0:
        return [0]
    digits = ""
    while number:
        digits += BASE36_DIGITS[int(number % base)]
        number //= base
    return digits


class ConfigException(Exception):
    """Raised when the OTP configuration/activation state is invalid or
    the server rejected a step of the activation/OTP protocol."""


class InweboOTP:
    """InWebo OTP client: activates a virtual OTP device against an account
    and generates OTP codes from the resulting keys.

    Mirrors the state machine of InWebo's mobile SDK, driven through two
    HTTP round trips per step (``activation_start`` / ``activation_finalyze``)
    in one of three modes: activating a new device (``ACTIVATE_MODE``),
    generating an OTP code (``OTP_MODE``), or the multi-server key exchange
    used internally during activation (``MS_MODE``).
    """

    OTP_TWICE = 10  # server asked for a second OTP round-trip before it will hand out real keys
    OK = 0
    NOK = -1
    # Fixed RSA public exponent used for every RSA key InWebo hands out
    # in this protocol (only the modulus varies).
    RSA_PUBLIC_EXPONENT_HEX = "11"
    exponent = int(RSA_PUBLIC_EXPONENT_HEX, 16)
    ACTIVATE_MODE = "activate"
    OTP_MODE = "otp"
    MS_MODE = "ms"
    iw_host = "https://otp.mpsa.com"
    proxies = None

    def __init__(self, inwebo_access_id, device_id=token_hex(8)):
        """Initialize a not-yet-activated OTP client for the InWebo service
        identified by ``inwebo_access_id``.

        :param inwebo_access_id: the InWebo "mac id" identifying the calling
            application/service (fixed per InWebo account, not per user).
        :param device_id: id of the virtual OTP device to activate/reuse.
            Defaults to a fresh random value; pass the previous session's
            ``device_id`` to reactivate the same device instead of
            registering a new one.
        """
        self.rsa_modulus_hex = None      # decoded RSA modulus (was "Kiw")
        self.pin_mode = None
        self.factory_key = None          # key used to decode rsa_modulus_hex (was "Kfact")
        self.needs_sync = None
        self.service_id = None
        self.alias = None
        self.device_alea = token_hex(16)  # random value included in the device serial
        self.device_id = device_id
        self.pin_code = None
        self.challenge = ""
        self.action = ""
        self.session_id = None
        self.sdk_version = "0.2.11"
        self.is_mac_client = True
        self.iw_data = IWData(self)
        self.rsa_cipher = None
        self.mac_id = inwebo_access_id
        self.sms_code = None
        self.mode = InweboOTP.ACTIVATE_MODE
        self.challenge_number = 0        # server's "defi" (French for "challenge") counter
        self.otp_count = 0

    def initialize_keys(self, Kfact=None, Kiw=None, pinmode=None):
        """Decode the RSA key material returned by the server after a
        successful activation and set up the RSA/OAEP cipher used to
        encrypt subsequent requests."""
        self.factory_key = Kfact
        self.pin_mode = pinmode
        self.rsa_modulus_hex = self.decode_oaep(Kiw, self.factory_key)
        key = RSA.construct((int(self.rsa_modulus_hex, 16), InweboOTP.exponent))
        self.rsa_cipher = oaep.new(key, hash_algo=SHA256)

    def get_serial(self):
        """Build the device serial string sent to the server, combining
        the device id with a random per-instance value."""
        return self.device_id + "/_/" + self.device_alea

    def generate_kma(self, pin_code):
        """Derive the "Kma" key (a hash of the PIN and device serial)
        used both as an AES key and sent to the server to prove
        knowledge of the PIN."""
        serial = self.get_serial()
        kma_source = pin_code + ";" + serial
        kma = hashlib.sha256(kma_source.encode("utf-8")).hexdigest()[:32]
        return kma

    def compute_r_values(self):
        """Compute the three "R0"/"R1"/"R2" proof-of-possession hashes
        the server expects with every request, binding the current
        challenge to the device's keys (and, during a "synchro", to the
        entered PIN)."""
        if self.action == "upgrade":
            iw_key = self.iw_data.master_key_1
            # not correctly implemented
        else:
            iw_key = self.iw_data.master_key_0

        if self.action == "synchro":
            r2_source = self.challenge + ";" + iw_key + ";" + self.pin_code
        else:
            r2_source = self.challenge + ";" + iw_key + ";"

        r0_source = self.challenge + ";" + iw_key + ";" + self.get_serial()
        r1_source = self.challenge + ";" + iw_key + ";" + self.iw_data.master_key_1
        logger.debug("%s\n%s\n%s", r0_source, r1_source, r2_source)
        return {"R0": hashlib.sha256(r0_source.encode("utf-8")).hexdigest(),
                "R1": hashlib.sha256(r1_source.encode("utf-8")).hexdigest(),
                "R2": hashlib.sha256(r2_source.encode("utf-8")).hexdigest()}

    @staticmethod
    def decode_oaep(encrypted_hex, key_hex):
        """Decrypt an RSA-OAEP-encrypted, hex-encoded, possibly
        multi-block payload using the RSA key derived from ``key_hex``.
        """
        modulus = int(key_hex, 16)
        rsa_key = RSA.construct((modulus, InweboOTP.exponent))
        cipher = oaep.new(rsa_key, hash_algo=SHA256)
        block_size = 128
        decrypted_hex = ""
        encrypted_bytes = bytes.fromhex(encrypted_hex)
        block_count = ceil(len(encrypted_bytes) / block_size)

        for block_index in range(0, block_count):
            if block_index == block_count - 1:
                block_end = len(encrypted_bytes)
            else:
                block_end = (1 + block_index) * 128
            block_start = block_index * 128
            plaintext_block = cipher.decrypt(encrypted_bytes[block_start:block_end])
            decrypted_hex += plaintext_block.hex()
        logger.debug(decrypted_hex)
        return decrypted_hex

    def request(self, params, is_setup=False):
        """Perform one HTTP round-trip against the InWebo OTP endpoint
        and parse the XML response into a dict, unwrapping the
        "ActionSetup" or "ActionFinalize" envelope as appropriate."""
        raw_xml = requests.get(
            f"{self.iw_host}/iwws/MAC",
            headers={
                "Connection": "Keep-Alive",
                "Host": "otp.mpsa.com",
                "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 8.0.0; Android SDK built for x86_64 "
                              "Build/OSR1.180418.004)"
            },
            params=params,
            proxies=self.proxies,
            verify=self.proxies is None,
            timeout=TIMEOUT_IN_S
        ).text
        try:
            raw_xml = raw_xml[raw_xml.index("?>") + 2:]  # strip the XML declaration
            if is_setup:
                return xml_element_to_dict(ElT.XML(raw_xml))["ActionSetup"]
            return xml_element_to_dict(ElT.XML(raw_xml))["ActionFinalize"]
        except KeyError:
            logger.debug(raw_xml)
            raise ValueError("Bad response from server") from KeyError

    def activation_start(self):
        """Step 1 of activation/OTP: send "ActionSetup" and store
        whatever key material or challenge the server returns."""
        params = {"action": "ActionSetup", "mode": self.mode, "id": self.iw_data.device_id,
                  "lastsync": self.iw_data.last_sync_timestamp,
                  "version": "Generator-1.0/0.2.11", "macid": self.mac_id}
        if self.mode == InweboOTP.OTP_MODE:
            params.update({"sid": self.iw_data.secret_ids})
        elif self.mode == InweboOTP.ACTIVATE_MODE:
            params.update({"code": self.sms_code})

        response = self.request(params, is_setup=True)
        if response["err"] == "OK":
            if self.mode == InweboOTP.ACTIVATE_MODE:
                key_material = {key: response[key] for key in ["Kiw", "Kfact", "pinmode"]}
                self.initialize_keys(**key_material)
            elif self.mode == InweboOTP.OTP_MODE:
                self.challenge = response["challenge"]
            return True
        raise ConfigException(response)

    def activation_finalyze(self, random_bytes=None):
        """Step 2 of activation/OTP: send "ActionFinalize" with the proof
        values computed from the current keys, then handle whatever
        follow-up the server asks for (a second OTP round, or a
        multi-server "ms" key exchange)."""
        r_values = self.compute_r_values()
        params = {"action": "ActionFinalize", "mode": self.mode, "id": self.iw_data.device_id,
                  "lastsync": self.iw_data.last_sync_timestamp,
                  "version": "Generator-1.0/0.2.11",
                  "lang": "fr", "ack": "", "macid": self.mac_id}
        if self.mode == InweboOTP.OTP_MODE:
            params.update({"keytype": '0', "sid": self.iw_data.secret_ids})

        elif self.mode == InweboOTP.ACTIVATE_MODE:
            kma_encrypted = self.rsa_cipher.encrypt(bytes.fromhex(self.generate_kma(self.pin_code))).hex()
            pin_encrypted = self.rsa_cipher.encrypt(self.pin_code.encode("utf-8")).hex()
            params.update({"serial": self.get_serial(), "code": self.sms_code,
                           "Kma": kma_encrypted, "pin": pin_encrypted,
                           "name": "Android SDK built for x86_64 / UNKNOWN", })

        params.update(r_values)
        response = self.request(params)
        if response["err"] != "OK":
            logger.error("Error during activation: %s", response)
            return response["err"]
        self.iw_data.apply_server_update(response, self.generate_kma(self.pin_code))

        if self.mode == InweboOTP.OTP_MODE:
            try:
                self.challenge_number = str(response["defi"])
            except KeyError:
                raise ConfigException from KeyError
            if "J" in response:
                logger.debug("Need another otp request")
                return InweboOTP.OTP_TWICE
            return InweboOTP.OK

        if "ms_n" not in response or response["ms_n"] == 0:
            logger.debug("no ms_n request needed")
            return InweboOTP.OK

        if int(response["ms_n"]) > 1:
            raise NotImplementedError
        ms_index = "0"

        # Multi-server key exchange: the server hands us a temporary key
        # to wrap a fresh random secret, which we also store locally
        # (AES-encrypted with our PIN-derived key) for later OTP
        # generation.
        self.challenge = response["challenge"]
        self.action = "synchro"
        temp_modulus_hex = self.decode_oaep(response["ms_key"], self.factory_key)
        temp_key = RSA.construct((int(temp_modulus_hex, 16), self.exponent))
        temp_cipher = oaep.new(temp_key, hash_algo=SHA256)
        if random_bytes is None:
            random_bytes = token_bytes(16)
        random_secret_encrypted = temp_cipher.encrypt(random_bytes)

        aes_cipher = AES.new(bytes.fromhex(self.generate_kma(self.pin_code)), AES.MODE_ECB)
        random_secret_locally_encrypted = aes_cipher.encrypt(random_bytes).hex()
        self.iw_data.secret_values = random_secret_locally_encrypted
        self.iw_data.secret_ids = response["s_id"]
        self.iw_data.secret_count = 1

        followup_params = {"action": "ActionFinalize", "mode": InweboOTP.MS_MODE,
                            "ms_id" + ms_index: response["ms_id"],
                            "ms_val" + ms_index: random_secret_encrypted.hex(), "macid": self.mac_id}
        followup_params.update({"id": self.iw_data.device_id, "lastsync": self.iw_data.last_sync_timestamp,
                                 "ms_n": 1})
        followup_params.update(self.compute_r_values())
        response = self.request(followup_params)
        self.iw_data.apply_server_update(response, self.generate_kma(self.pin_code))
        return InweboOTP.OK

    def _compute_otp_code(self):
        """Derive the actual OTP code from the current keys and challenge
        counter: hash them together, then map the hash to a base-36
        string using InWebo's own bit-slicing scheme."""
        password = self.iw_data.master_key_1 + ":" + str(self.challenge_number) + ":" + self.iw_data.secret_values
        digest = bytes(hashlib.sha256(password.encode("utf-8")).digest())
        code_value = ((int.from_bytes(digest[:4], byteorder="big") & 0xfffffff) * 1024) + (
            int.from_bytes(digest[4:8], byteorder="big") & 1023)
        otp_code = number_to_base36(code_value)
        return otp_code

    def get_otp_code(self):
        """Run the full activation/OTP flow (retrying once if the server
        asks for it) and return the resulting OTP code, or None on
        failure."""
        self.mode = InweboOTP.OTP_MODE
        otp_code = None
        try:
            if self.activation_start():
                result = self.activation_finalyze()
                if result != InweboOTP.NOK:
                    if result == InweboOTP.OTP_TWICE:
                        self.mode = InweboOTP.OTP_MODE
                        self.activation_start()
                        assert self.activation_finalyze() == InweboOTP.OK
                    otp_code = self._compute_otp_code()
                    assert otp_code is not None
                    logger.debug("otp code: %s", otp_code)
        except AssertionError as e:
            raise ConfigException("Can't get otp code") from e
        return otp_code

    def __getstate__(self):
        """Return the picklable state for this instance, dropping the
        RSA/OAEP cipher object (rebuilt from ``rsa_modulus_hex`` on load,
        see ``__setstate__``)."""
        state = self.__dict__.copy()
        if 'rsa_cipher' in state:
            del state['rsa_cipher']  # the RSA/OAEP cipher object isn't picklable, rebuild it on load instead
        return state

    def __setstate__(self, state):
        """Restore state from a pickled instance, reconstructing the
        RSA/OAEP cipher from ``rsa_modulus_hex`` if the device was already
        activated."""
        self.__dict__.update(state)
        if self.rsa_modulus_hex is not None:
            key = RSA.construct((int(self.rsa_modulus_hex, 16), InweboOTP.exponent))
            self.rsa_cipher = oaep.new(key, hash_algo=SHA256)

    @staticmethod
    def set_proxies(proxies):
        """Set the HTTP(S) proxy configuration (a ``requests``-style
        proxies dict) used for every request made by every instance of
        this class."""
        InweboOTP.proxies = proxies


def encode_oaep(plaintext, key_hex):
    """Encrypt ``plaintext`` with RSA-OAEP using the RSA key material in
    ``key_hex``, the mirror operation of ``InweboOTP.decode_oaep``.

    Currently unused by this module (nothing calls it), kept for API
    symmetry with ``decode_oaep``.
    """
    cipher = oaep.new(bytes.fromhex(key_hex), hash_algo=SHA256)
    return cipher.encrypt(plaintext)


def save_otp_session(otp_session, filename="otp.bin"):
    """Persist an InweboOTP session to disk (pickled) so it can be reused
    without repeating the full activation flow next time."""
    with open(filename, 'wb') as output_file:
        pickle.dump(otp_session, output_file)


class RenameUnpickler(pickle.Unpickler):
    """Unpickler that redirects classes pickled under their old module
    path to their current location inside psa_car_controller.psa,
    so previously saved otp.bin files still load after the package was
    reorganised."""
    def find_class(self, module, name):
        """Redirect ``module`` (as recorded in the pickle) to its current
        location under ``psa_car_controller.psa`` before deferring to the
        default lookup, so old-format pickles keep unpickling."""
        renamed_module = "psa_car_controller.psa." + module.lower()
        return super().find_class(renamed_module, name)


def load_otp_session(filename=CONFIG_NAME):
    """Load a previously saved InweboOTP session from disk, or None if there
    isn't one yet, or if the file on disk can no longer be unpickled
    into the current InweboOTP/IWData classes (e.g. it was written by an
    older version of this module that used different attribute names).
    Callers should treat None the same way as "never activated" and
    prompt the user to redo the OTP activation step."""
    try:
        with open(filename, 'rb') as input_file:
            try:
                return pickle.load(input_file)
            except ModuleNotFoundError as ex:
                logger.debug(ex, exc_info=True)
                try:
                    input_file.seek(0)
                    return RenameUnpickler(input_file).load()
                except Exception as ex2:
                    logger.warning(
                        "Saved OTP session at %s is incompatible with the current "
                        "code (likely from an older version) and will be discarded: %s",
                        filename, ex2
                    )
                    logger.debug(ex2, exc_info=True)
                    return None
            except Exception as ex:
                # Any other unpickling failure (AttributeError, TypeError,
                # EOFError, pickle.UnpicklingError, ...) means the stored
                # object no longer matches this module's classes.
                logger.warning(
                    "Saved OTP session at %s is incompatible with the current "
                    "code (likely from an older version) and will be discarded: %s",
                    filename, ex
                )
                logger.debug(ex, exc_info=True)
                return None
    except FileNotFoundError:
        logger.debug("", exc_info=True)
    return None


def new_otp_session(sms_code, pin_code, previous_otp_session: InweboOTP = None):
    """Activate a brand-new OTP device (or reactivate, reusing the same
    device id as ``previous_otp_session`` if given) and persist it to
    disk on success."""
    if previous_otp_session is None:
        otp_session = InweboOTP("bb8e981582b0f31353108fb020bead1c")
    else:
        otp_session = InweboOTP("bb8e981582b0f31353108fb020bead1c", device_id=previous_otp_session.device_id)
    otp_session.sms_code = sms_code
    otp_session.pin_code = pin_code
    if otp_session.activation_start():
        otp_session.activation_finalyze()
        save_otp_session(otp_session)
        return otp_session
    return None
