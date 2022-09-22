# Google BigQuery Technical Add-on

Written by Justin Lai and Brett Adams

Queries Google BigQuery and indexes the result.

Python dependencies included.

Splunkbase link: https://splunkbase.splunk.com/app/5692/
Github link: https://github.com/Bre77/TA-googlebigquery

## How to use

### Query

The query that is run. The special string `"%checkpoint%"` (without quotes) will be replaced with the largest value seen in the checkpoint field if set.

### Service Account

A Google Service account in JSON format, with new lines removed.

```sh
jq -c . service_account.json
```

### Time Field

The field to use as the timestamp. The TIMESTAMP data type is recommended, but any number will be converted into a timestamp by dividing by 10 until the integral part has 10 digits.
`TIMESTAMP_MICROS(event_info.timestamp_usec) as time`

### Checkpoint Field

The field whose largest value will be used as the `%checkpoint%` in the next search. The initial value is 0 and will be compared using `max()`, so you should to convert TIMESTAMP fields to a number using UNIX_MICROS and use that for checkpoints.

You can do this with a subquery such as:

```sql
SELECT * FROM (
    SELECT UNIX_MICROS(timestamp_column) as timestamp_column_micros, * FROM `table`
) WHERE timestamp_column_micros > %checkpoint% 
```

### Field Blacklist

If you have created extra fields like time and checkpoint, you can remove them by adding them to the field blacklist.

## Example

Query:

```sql
SELECT TIMESTAMP_MICROS(event_info.timestamp_usec) as time, *
FROM `project.gmail_logs_dataset.daily_*`
WHERE event_info.timestamp_usec > %checkpoint%
AND time < TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 600 SECOND)
```

Time Field: `time`

Checkpoint Field: `event_info.timestamp_usec`

Field Blacklist: `time`

## Troubleshooting

If you're not getting any data show up in the index (especially when using checkpoints), have a look at the logs in your Splunk instance with this search:

```spl
index="_internal" bigquery source="*/splunkd.log"
```

## Binary File Declaration

* `lib/google/protobuf/internal/_api_implementation.cpython-37m-x86_64-linux-gnu.so`
* `lib/google/protobuf/pyext/_message.cpython-37m-x86_64-linux-gnu.so`
* `lib/google_crc32c/_crc32c.cpython-37m-x86_64-linux-gnu.so`
* `lib/grpc/_cython/cygrpc.cpython-37m-x86_64-linux-gnu.so`
