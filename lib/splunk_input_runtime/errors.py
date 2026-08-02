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

class SplunkInputRuntimeError(Exception):
    """Base class for every error this runtime raises."""


class ProtocolError(SplunkInputRuntimeError):
    """The modular-input XML protocol was violated, or context construction was invalid."""


class RestError(SplunkInputRuntimeError):
    """A REST call to splunkd failed. Never carries a response body or request payload."""


class CredentialError(SplunkInputRuntimeError):
    """Credential lookup or protect_input_fields failed closed. Never carries a secret value."""
