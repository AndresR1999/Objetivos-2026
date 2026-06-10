WITH ultimos AS (
    SELECT 
        REGEXP_SUBSTR(start_location_wcs, 'Aisle[0-9]+') AS AISLE,
        MAX(CAST(FINISHED_TIME AS DATE)) AS ULTIMO_FIN
    FROM VW_HOST_TRACE_MOVEMENTS@dbtgwp
    WHERE start_location_wcs LIKE '/Miniload/Aisle%'
      AND final_errorcode NOT IN ('Expired', 'SourcePositionBlocked')
      AND finishing_time IS NULL
    GROUP BY REGEXP_SUBSTR(start_location_wcs, 'Aisle[0-9]+')
),
movimientos_por_estado AS (
    SELECT 
        REGEXP_SUBSTR(origin, 'Aisle[0-9]+') AS AISLE,
        SUM(CASE WHEN status = 'Created' THEN 1 ELSE 0 END) AS ACTIVE_CREATED,
        SUM(CASE WHEN status = 'SentToMFS' THEN 1 ELSE 0 END) AS ACTIVE_SENT,
        SUM(CASE WHEN status = 'Executing' THEN 1 ELSE 0 END) AS ACTIVE_EXECUTING
    FROM VW_HOST_ACTIVE_MOVEMENTS@dbtgwp
    WHERE origin LIKE '/Miniload/Aisle%'
      AND status IN ('Created', 'SentToMFS', 'Executing')
    GROUP BY REGEXP_SUBSTR(origin, 'Aisle[0-9]+')
)
SELECT 
    u.AISLE,
    TO_CHAR(u.ULTIMO_FIN, 'dd/mm/yyyy hh24:mi:ss') AS ULTIMO_FINISHED,
    ROUND((CAST(SYSDATE AS DATE) - u.ULTIMO_FIN) * 24 * 60, 2) AS MINUTOS_SIN_COMPLETAR,
    NVL(m.ACTIVE_CREATED, 0) AS ACTIVE_CREATED,
    NVL(m.ACTIVE_SENT, 0) AS ACTIVE_SENT,
    NVL(m.ACTIVE_EXECUTING, 0) AS ACTIVE_EXECUTING
FROM ultimos u
JOIN movimientos_por_estado m
  ON m.AISLE = u.AISLE
WHERE (CAST(SYSDATE AS DATE) - u.ULTIMO_FIN) * 24 * 60 >= 10
ORDER BY MINUTOS_SIN_COMPLETAR DESC
