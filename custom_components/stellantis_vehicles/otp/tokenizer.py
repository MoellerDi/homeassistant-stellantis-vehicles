"""A simple tokenizer that splits a string on a fixed delimiter.

The original InWebo mobile SDK encodes its configuration data as one long
string where individual fields are separated by a custom delimiter
(by default ``"&&"``). This class walks through that string one token at a
time, similar to ``str.split()`` but lazily and with an extra helper to
read a token directly as a hexadecimal integer.
"""


class Tokenizer:
    """Lazily splits a delimited string into tokens, matching the field
    order InWebo's mobile SDK uses to serialize its blob."""

    def __init__(self, token_string, delimiter="&&"):
        """
        :param token_string: the full delimited string to tokenize.
        :param delimiter: the substring that separates tokens.
        """
        self.token_string: str = token_string
        self.delimiter = delimiter
        # Position (in token_string) where the next token starts.
        self.current_index = 0

    def next_token(self):
        """Return the next token in the string, advancing the internal
        cursor past it (and past the following delimiter).

        Returns an empty string once the end of the string has been
        reached.
        """
        if self.current_index >= len(self.token_string):
            return ""

        # Find the next delimiter occurrence starting from current_index.
        delimiter_index = self.current_index + self.token_string[self.current_index:].index(self.delimiter)

        if delimiter_index == -1:
            # No more delimiters: the rest of the string is the last token.
            remaining = self.token_string[self.current_index:]
            self.current_index = len(self.token_string)
            return remaining

        token = self.token_string[self.current_index:delimiter_index]
        self.current_index = delimiter_index + len(self.delimiter)
        return token

    def next_token_as_int(self):
        """Read the next token and parse it as a base-16 (hexadecimal)
        integer. Returns 0 if the token is empty."""
        token = self.next_token()
        if token == "":
            return 0
        return int(token, 16)

    def has_more_tokens(self):
        """Whether there is still unread data left to tokenize."""
        return self.current_index < len(self.token_string)
