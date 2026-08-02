# Copyright 2026 Bre77
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""App-scoped credential store backed by storage/passwords, and input-field protection."""

from ._rest import credential_entity_path, input_stanza_path, storage_passwords_collection_path
from .errors import CredentialError, RestError

DEFAULT_PLACEHOLDER = "<encrypted>"


class Credential:
    """An immutable, redacted storage/passwords entry."""

    __slots__ = ("_realm", "_username", "_clear_password", "_encrypted_password")

    def __init__(self, realm, username, clear_password, encrypted_password):
        self._realm = realm
        self._username = username
        self._clear_password = clear_password
        self._encrypted_password = encrypted_password

    @property
    def realm(self):
        return self._realm

    @property
    def username(self):
        return self._username

    @property
    def clear_password(self):
        return self._clear_password

    @property
    def encrypted_password(self):
        return self._encrypted_password

    def __repr__(self):
        return (
            f"Credential(realm={self._realm!r}, username={self._username!r}, "
            "clear_password=<redacted>, encrypted_password=<redacted>)"
        )


class SecretField:
    """Declares one stanza field that should be protected by protect_input_fields.

    A plain string in the ``fields`` argument is equivalent to ``SecretField(name)``.
    ``optional=True`` fields may be absent from ``values`` entirely; a required field
    that is absent fails closed instead.
    """

    __slots__ = ("name", "optional")

    def __init__(self, name, optional=False):
        self.name = name
        self.optional = optional

    def __repr__(self):
        return f"SecretField(name={self.name!r}, optional={self.optional!r})"


class CredentialStore:
    """Credential storage for exactly one (owner, app) namespace."""

    def __init__(self, transport, owner, app):
        self._transport = transport
        self.owner = owner
        self.app = app

    def list_credentials(self):
        """Return every Credential visible in this (owner, app) namespace."""
        data = self._transport.get_json(storage_passwords_collection_path(self.owner, self.app))
        credentials = []
        for entry in data.get("entry", []):
            content = entry.get("content", {})
            credentials.append(
                Credential(
                    realm=content.get("realm"),
                    username=content.get("username"),
                    clear_password=content.get("clear_password"),
                    encrypted_password=content.get("encr_password"),
                )
            )
        return credentials

    def _find_matches(self, realm, username):
        return [
            credential
            for credential in self.list_credentials()
            if credential.realm == realm and credential.username == username
        ]

    def get(self, realm, username):
        """Return the exactly-one credential for (realm, username). Fails closed otherwise."""
        matches = self._find_matches(realm, username)
        if len(matches) != 1:
            raise CredentialError(
                f"expected exactly one credential for realm={realm!r} username={username!r}, "
                f"found {len(matches)}"
            )
        return matches[0]

    def set(self, realm, username, password):
        """Create the credential if absent, or update it in place. Never deletes first."""
        matches = self._find_matches(realm, username)
        if len(matches) > 1:
            raise CredentialError(
                f"expected at most one credential for realm={realm!r} username={username!r}, "
                f"found {len(matches)}"
            )
        if matches:
            path = credential_entity_path(self.owner, self.app, realm, username)
            self._transport.post_form(path, {"password": password})
        else:
            path = storage_passwords_collection_path(self.owner, self.app)
            self._transport.post_form(path, {"name": username, "password": password, "realm": realm})

    def delete(self, realm, username):
        """Explicitly delete a credential. Never called implicitly by protect_input_fields."""
        path = credential_entity_path(self.owner, self.app, realm, username)
        self._transport.delete(path)

    def protect_input_fields(self, kind, stanza, values, fields, placeholder=DEFAULT_PLACEHOLDER):
        """Resolve and protect a set of secret fields on one modular-input stanza.

        For each field: a value equal to ``placeholder`` is resolved from the existing
        credential (exactly one match required); a non-empty plaintext value is stored
        (create-or-update) and scheduled for masking; an empty value is left alone.
        Returns a mapping of field name to clear value. Never mutates a clear value into
        a log line or exception message.
        """
        if not placeholder:
            # An empty placeholder is indistinguishable from "leave alone" below,
            # which would silently disable placeholder resolution entirely.
            raise ValueError("placeholder must be a non-empty string")

        normalized = [field if isinstance(field, SecretField) else SecretField(field) for field in fields]

        resolved = {}
        to_store = {}

        for field in normalized:
            if field.name not in values:
                if field.optional:
                    resolved[field.name] = ""
                    continue
                raise CredentialError(
                    f"missing required field {field.name!r} in stanza {stanza!r}"
                )
            value = values[field.name]
            if not value:
                resolved[field.name] = ""
                continue
            if value == placeholder:
                credential = self.get(realm=stanza, username=field.name)
                resolved[field.name] = credential.clear_password
                continue
            resolved[field.name] = value
            to_store[field.name] = value

        for name, plaintext in to_store.items():
            try:
                self.set(realm=stanza, username=name, password=plaintext)
            except RestError:
                # Fields stored before this failure are intentionally left stored,
                # not rolled back; retry protect_input_fields on next invocation.
                raise CredentialError(
                    f"failed to store credential for stanza {stanza!r} field {name!r}"
                ) from None

        if to_store:
            mask = {name: placeholder for name in to_store}
            try:
                self._transport.post_form(
                    input_stanza_path(self.owner, self.app, kind, stanza), mask
                )
            except RestError:
                raise CredentialError(
                    f"stored credentials for stanza {stanza!r} but failed to mask the input "
                    "stanza; retry masking on next invocation"
                ) from None

        return resolved
