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

"""Modular-input XML protocol types: Argument, Event, Scheme, InputDefinition,
ValidationDefinition, EventWriter. Signatures and XML shape match splunklib.modularinput 2.1.1.
"""

from io import TextIOBase
import sys
import traceback
import xml.etree.ElementTree as ET


def _write_element(stream, element, errors="strict"):
    payload = ET.tostring(element)
    if isinstance(stream, TextIOBase):
        payload = payload.decode("utf-8", errors=errors)
    stream.write(payload)
    stream.flush()


def _parse_parameters(param_node):
    if param_node.tag == "param":
        return param_node.text
    if param_node.tag == "param_list":
        return [value.text for value in param_node]
    raise ValueError(f"Invalid configuration scheme, {param_node.tag} tag unexpected.")


def _parse_xml_data(parent_node, child_node_tag):
    data = {}
    for child in parent_node:
        child_name = child.get("name")
        if child.tag == child_node_tag:
            if child_node_tag == "stanza":
                data[child_name] = {"__app": child.get("app", None)}
                for param in child:
                    data[child_name][param.get("name")] = _parse_parameters(param)
        elif parent_node.tag == "item":
            data[child_name] = _parse_parameters(child)
    return data


class Argument:
    """An argument to a modular-input kind, used by Scheme.add_argument."""

    data_type_boolean = "BOOLEAN"
    data_type_number = "NUMBER"
    data_type_string = "STRING"

    def __init__(
        self,
        name,
        description=None,
        validation=None,
        data_type=data_type_string,
        required_on_edit=False,
        required_on_create=False,
        title=None,
    ):
        self.name = name
        self.description = description
        self.validation = validation
        self.data_type = data_type
        self.required_on_edit = required_on_edit
        self.required_on_create = required_on_create
        self.title = title

    def add_to_document(self, parent):
        arg = ET.SubElement(parent, "arg")
        arg.set("name", self.name)

        if self.title is not None:
            ET.SubElement(arg, "title").text = self.title
        if self.description is not None:
            ET.SubElement(arg, "description").text = self.description
        if self.validation is not None:
            ET.SubElement(arg, "validation").text = self.validation

        for name, value in (
            ("data_type", self.data_type),
            ("required_on_edit", self.required_on_edit),
            ("required_on_create", self.required_on_create),
        ):
            ET.SubElement(arg, name).text = str(value).lower()

        return arg


class Scheme:
    """Metadata for a modular-input kind: title, options, and a list of Arguments."""

    streaming_mode_simple = "SIMPLE"
    streaming_mode_xml = "XML"

    def __init__(self, title):
        self.title = title
        self.description = None
        self.use_external_validation = True
        self.use_single_instance = False
        self.streaming_mode = Scheme.streaming_mode_xml
        self.arguments = []

    def add_argument(self, arg):
        self.arguments.append(arg)

    def to_xml(self):
        root = ET.Element("scheme")
        ET.SubElement(root, "title").text = self.title

        if self.description is not None:
            ET.SubElement(root, "description").text = self.description

        for name, value in (
            ("use_external_validation", self.use_external_validation),
            ("use_single_instance", self.use_single_instance),
            ("streaming_mode", self.streaming_mode),
        ):
            ET.SubElement(root, name).text = str(value).lower()

        endpoint = ET.SubElement(root, "endpoint")
        args = ET.SubElement(endpoint, "args")
        for arg in self.arguments:
            arg.add_to_document(args)

        return root


class Event:
    """One event, or event fragment, to be written by a modular input to Splunk."""

    def __init__(
        self,
        data=None,
        stanza=None,
        time=None,
        host=None,
        index=None,
        source=None,
        sourcetype=None,
        done=True,
        unbroken=True,
    ):
        self.data = data
        self.done = done
        self.host = host
        self.index = index
        self.source = source
        self.sourceType = sourcetype
        self.stanza = stanza
        self.time = time
        self.unbroken = unbroken

    def write_to(self, stream):
        if self.data is None:
            raise ValueError(
                "Events must have at least the data field set to be written to XML."
            )

        event = ET.Element("event")
        if self.stanza is not None:
            event.set("stanza", self.stanza)
        event.set("unbroken", str(int(self.unbroken)))

        if self.time is not None:
            ET.SubElement(event, "time").text = str(self.time)

        for node, value in (
            ("source", self.source),
            ("sourcetype", self.sourceType),
            ("index", self.index),
            ("host", self.host),
            ("data", self.data),
        ):
            if value is not None:
                ET.SubElement(event, node).text = value

        if self.done:
            ET.SubElement(event, "done")

        _write_element(stream, event)


class InputDefinition:
    """The stanza configuration splunkd passes to a modular-input script on stdin."""

    def __init__(self):
        self.metadata = {}
        self.inputs = {}

    def __eq__(self, other):
        if not isinstance(other, InputDefinition):
            return False
        return self.metadata == other.metadata and self.inputs == other.inputs

    @staticmethod
    def parse(stream):
        definition = InputDefinition()
        root = ET.parse(stream).getroot()
        for node in root:
            if node.tag == "configuration":
                definition.inputs = _parse_xml_data(node, "stanza")
            else:
                definition.metadata[node.tag] = node.text
        return definition


class ValidationDefinition:
    """The proposed-input XML splunkd passes for external validation."""

    def __init__(self):
        self.metadata = {}
        self.parameters = {}

    def __eq__(self, other):
        if not isinstance(other, ValidationDefinition):
            return False
        return self.metadata == other.metadata and self.parameters == other.parameters

    @staticmethod
    def parse(stream):
        definition = ValidationDefinition()
        root = ET.parse(stream).getroot()
        for node in root:
            if node.tag == "item":
                definition.metadata["name"] = node.get("name")
                definition.parameters = _parse_xml_data(node, "")
            else:
                definition.metadata[node.tag] = node.text
        return definition


class EventWriter:
    """Writes events and log messages to Splunk from a modular input."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"
    FATAL = "FATAL"

    def __init__(self, output=sys.stdout, error=sys.stderr):
        self._out = output
        self._err = error
        self.header_written = False
        self._closed = False

    def write_event(self, event):
        if not self.header_written:
            self._out.write("<stream>")
            self.header_written = True
        event.write_to(self._out)

    def log(self, severity, message):
        self._err.write(f"{severity} {message}\n")
        self._err.flush()

    def log_exception(self, message, exception=None, severity=None):
        if exception is not None:
            tb_str = traceback.format_exception(type(exception), exception, exception.__traceback__)
        else:
            tb_str = traceback.format_exc()

        if severity is None:
            severity = EventWriter.ERROR

        self._err.write(("%s %s - %s" % (severity, message, tb_str)).replace("\n", " "))
        self._err.flush()

    def write_xml_document(self, document):
        _write_element(self._out, document, errors="replace")

    def close(self):
        """Write the closing </stream> tag. Idempotent: a deliberate divergence from
        SDK 2.1.1, whose close() writes </stream> on every call.
        """
        if self._closed:
            return
        self._closed = True
        if self.header_written:
            self._out.write("</stream>")
        self._out.flush()
