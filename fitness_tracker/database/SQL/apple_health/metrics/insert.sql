INSERT OR IGNORE INTO MetricItem(metric_id, value, date, apple_id)
SELECT 1 as metric_id, value, timestamp, id
FROM AppleHealthDataRecord
WHERE data_type_id = 119