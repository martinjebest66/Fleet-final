# Auth-Gated App Testing Playbook (Emergent Google Auth)

## Step 1: Create Test User & Session
```
mongosh --eval "
use('test_database');
var userId = 'test-user-' + Date.now();
var sessionToken = 'test_session_' + Date.now();
db.users.insertOne({
  user_id: userId,
  email: 'test.user.' + Date.now() + '@example.com',
  name: 'Test User',
  picture: 'https://via.placeholder.com/150',
  created_at: new Date()
});
db.user_sessions.insertOne({
  user_id: userId,
  session_token: sessionToken,
  expires_at: new Date(Date.now() + 7*24*60*60*1000),
  created_at: new Date()
});
print('Session token: ' + sessionToken);
print('User ID: ' + userId);
"
```

## Step 2: Test Backend API
```
curl -X GET "https://your-app.com/api/auth/me" -H "Authorization: Bearer YOUR_SESSION_TOKEN"
```

## Step 3: Browser Testing
Set cookie session_token (httpOnly, secure, sameSite=None, path=/) then navigate to app.

## Checklist
- User document has user_id field (custom UUID)
- Session user_id matches user's user_id exactly
- All queries use {"_id": 0} projection
- API returns user data with user_id field (not 401/404)
- Browser loads dashboard (not login page)

## Success Indicators
- /api/auth/me returns user data
- Dashboard loads without redirect
- CRUD operations work

## Notes
- Emergent Auth: frontend redirects to https://auth.emergentagent.com/?redirect=<origin>/dashboard
- Backend exchanges session_id at https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data (X-Session-ID header)
- session_token cookie: httpOnly, secure=True, samesite="none", path="/", 7-day expiry
