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

"""Builds the invocation-scoped REST context from splunkd's trusted stdin metadata."""

from urllib.parse import urlsplit

from ._rest import RestTransport
from .credentials import CredentialStore
from .errors import ProtocolError

DEFAULT_OWNER = "nobody"


class InvocationContext:
    """Everything a modular input needs to reach splunkd's REST API for one invocation."""

    def __init__(self, scheme, host, port, session_key, app, owner=DEFAULT_OWNER):
        self.app = app
        self.owner = owner
        self._transport = RestTransport(scheme, host, port, session_key)
        self.credentials = CredentialStore(self._transport, owner=owner, app=app)

    @classmethod
    def from_metadata(cls, metadata, app):
        """Build a context from an InputDefinition/ValidationDefinition metadata dict."""
        if not app:
            raise ProtocolError("Script.APP must be set before using context")

        server_uri = metadata.get("server_uri")
        session_key = metadata.get("session_key")
        if not server_uri or not session_key:
            raise ProtocolError("server_uri and session_key are required in invocation metadata")

        parts = urlsplit(server_uri, allow_fragments=True)
        if parts.scheme not in ("http", "https"):
            raise ProtocolError(f"unsupported server_uri scheme: {parts.scheme!r}")
        if parts.username is not None or parts.password is not None:
            raise ProtocolError("server_uri must not contain userinfo")
        if parts.query or parts.fragment:
            raise ProtocolError("server_uri must not contain a query or fragment")
        if not parts.hostname:
            raise ProtocolError("server_uri must contain a host")

        port = parts.port or (443 if parts.scheme == "https" else 80)
        return cls(parts.scheme, parts.hostname, port, session_key, app)

    @classmethod
    def from_input_definition(cls, input_definition, app):
        return cls.from_metadata(input_definition.metadata, app)
