-- Local integration fixture only. Do not run against production.
-- Reuses the local viewer password hash; never exports a credential.
INSERT INTO platform.users(id,username,password_hash,nickname,role)
SELECT ('10000000-0000-4000-8000-'||lpad(n::text,12,'0'))::uuid,
 'demo-viewer-'||n,password_hash,'시청자 '||n,'VIEWER'
FROM platform.users CROSS JOIN generate_series(10,19) n WHERE username='viewer'
ON CONFLICT(id) DO NOTHING;
INSERT INTO platform.channel_members(channel_id,user_id,member_role)
SELECT '20000000-0000-4000-8000-000000000001'::uuid,id,'VIEWER'
FROM platform.users WHERE username LIKE 'demo-viewer-%'
ON CONFLICT DO NOTHING;
