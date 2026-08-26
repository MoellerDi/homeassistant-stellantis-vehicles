"""Parsing of the InWebo "IW data" blob.

The InWebo OTP mobile SDK stores its local state (account id, rotating
keys, list of linked services, pending messages, etc.) as one big
delimiter-separated string, historically produced by a Java client
(hence the very compact/cryptic original field names such as ``iwK0``,
``iwsrvn``...). This module decodes that blob into a Python object and
knows how to merge in updates ("synchro") received from the server.

Field names have been kept close to the protocol's own vocabulary
(prefixed to indicate their group: device/account, keys, linked
services, messages) but spelled out so their purpose is clear.
"""
import hashlib
from locale import atoi
from time import time

from Crypto.Cipher import AES

from .tokenizer import Tokenizer

# A "factory default" blob used to bootstrap a brand-new IWData object
# before the very first real synchronisation with the server happens.
DEFAULT_TOKEN = "0.2.11&&&&&&0&&0&&0&&9f13ba238fbabba08e85d93638e98ef5e48682a9d3e5bc325c3dd6fac8199a6ce09e9b4f373aa6a" \
                "75a905c3d690f6e3335d1e8e5b748ecec3020a794149033f6ada6896db6d73b8d43b8365bbe15b9ac66f49d4e684a3628f1e" \
                "9f3deda0c4e24aba771946e6085b92c5ad312477152acf8db01e6aea4b409d5ac1a05c2fd4e95&&0&&&&&&&&&&&&0&&0&&0&" \
                "&0&&0&&0&&0&&&&&&&&0&&0&&0&&0&&0&&2.0.0&&http://m.inwebo.com/&&"
# Protocol/format version that DEFAULT_TOKEN was written for; controls
# which optional fields load_iw_data_v1xx() expects to find.
DEFAULT_FORMAT_VERSION = "529"


def unescape_ampersand(text: str):
    """The server escapes literal '&' characters as '&amp;' so they don't
    get confused with the '&&' field delimiter; undo that here."""
    return text.replace("&amp;", "&")


class IWData:
    """Decoded state of the InWebo "IW data" blob: device/account identity,
    rotating keys, linked services, and pending messages, kept in sync
    with the server via ``apply_server_update``."""

    # pylint: disable=invalid-name,too-many-branches,too-many-statements
    def __init__(self, otp_client):
        """
        :param otp_client: the owning Otp instance (needed for a couple of
            flags such as ``is_mac_client`` that change how the blob is
            structured).
        """
        self.otp_client = otp_client
        self.tokenizer = Tokenizer(DEFAULT_TOKEN)
        self.tokenizer.next_token()  # discard the leading version token
        self.load_iw_data_v1xx(int(DEFAULT_FORMAT_VERSION), self.tokenizer)

    # Maps attribute names used before the "annotated" rewrite (commit
    # 35d150c) to their current name, so otp.bin files saved by that older
    # code still restore this nested object under the right attributes.
    LEGACY_ATTR_ALIASES = {
        "IW": "otp_client",
        "iwid": "device_id",
        "iwalea": "device_alea",
        "iwblocked": "is_blocked",
        "iwhasnopin": "has_no_pin",
        "iwTsync": "last_sync_timestamp",
        "kfact": "factory_key",
        "iwconnected": "connected_timestamp",
        "iwserver": "server_url",
        "iwJ": "challenge_token",
        "iwK": "master_key",
        "iwK0": "master_key_0",
        "iwK1": "master_key_1",
        "iwTref": "reference_timestamp",
        "iwcancelpin": "cancel_pin_count",
        "iwnboka": "ok_attempt_count",
        "iwlastt1": "last_attempt_time_1",
        "iwlastt2": "last_attempt_time_2",
        "iwlastt3": "last_attempt_time_3",
        "iwlastbp": "last_bad_pin_time",
        "iwstackrand": "stack_random",
        "iwstack": "stack",
        "iwH": "verification_hash",
        "iwsrvn": "service_count",
        "iwsrvid": "service_ids",
        "iwsrvname": "service_names",
        "iwsrvlogo": "service_logos",
        "iwsrvurl": "service_urls",
        "iwsrvonlineotp": "service_online_otp",
        "iwsrvconnected": "service_connected",
        "iwsrvsecure": "service_secure",
        "iwsrvksc": "service_ksc",
        "iwsecn": "secret_count",
        "iwsecid": "secret_ids",
        "iwsecval": "secret_values",
        "iwmsgn": "message_count",
        "iwmsgtime": "message_time",
        "iwmsgid": "message_ids",
        "iwmsgtitle": "message_titles",
        "iwmsgcontent": "message_contents",
        "iwmsgack": "message_acks",
        "iwmajorversion": "major_version",
        "iwnewversion": "new_version",
        "iwnewversionurl": "new_version_url",
        "mustupgrade": "must_upgrade",
        "datatouch": "data_touched",
    }

    def __setstate__(self, state):
        """Restore a pickled IWData, remapping attribute names from the
        pre-rewrite field-name scheme (``iwid``, ``iwK0``, ...) to their
        current names if present."""
        self.__dict__.update(
            {self.LEGACY_ATTR_ALIASES.get(key, key): value for key, value in state.items()}
        )

    def load_iw_data_v1xx(self, format_version, tokenizer):
        """Parse a "1.xx" format IW data blob token by token, in the exact
        order the fields were written by the server/client."""
        self.device_id = tokenizer.next_token()
        self.device_alea = tokenizer.next_token()  # random value used to build the device serial
        self.is_blocked = tokenizer.next_token_as_int()
        if format_version >= 519:
            self.has_no_pin = tokenizer.next_token_as_int()
        self.last_sync_timestamp = tokenizer.next_token_as_int()
        self.factory_key = tokenizer.next_token()
        if self.otp_client.is_mac_client:
            self.connected_timestamp = tokenizer.next_token_as_int()
            self.server_url = tokenizer.next_token()
        self.challenge_token = tokenizer.next_token()  # server field "J"
        self.master_key = tokenizer.next_token()       # server field "K"
        self.master_key_0 = tokenizer.next_token()      # server field "K0"
        self.master_key_1 = tokenizer.next_token()      # server field "K1"
        self.reference_timestamp = tokenizer.next_token_as_int()
        self.cancel_pin_count = tokenizer.next_token_as_int()
        self.ok_attempt_count = tokenizer.next_token_as_int()
        self.last_attempt_time_1 = tokenizer.next_token_as_int()
        self.last_attempt_time_2 = tokenizer.next_token_as_int()
        self.last_attempt_time_3 = tokenizer.next_token_as_int()
        self.last_bad_pin_time = tokenizer.next_token_as_int()
        self.stack_random = tokenizer.next_token()
        self.stack = tokenizer.next_token()
        self.verification_hash = tokenizer.next_token()  # server field "H"

        service_count = tokenizer.next_token_as_int()
        self.service_count = service_count
        self.service_ids = [None] * service_count
        self.service_names = [None] * service_count
        self.service_logos = [None] * service_count
        self.service_urls = [None] * service_count
        self.service_online_otp = [None] * service_count
        if self.otp_client.is_mac_client:
            self.service_connected = [None] * self.service_count
        self.service_secure = [None] * service_count
        self.service_ksc = [None] * service_count

        i = 0
        while i < self.service_count:
            self.service_ids[i] = tokenizer.next_token()
            self.service_names[i] = unescape_ampersand(tokenizer.next_token())
            self.service_logos[i] = unescape_ampersand(tokenizer.next_token())
            if self.otp_client.is_mac_client:
                self.service_connected[i] = tokenizer.next_token_as_int()
            if format_version > 515:
                url_field_present = 1
            elif format_version == 515:
                url_field_present = 0
            else:
                url_field_present = -1
            if url_field_present < 0 or self.otp_client.is_mac_client:
                self.service_urls[i] = ""
            else:
                self.service_urls[i] = unescape_ampersand(tokenizer.next_token())
            if format_version < 520 or self.otp_client.is_mac_client:
                self.service_online_otp[i] = 0
            else:
                self.service_online_otp[i] = tokenizer.next_token_as_int()
            self.service_secure[i] = tokenizer.next_token()
            if url_field_present < 0 or not self.otp_client.is_mac_client:
                self.service_ksc[i] = ""
            else:
                self.service_ksc[i] = tokenizer.next_token()
            i += 1

        secret_count = tokenizer.next_token_as_int()
        self.secret_count = secret_count
        self.secret_ids = [None] * secret_count
        self.secret_values = [None] * secret_count
        i = 0
        while i < self.secret_count:
            self.secret_ids[i] = tokenizer.next_token()
            self.secret_values[i] = tokenizer.next_token()
            i += 1

        self.message_count = tokenizer.next_token_as_int()
        self.message_time = tokenizer.next_token_as_int()
        self.message_ids = ""
        self.message_titles = ""
        self.message_contents = ""
        self.message_acks = ""
        i = 0
        while i < self.message_count:
            self.message_ids += tokenizer.next_token()
            self.message_titles += unescape_ampersand(tokenizer.next_token())
            self.message_contents += unescape_ampersand(tokenizer.next_token())
            self.message_acks += tokenizer.next_token_as_int()
            i += 1

        self.major_version = tokenizer.next_token_as_int()
        self.new_version = unescape_ampersand(tokenizer.next_token())
        self.new_version_url = unescape_ampersand(tokenizer.next_token())
        self.must_upgrade = False
        self.data_touched = 0

    def apply_server_update(self, response_xml: dict, aes_key: str):
        """Merge a partial update received from the server (a "synchro")
        into the current state. Only the fields present in
        ``response_xml`` are updated; everything else keeps its previous
        value.

        :param response_xml: dict-ified XML response from the server.
        :param aes_key: hex-encoded AES key used to decrypt the fields
            that come back encrypted (K0, K1, H).
        """
        aes_cipher = AES.new(bytes.fromhex(aes_key), AES.MODE_ECB)

        value = response_xml.get("id")
        if value is not None and len(value) > 0:
            self.device_id = value

        value = response_xml.get("server")
        if value is not None and len(value) > 0:
            self.server_url = value

        value = response_xml.get("K0")
        if value is not None and len(value) > 0:
            self.master_key_0 = aes_cipher.decrypt(bytes.fromhex(value)).hex()

        value = response_xml.get("K1")
        if value is not None and len(value) > 0:
            self.master_key_1 = aes_cipher.decrypt(bytes.fromhex(value)).hex()

        value = response_xml.get("dK1")
        if value is not None and len(value) > 0:
            # K1 is rotated forward by hashing it together with the
            # server-supplied delta "dK1".
            self.master_key_1 = hashlib.sha256(
                ("" + self.master_key_1 + ";" + value).encode("utf-8")
            ).hexdigest()[0:32]

        value = response_xml.get("J")
        if value is not None and len(value) > 0:
            self.challenge_token = value
            self.reference_timestamp = int(time())
            self.otp_client.otpRetryService = -1

        value = response_xml.get("K")
        if value is not None and len(value) > 0:
            self.master_key = value

        value = response_xml.get("H")
        if value is not None and len(value) > 0:
            self.verification_hash = aes_cipher.decrypt(bytes.fromhex(value))

        value = response_xml.get("connected")
        if value is not None and len(value) > 0:
            self.connected_timestamp = atoi(value) + int(time())

        value = response_xml.get("s_n")
        if value is not None and len(value) > 0:
            # A full "linked services" list was sent: reset the
            # per-attempt counters and replace the service list wholesale.
            self.cancel_pin_count = 0
            self.ok_attempt_count = 0
            self.last_attempt_time_1 = 0
            self.last_attempt_time_2 = 0
            self.last_attempt_time_3 = 0
            self.last_bad_pin_time = 0
            self.stack_random = ""
            self.stack = ""
            self.last_sync_timestamp = response_xml.get("Tsync")
            self.service_count = response_xml.get("s_n")
            self.service_ids = response_xml.get("s_id")
            self.service_names = response_xml.get("s_name")
            self.service_logos = response_xml.get("s_icon")
            self.service_connected = response_xml.get("s_connected")
            self.service_ksc = response_xml.get("s_ksc")
            self.service_secure = response_xml.get("s_secure")
            self.service_urls = response_xml.get("s_url")
            self.service_online_otp = response_xml.get("s_onlineotp")
            self.otp_client.synchroJustDone = 1

        value = response_xml.get("m_n")
        if value is not None and len(value) > 0:
            self.message_time = int(time())
            self.message_count = response_xml.get("m_n")
            self.message_ids = response_xml.get("m_id")
            self.message_titles = response_xml.get("m_title")
            self.message_contents = response_xml.get("m_content")
            self.message_acks = response_xml.get("m_ack")

        self.data_touched = 1

    # Backward-compatible alias: the server-facing code originally called
    # this method "synchro".
    synchro = apply_server_update
