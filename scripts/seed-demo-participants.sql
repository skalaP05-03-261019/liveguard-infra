-- Local demo DB only. Copies viewer's password hash (normally liveguard-local).
-- Run with psql -v ON_ERROR_STOP=1; never use this on a shared/production DB.
BEGIN;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM platform.users WHERE username = 'viewer' AND role = 'VIEWER') THEN
    RAISE EXCEPTION 'Local viewer seed is required';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM platform.channels WHERE id = '20000000-0000-4000-8000-000000000001') THEN
    RAISE EXCEPTION 'Local channel A seed is required';
  END IF;
END $$;

INSERT INTO platform.users(id, username, password_hash, nickname, role)
SELECT ('10000000-0000-4000-8001-' || lpad(n::text, 12, '0'))::uuid,
       'p' || lpad(n::text, 3, '0'), password_hash,
       '참여자 ' || lpad(n::text, 3, '0'), 'VIEWER'
FROM platform.users CROSS JOIN generate_series(1, 200) n
WHERE username = 'viewer'
ON CONFLICT (id) DO NOTHING;

INSERT INTO platform.channel_members(channel_id, user_id, member_role)
SELECT '20000000-0000-4000-8000-000000000001'::uuid,
       ('10000000-0000-4000-8001-' || lpad(n::text, 12, '0'))::uuid, 'VIEWER'
FROM generate_series(1, 200) n
ON CONFLICT (channel_id, user_id) DO NOTHING;

DO $$
BEGIN
  IF (SELECT count(*)
      FROM generate_series(1, 200) n
      JOIN platform.users u ON u.id =
        ('10000000-0000-4000-8001-' || lpad(n::text, 12, '0'))::uuid
      JOIN platform.channel_members m ON m.user_id = u.id
        AND m.channel_id = '20000000-0000-4000-8000-000000000001'
      JOIN platform.users v ON v.username = 'viewer'
      WHERE u.username = 'p' || lpad(n::text, 3, '0')
        AND u.nickname = '참여자 ' || lpad(n::text, 3, '0')
        AND u.password_hash = v.password_hash
        AND u.role = 'VIEWER' AND m.member_role = 'VIEWER') <> 200 THEN
    RAISE EXCEPTION 'Participant seed conflict: expected 200 matching accounts and memberships; nothing committed';
  END IF;
END $$;

COMMIT;
