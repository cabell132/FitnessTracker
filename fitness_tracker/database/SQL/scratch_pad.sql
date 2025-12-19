-- INSERT OR IGNORE INTO MetricItem(metric_id, value, date, apple_id)
-- SELECT 1 as metric_id, value, timestamp, id
-- FROM AppleHealthDataRecord
-- WHERE data_type_id = 119

INSERT OR IGNORE INTO MetricItem(metric_id, value, date, workout_id)
SELECT 
	2 as metric_id,
    ROUND(COALESCE(SUM(a.value), 0),0) AS value,
    w.end_date AS date,
    w.id AS workout_id
FROM 
    Workout w
LEFT JOIN 
    AppleHealthDataRecord a 
    ON a.timestamp BETWEEN w.start_date AND w.end_date
WHERE a.data_type_id = 1
GROUP BY 
    w.id, w.title, w.start_date, w.end_date
HAVING COALESCE(SUM(a.value), 0) > 200