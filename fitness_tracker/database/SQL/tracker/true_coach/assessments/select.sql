SELECT mi.id, m.true_coach_id as assessment_id, mi.date, mi.value 
FROM MetricItem mi
JOIN Metric m on m.id = mi.metric_id
WHERE mi.true_coach_id IS NULL