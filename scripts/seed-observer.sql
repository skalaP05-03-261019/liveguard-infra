-- Disposable local integration DB only. Extra viewer for hidden-text isolation checks.
INSERT INTO platform.users (id, username, password_hash, nickname, role)
SELECT '10000000-0000-4000-8000-000000000099', 'integration-observer', password_hash, '통합검증 시청자', 'VIEWER'
FROM platform.users WHERE username = 'viewer'
ON CONFLICT (id) DO NOTHING;
INSERT INTO platform.channel_members (channel_id, user_id, member_role)
VALUES ('20000000-0000-4000-8000-000000000001', '10000000-0000-4000-8000-000000000099', 'VIEWER')
ON CONFLICT (channel_id, user_id) DO NOTHING;
