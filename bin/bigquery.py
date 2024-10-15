import os
import sys
import json
import time
import base64

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))
from splunklib.modularinput import Argument, Event, EventWriter, Script, Scheme
from google.cloud import bigquery
from google.oauth2.service_account import Credentials
from google.api_core.exceptions import BadRequest


def fix_types(inputval):
    # this helper function converts BigQuery output into a format that is JSON-serialisable
    inputval_type = type(inputval).__name__
    if inputval_type in ["NoneType"]:
        # None is not useful, so return blank.
        return ""
    elif inputval_type in ["int", "bool", "str", "float"]:
        # for these types, no need to do anything
        return inputval
    elif inputval_type in ["Decimal"]:
        return float(inputval)
    elif inputval_type in ["bytes"]:
        return str(base64.b64encode(inputval))[
            2:-1
        ]  # trim off the leading b' and trailing '
    elif inputval_type in ["datetime", "date", "time"]:
        return str(inputval)
    elif inputval_type == "list":
        # we need to process each subelement
        new_list = []
        for element in inputval:
            new_list.append(fix_types(element))
        return new_list
    elif inputval_type == "dict":
        new_dict = {}
        for key in inputval.keys():
            new_dict[key] = fix_types(inputval[key])
        return new_dict
    else:
        raise Exception(
            "Encountered unexpected type: {typename}".format(typename=inputval_type)
        )


def integer_to_epoch(ts):
    while ts > 9999999999:
        ts = ts / 10
    return ts


def timestamp_to_epoch(ts):
    return ts.timestamp()


class Input(Script):
    MASK = "<encrypted>"
    APP = __file__.split(os.sep)[-3]

    def get_scheme(self):

        scheme = Scheme("Google BigQuery")
        scheme.description = (
            "Executes a query against Google BigQuery and loads each row as an event"
        )
        scheme.use_external_validation = False
        scheme.streaming_mode_xml = True
        scheme.use_single_instance = False

        scheme.add_argument(
            Argument(
                name="query",
                title="Query (use %checkpoint% where required)",
                data_type=Argument.data_type_string,
                required_on_create=True,
            )
        )
        scheme.add_argument(
            Argument(
                name="service_account",
                title="Service Account",
                description="GCP Service Account as a single line of JSON",
                data_type=Argument.data_type_string,
                required_on_create=True,
            )
        )
        scheme.add_argument(
            Argument(
                name="time_field",
                title="Time Field",
                description="The column that contains the event time",
                data_type=Argument.data_type_string,
                required_on_create=False,
            )
        )
        scheme.add_argument(
            Argument(
                name="checkpoint_field",
                title="Checkpoint Field",
                description="The column that increases in newer events, last value will replace %checkpoint% in query.",
                data_type=Argument.data_type_string,
                required_on_create=False,
            )
        )
        scheme.add_argument(
            Argument(
                name="checkpoint_start",
                title="Checkpoint start value",
                description="Start sync from a certain point or use a TIMESTAMP type field you can set a different value here, for example 1970-01-01 00:00:00 UTC",
                data_type=Argument.data_type_string,
                required_on_create=False,
            )
        )
        scheme.add_argument(
            Argument(
                name="blacklist",
                title="Field Blacklist",
                description="Comma seperated list of columns that should not be indexed (such as the checkpoint field)",
                data_type=Argument.data_type_string,
                required_on_create=False,
            )
        )
        return scheme

    def stream_events(self, inputs, ew):
        self.service.namespace["app"] = self.APP

        # Get Variables
        input_name, input_items = inputs.inputs.popitem()
        kind, name = input_name.split("://")
        checkpointfile = os.path.join(
            self._input_definition.metadata["checkpoint_dir"],
            "".join(
                [c for c in name if c.isalpha() or c.isdigit() or c == " "]
            ).rstrip(),
        )

        query = input_items["query"]
        time_field = input_items.get("time_field")
        checkpoint_field = input_items.get("checkpoint_field")
        checkpoint_start = input_items.get("checkpoint_start","0")
        blacklist = (input_items.get("blacklist") or "").split(",")

        # Password Encryption
        updates = {}

        for item in ["service_account"]:
            stored_password = [
                x
                for x in self.service.storage_passwords
                if x.username == item and x.realm == name
            ]
            if input_items[item] == self.MASK:
                if len(stored_password) != 1:
                    ew.log(
                        EventWriter.ERROR,
                        f'stanza="{name}" message="Encrypted {item} was not found for {input_name}, reconfigure its value."',
                    )
                    return
                input_items[item] = stored_password[0].content.clear_password
            else:
                if stored_password:
                    self.service.storage_passwords.delete(username=item, realm=name)
                self.service.storage_passwords.create(input_items[item], item, name)
                updates[item] = self.MASK
        if updates:
            self.service.inputs.__getitem__((name, kind)).update(**updates)

        # Apply Checkpoint
        checkpoint_value = None
        if checkpoint_field:
            try:
                with open(checkpointfile, "r") as file:
                    checkpoint_value = file.read()
            except FileNotFoundError:
                checkpoint_value = checkpoint_start
            query = query.replace("%checkpoint%", checkpoint_value)

        # Do the Query
        service_account = json.loads(input_items["service_account"])
        project_id = service_account["project_id"]
        credentials = Credentials.from_service_account_info(
            service_account,
            scopes=[
                'https://www.googleapis.com/auth/cloud-platform',            
                "https://www.googleapis.com/auth/drive",
                "https://www.googleapis.com/auth/bigquery"
            ]
        )

        ew.log(EventWriter.INFO, f'stanza="{name}" query="{query}"')
        try:
            client = bigquery.Client(project_id, credentials)
        except Exception as e:
            ew.log(
                EventWriter.ERROR,
                f'stanza="{name}" message="Unable to execute query as unable to obtain BigQuery client based on specified project ID and credentials." error="{e}"',
            )
            sys.exit(1)

        query_epoch = time.time()
        try:
            query_job = client.query(query)
            results = query_job.result()
        except BadRequest as br:
            ew.log(
                EventWriter.ERROR,
                f'stanza="{name}" message="BadRequest" error="{json.dumps(br.errors)}"',
            )
            sys.exit(1)
        except Exception as e:
            ew.log(EventWriter.ERROR, f'stanza="{name}" error="{e}"')
            sys.exit(2)

        # Get Schema
        schema_obj = results.schema

        # Verify whether the timestamp field exists
        time_field_index = 0
        if time_field is not None:
            for field in schema_obj:
                if field.name == time_field:
                    if field.field_type == "TIMESTAMP":
                        time_func = timestamp_to_epoch
                        break
                    elif field.field_type == "INTEGER":
                        time_func = integer_to_epoch
                        break
                    else:
                        ew.log(
                            EventWriter.ERROR,
                            f"stanza=\"{name}\" message=\"The specified timestamp column '{time_field}' exists, but is of type '{field.field_type}'.\"",
                        )
                        # ew.log(EventWriter.ERROR,schema_obj)
                        sys.exit(3)
                time_field_index += 1
            else:
                ew.log(
                    EventWriter.ERROR,
                    f'stanza="{name}" message="The specified timestamp column \'{time_field}\' was not returned in the query results."',
                )
                # ew.log(EventWriter.ERROR,schema_obj)
                sys.exit(4)
        else:
            ew.log(
                EventWriter.WARN,
                'stanza="{name}" message="No time field is being used"',
            )

        checkpoint_next = checkpoint_value
        if checkpoint_field is not None:
            for field in schema_obj:
                if field.name == checkpoint_field:
                    break
            else:
                ew.log(
                    EventWriter.ERROR,
                    f'stanza="{name}" message="The specified checkpoint column \'{checkpoint_field}\' was not returned in the query results."',
                )
                # ew.log(EventWriter.ERROR,schema_obj)
                sys.exit(5)
        else:
            ew.log(
                EventWriter.WARN,
                'stanza="{name}" message="No checkpoint field is being used"',
            )

        if input_items["sourcetype"].endswith("tsv"):
            for page in results.pages:
                for row in page:
                    # Get time
                    if time_field is not None:
                        event_time = time_func(row[time_field])
                    else:
                        # If no time_field is specified then we will simply reuse the query epoch as the event_timestamp that is written to Splunk
                        event_time = query_epoch

                    # Find next checkpoint
                    if checkpoint_field is not None:
                        checkpoint_next = max(
                            checkpoint_next, str(row[checkpoint_field])
                        )

                    # Write the event
                    ew.write_event(
                        Event(
                            time=event_time,
                            data="\t".join(
                                [str(fix_types(value)) for value in row.values()]
                            )
                            + "\n",
                        )
                    )
        else:
            for page in results.pages:
                ew.log(
                    EventWriter.DEBUG,
                    f'stanza="{name}" message="Getting next page, checkpoint is {checkpoint_next}"',
                )
                for row in page:
                    # Turn the rows in to a dictionary with correct types
                    data = {}
                    for column, value in zip(results.schema, row.values()):
                        if (
                            value is not None
                            and value != []
                            and column.name not in blacklist
                        ):
                            data[column.name] = fix_types(value)

                    # Get time
                    if time_field is not None:
                        event_time = time_func(row[time_field])
                    else:
                        # If no time_field is specified then we will simply reuse the query epoch as the event_timestamp that is written to Splunk
                        event_time = query_epoch

                    # Find next checkpoint
                    if checkpoint_field is not None:
                        checkpoint_next = max(
                            checkpoint_next, str(row[checkpoint_field])
                        )

                    # Write the event
                    ew.write_event(
                        Event(
                            time=event_time,
                            data=json.dumps(data, separators=(",", ":")),
                        )
                    )

        # Save Checkpoint if its not the default
        if checkpoint_field is not None:
            if checkpoint_next != checkpoint_value:
                ew.log(
                    EventWriter.INFO,
                    f'stanza="{name}" message="Saving checkpoint {checkpoint_next}"',
                )
                with open(checkpointfile, "w") as file:
                    file.write(checkpoint_next)

        ew.close()


if __name__ == "__main__":
    exitcode = Input().run(sys.argv)
    sys.exit(exitcode)
