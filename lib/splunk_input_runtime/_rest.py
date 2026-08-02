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

"""Private stdlib HTTP(S) transport and URL builder for splunkd's app-scoped REST endpoints.

Not a public client: only the paths needed by credentials.py and _inputs.py are exposed.
"""

import http.client
import json
import ssl
from urllib.parse import quote, urlencode

from .errors import RestError

_TIMEOUT_SECONDS = 30


def quote_component(value):
    return quote(str(value), safe="")


def storage_passwords_collection_path(owner, app):
    return f"/servicesNS/{quote_component(owner)}/{quote_component(app)}/storage/passwords"


def credential_entity_path(owner, app, realm, username):
    entity = f"{quote_component(realm)}:{quote_component(username)}:"
    return f"{storage_passwords_collection_path(owner, app)}/{entity}"


def input_stanza_path(owner, app, kind, stanza):
    return (
        f"/servicesNS/{quote_component(owner)}/{quote_component(app)}"
        f"/data/inputs/{quote_component(kind)}/{quote_component(stanza)}"
    )


class RestTransport:
    """Session-key-authenticated transport bound to exactly the host/port from a trusted server_uri."""

    def __init__(self, scheme, host, port, session_key, timeout=_TIMEOUT_SECONDS):
        self._scheme = scheme
        self._host = host
        self._port = port
        self._session_key = session_key
        self._timeout = timeout

    def _headers(self, extra=None):
        headers = {"Authorization": f"Splunk {self._session_key}"}
        if extra:
            headers.update(extra)
        return headers

    def _connect(self):
        if self._scheme == "https":
            # Local splunkd invocation URIs are commonly self-signed; verification is
            # scoped to exactly this caller-supplied authority, never a general client.
            context = ssl._create_unverified_context()
            return http.client.HTTPSConnection(
                self._host, self._port, timeout=self._timeout, context=context
            )
        return http.client.HTTPConnection(self._host, self._port, timeout=self._timeout)

    def _do(self, method, path, body=None, headers=None):
        conn = self._connect()
        try:
            conn.request(method, path, body=body, headers=self._headers(headers))
            response = conn.getresponse()
            payload = response.read()
        except (OSError, http.client.HTTPException) as exc:
            raise RestError(f"splunkd request failed: {type(exc).__name__}") from None
        finally:
            conn.close()
        # 3xx is treated as failure: redirects to another authority are never followed.
        if response.status >= 300:
            raise RestError(f"splunkd returned status {response.status}")
        return payload

    def get_json(self, path):
        separator = "&" if "?" in path else "?"
        payload = self._do("GET", f"{path}{separator}output_mode=json&count=0")
        if not payload:
            return {}
        return json.loads(payload)

    def post_form(self, path, fields):
        separator = "&" if "?" in path else "?"
        body = urlencode(fields)
        payload = self._do(
            "POST",
            f"{path}{separator}output_mode=json",
            body=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if not payload:
            return {}
        return json.loads(payload)

    def delete(self, path):
        separator = "&" if "?" in path else "?"
        self._do("DELETE", f"{path}{separator}output_mode=json")
