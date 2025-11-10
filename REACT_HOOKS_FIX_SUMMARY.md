# React Hooks Violation Fix Summary

## Issue
The website was broken on the test server (Node 20) with the error:
```
Error: Rendered fewer hooks than expected. This may be caused by an accidental early return statement.
```

## Root Cause
The error was **NOT** caused by Node.js version differences (Node 20 vs Node 22), but by a **React 19 Hooks Rules violation** in the `MicrophoneButton` component.

### The Problem
In `frontend/src/components/MicrophoneButton.tsx`, there was an early return statement that happened AFTER hooks were called:

**Before (WRONG):**
```typescript
// Line 31-73: useRealtimeSTT() hook is called
const { ... } = useRealtimeSTT({ ... });

// Line 76-110: useEffect() hook is called
useEffect(() => { ... }, []);

// Line 112-115: Early return AFTER hooks (VIOLATES RULES OF HOOKS)
if (!isSTTEnabled) {
  return null;
}

// Line 117: useCallback() hook would be called
const handleToggleRecording = useCallback(...);
```

When `isSTTEnabled` changed from `true` to `false` (after the `useEffect` fetched STT settings), the component would re-render with fewer hooks being called, violating React's Rules of Hooks. React 19 is stricter about enforcing this rule.

## Solution
Moved the early return to happen AFTER all hooks have been called:

**After (CORRECT):**
```typescript
// All hooks are called first
const { ... } = useRealtimeSTT({ ... });
useEffect(() => { ... }, []);
const handleToggleRecording = useCallback(...);
// ... all other hooks ...

// Early return happens AFTER all hooks (COMPLIES WITH RULES OF HOOKS)
if (!isSTTEnabled) {
  return null;
}

return (
  // JSX...
);
```

## Files Modified
- `frontend/src/components/MicrophoneButton.tsx` - Moved the `if (!isSTTEnabled) return null;` check to be after all hooks

## Testing Instructions

### On Test Server (Node 20)
1. Navigate to your test server directory
2. Pull the latest changes:
   ```bash
   cd /path/to/kahani
   git pull
   ```

3. Rebuild the frontend (if using production mode):
   ```bash
   cd frontend
   rm -rf .next
   npm run build
   cd ..
   ```

4. Restart the server:
   ```bash
   # If using start-dev.sh
   ./start-dev.sh
   
   # If using start-prod.sh
   ./start-prod.sh
   ```

5. Open the website in your browser
6. Open the browser console (F12)
7. Navigate to a story page
8. **Verify:** No "Rendered fewer hooks" error appears in the console

### Test STT Functionality
1. Go to Settings → STT Settings
2. Toggle STT enabled/disabled
3. Return to a story page
4. **Verify:** 
   - When STT is enabled, the microphone button appears
   - When STT is disabled, the microphone button is hidden
   - No React errors occur during the toggle

### On Dev Server (Node 22)
Repeat the same tests to ensure no regression.

## Why It Appeared After NPM Upgrade
The issue appeared after upgrading to React 19.2.0 and Next.js 16.0.1. React 19 has stricter enforcement of the Rules of Hooks compared to React 18. The code violation existed before but wasn't caught by React 18's less strict checks.

## React Rules of Hooks Reminder
1. **Only call hooks at the top level** - Don't call hooks inside loops, conditions, or nested functions
2. **Only call hooks from React functions** - Call them from React function components or custom hooks
3. **Hooks must be called in the same order on every render** - This is why early returns before all hooks are called violates the rules

## Status
✅ **FIXED** - The early return has been moved to after all hooks, ensuring compliance with React's Rules of Hooks.



