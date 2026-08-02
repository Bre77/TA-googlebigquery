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

"""Script: the modular-input entry point. Deliberately has no .service property;
unsupported client surface must fail immediately rather than half-work.
"""

from abc import ABCMeta, abstractmethod
import sys
import xml.etree.ElementTree as ET

from ._protocol import EventWriter, InputDefinition, ValidationDefinition


class Script(metaclass=ABCMeta):
    """Base class for a modular input. Subclasses set APP and override get_scheme,
    stream_events, and optionally validate_input.
    """

    APP = None

    def __init__(self):
        self._input_definition = None
        self._validation_definition = None
        self._context = None

    def run(self, args):
        return self.run_script(args, EventWriter(), sys.stdin)

    def run_script(self, args, event_writer, input_stream):
        try:
            if len(args) == 1:
                self._input_definition = InputDefinition.parse(input_stream)
                self.stream_events(self._input_definition, event_writer)
                event_writer.close()
                return 0

            if str(args[1]).lower() == "--scheme":
                scheme = self.get_scheme()
                if scheme is None:
                    event_writer.log(
                        EventWriter.FATAL, "Modular input script returned a null scheme."
                    )
                    return 1
                event_writer.write_xml_document(scheme.to_xml())
                return 0

            if args[1].lower() == "--validate-arguments":
                self._validation_definition = ValidationDefinition.parse(input_stream)
                try:
                    self.validate_input(self._validation_definition)
                    return 0
                except Exception as e:
                    root = ET.Element("error")
                    ET.SubElement(root, "message").text = str(e)
                    event_writer.write_xml_document(root)
                    return 1

            event_writer.log(
                EventWriter.ERROR,
                "Invalid arguments to modular input script:" + " ".join(args),
            )
            return 1

        except Exception as e:
            event_writer.log_exception(str(e))
            return 1

    @property
    def context(self):
        """The InvocationContext for this run, built lazily from the parsed metadata
        and this subclass's APP. None until an input or validation definition is parsed.
        """
        if self._context is not None:
            return self._context

        if self._input_definition is not None:
            metadata = self._input_definition.metadata
        elif self._validation_definition is not None:
            metadata = self._validation_definition.metadata
        else:
            return None

        # Imported here: context.py pulls in _rest/credentials, which stream_events-only
        # scripts (e.g. TA-icmp) should never need to load.
        from ..context import InvocationContext

        self._context = InvocationContext.from_metadata(metadata, app=self.APP)
        return self._context

    @abstractmethod
    def get_scheme(self):
        """Return a Scheme object describing this modular input's arguments."""

    def validate_input(self, definition):
        """External validation hook. Raise to fail validation; the default always passes."""

    @abstractmethod
    def stream_events(self, inputs, ew):
        """Stream events into Splunk via ew. inputs is the parsed InputDefinition."""
