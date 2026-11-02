-- Employees whose linked login doesn't count for the employee record's property
-- READ-ONLY report: lists rows to clean up by hand; changes nothing.
--
-- Rankings count an employee for property P only if employees.property_id = P
-- and, when employees.user_id is set, that user is active, not deleted and has
-- users.property_id = P (RankingService employee_counts_for_property, 2026-11-02).
-- Every row below is an employee that rule leaves out, with the reason.
-- Unlinked employees (user_id IS NULL) are never listed.

SELECT
    e.tenant_id,
    e.id                         AS employee_id,
    e.first_name || ' ' || COALESCE(e.last_name, '') AS employee_name,
    e.is_active                  AS employee_is_active,
    e.property_id                AS employee_property_id,
    ep.name                      AS employee_property,
    u.id                         AS user_id,
    r.name                       AS user_role,
    u.property_id                AS user_property_id,
    up.name                      AS user_property,
    CASE
        WHEN u.id IS NULL                THEN 'linked user does not exist'
        WHEN u.deleted_at IS NOT NULL    THEN 'linked user is deleted'
        WHEN NOT u.is_active             THEN 'linked user is deactivated'
        WHEN u.property_id IS NULL       THEN 'linked user has no property'
        ELSE                                  'linked user belongs to another property'
    END                          AS reason,
    (SELECT COUNT(*) FROM employee_rankings er
      WHERE er.employee_id = e.id AND er.deleted_at IS NULL) AS stored_ranking_rows
FROM employees e
LEFT JOIN users u        ON u.id = e.user_id
LEFT JOIN roles r        ON r.id = u.role_id
LEFT JOIN properties ep  ON ep.id = e.property_id
LEFT JOIN properties up  ON up.id = u.property_id
WHERE e.user_id IS NOT NULL
  AND (
        u.id IS NULL
     OR u.deleted_at IS NOT NULL
     OR NOT u.is_active
     OR u.property_id IS DISTINCT FROM e.property_id
  )
ORDER BY e.tenant_id, ep.name, reason, employee_name;
