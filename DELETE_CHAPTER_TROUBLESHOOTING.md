# Delete Chapter Troubleshooting Guide

## Issue: Delete button not working on test server

### Symptoms
- Delete button appears in UI
- Clicking it shows no error
- Nothing happens (no deletion, no error message)
- No logs in backend

### Possible Causes & Solutions

#### 1. Check Browser Console for Errors

Open browser DevTools (F12) and check the Console tab when clicking delete:

**Common errors:**
- **CORS error**: Backend needs to allow requests from your test server domain
- **401 Unauthorized**: Authentication token expired or invalid
- **Network error**: Backend not reachable from test server

**Solution for CORS:**
```bash
# In your .env file on test server, add:
CORS_ORIGINS=["http://your-test-server.com:6789", "http://localhost:6789"]
```

#### 2. Check Network Tab

In DevTools → Network tab:
- Look for the DELETE request to `/api/stories/{id}/chapters/{id}`
- Check the status code:
  - **404**: Story or chapter not found
  - **400**: Cannot delete (only chapter, or wrong branch)
  - **401**: Not authenticated
  - **403**: Not authorized (not your story)
  - **500**: Server error

#### 3. Check Backend Logs

With the new logging, you should see:
```
[CHAPTER:DELETE:START] story_id=X chapter_id=Y user_id=Z
```

If you don't see this, the request isn't reaching the backend.

**Check logs:**
```bash
# Docker
docker logs kahani-backend | grep "CHAPTER:DELETE"

# Local
tail -f backend/logs/kahani.log | grep "CHAPTER:DELETE"
```

#### 4. Verify Authentication

The delete endpoint requires authentication. Check:

```bash
# In browser console, check if token exists:
localStorage.getItem('token')

# If null or expired, log out and log back in
```

#### 5. Check if Button is Actually Visible

The button only shows when:
- There are **multiple chapters** (not just one)
- You have an active chapter selected

**Debug:**
```javascript
// In browser console:
console.log('Chapters:', chapters.length);
console.log('Active chapter:', activeChapter);
```

### Testing the Fix

1. **Pull latest code** on test server:
   ```bash
   git pull origin dev
   ```

2. **Restart backend**:
   ```bash
   docker-compose restart backend
   # or
   ./start-dev.sh
   ```

3. **Clear browser cache** and reload

4. **Try deleting** and check logs:
   ```bash
   docker logs -f kahani-backend | grep "CHAPTER"
   ```

### Manual Verification

If UI still doesn't work, test the API directly:

```bash
# Get your auth token from browser localStorage
TOKEN="your-token-here"

# Try to delete a chapter
curl -X DELETE \
  "http://your-server:9876/api/stories/1/chapters/2" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json"
```

**Expected response:**
```json
{
  "message": "Chapter deleted successfully",
  "chapter_number": 2,
  "chapter_title": "Chapter 2",
  "scenes_deleted": 0,
  "batches_deleted": 0
}
```

---

## Fix Duplicate Chapters Script - PostgreSQL

### Issue
Script was trying to use SQLite when running in Docker with PostgreSQL.

### Solution
The script now:
1. ✅ Reads `DATABASE_URL` from environment (works in Docker)
2. ✅ Falls back to `.env` file (works locally)
3. ✅ Uses SQLAlchemy 2.0 syntax (no deprecation warnings)

### Usage in Docker

```bash
# The script automatically uses DATABASE_URL from environment
docker exec -it kahani-backend python /app/fix_duplicate_chapters_standalone.py
```

### Expected Output

```
================================================================================
DUPLICATE CHAPTER FIXER - Standalone Version
================================================================================

Using DATABASE_URL from environment
Connecting to database: postgresql://user:pass@postgres:5432/kahani

Found 1 story/branch combinations with duplicate chapters:
...
```

### If Still Getting Errors

1. **Check DATABASE_URL is set in container:**
   ```bash
   docker exec kahani-backend env | grep DATABASE_URL
   ```

2. **Check PostgreSQL is running:**
   ```bash
   docker ps | grep postgres
   ```

3. **Check connection from backend:**
   ```bash
   docker exec kahani-backend python -c "import os; print(os.environ.get('DATABASE_URL'))"
   ```

---

## Quick Fixes Summary

### For Delete Button Not Working:
1. Check browser console for errors
2. Check Network tab for failed requests
3. Verify authentication (re-login if needed)
4. Check backend logs for `[CHAPTER:DELETE:START]`
5. Ensure multiple chapters exist (button only shows with 2+)

### For Duplicate Chapters Script:
1. Use `fix_duplicate_chapters_standalone.py` (not the other one)
2. Run in Docker: `docker exec -it kahani-backend python /app/fix_duplicate_chapters_standalone.py`
3. Script auto-detects PostgreSQL from environment

---

## Still Having Issues?

1. **Check the logs** - they now have detailed tracing
2. **Test the API directly** with curl (see above)
3. **Verify your setup**:
   - Backend running?
   - Frontend can reach backend?
   - Logged in with valid token?
   - Multiple chapters exist?

If all else fails, check the browser DevTools Console and Network tabs - they'll tell you exactly what's failing.

