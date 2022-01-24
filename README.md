# Google Big Query Technical Add-on

Written by Justin Lai and Brett Adams

Queries Google Big Query and indexes the result.

Python dependancies included

https://splunkbase.splunk.com/app/5692/

## How to use

### Query

The query that is run. The special string `"%checkpoint%"` (without quotes) will be replaced with the largest value seen in the checkpoint field if set.

### Service Account

A Google Service account in JSON format, with new lines removed.

```
jq -c . service_account.json
```

### Time Field

The field to use as the timestamp. The TIMESTAMP data type is recommended, but any number will be converted into a timestamp by dividing by 10 until the integral part has 10 digits.
`TIMESTAMP_MICROS(event_info.timestamp_usec) as time`

### Checkpoint Field

The field that's largest value will be used as the `%checkpoint%` in the next search. Will be converted to a string, so its recommended to convert TIMESTAMP fields to a number using TIMESTAMP_MICROS and use that for checkpoints.

### Field Blacklist

If you have created extra fields like time and checkpoint, you can remove them by adding them to the field blacklist.

## Example

Query:
```
SELECT TIMESTAMP_MICROS(event_info.timestamp_usec) as time, * `FROM project.gmail_logs_dataset.daily_*` WHERE event_info.timestamp_usec > %checkpoint% AND time < TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 600 SECOND)
```

Time Field: `time`

Checkpoint Field: `event_info.timestamp_usec`

Field Blacklist: `time`
