# Segments Integration Test Checklist

This document provides a comprehensive test checklist for validating the Contacts + Segments integration.

## Test Environment Setup

- [ ] Backend server running at `http://localhost:8000`
- [ ] Frontend dev server running at `http://localhost:3000`
- [ ] PostgreSQL database accessible
- [ ] Redis accessible
- [ ] Test workspace with contacts data

## 1. Segment Preview Count Tests

### Basic Filters
- [ ] **Name filter**: Create segment with `name` equals "John" → verify count matches contacts with name "John"
- [ ] **Name contains**: Create segment with `name` contains "test" → verify count matches partial matches
- [ ] **Phone filter**: Create segment with `phone` equals "+1234567890" → verify exact match
- [ ] **Created date**: Filter by `created_at` before/after specific date → verify date filtering works

### Nested Filters
- [ ] **AND group**: Create segment with two conditions using AND → verify intersection of both conditions
- [ ] **OR group**: Create segment with two conditions using OR → verify union of both conditions
- [ ] **Deep nesting**: Create segment with 3+ levels of nested groups → verify correct SQL generation

### Tag Filtering
- [ ] **Has tag**: Create segment with `has_tag` operator → verify contacts with specified tag are matched
- [ ] **Multiple tags**: Create segment with multiple tag conditions using AND/OR → verify correct filtering

### Attribute Filtering
- [ ] **String attribute**: Filter by text attribute with `eq` operator → verify attribute matching
- [ ] **Numeric attribute**: Filter by number attribute with `gt/gte/lt/lte` → verify numeric comparison
- [ ] **Attribute contains**: Filter with `contains` operator → verify partial text matching
- [ ] **Missing attribute**: Filter by non-existent attribute key → verify graceful handling (no matches)

### Activity Filtering
- [ ] **Activity type filter**: Select activity filter (note: backend doesn't support this fully)
- [ ] **Activity with days**: Filter by activity within X days → verify temporal filtering

### Edge Cases
- [ ] **Empty segment**: Create segment with no conditions → verify behavior (should match all or none)
- [ ] **Invalid values**: Enter invalid date format → verify validation error shown
- [ ] **Large result set**: Preview segment matching 10000+ contacts → verify performance

## 2. Materialization Refresh Tests

### Materialization Trigger
- [ ] **Manual materialize**: Click "Materialize" button on segment → verify task queued
- [ ] **Materialization status**: Verify status changes from "idle" to "materializing" to "ready"
- [ ] **Refresh existing**: Click "Refresh" on already-materialized segment → verify re-materialization

### Batch Operations
- [ ] **Refresh all**: Click "Refresh All" → verify all segments start materializing
- [ ] **Concurrent materialization**: Materialize multiple segments simultaneously → verify no conflicts

### Error Handling
- [ ] **Failed materialization**: Trigger condition that causes SQL error → verify error message displayed
- [ ] **Timeout handling**: Start materialization on very large segment → verify timeout handling

## 3. Frontend/Backend DSL Compatibility Tests

### Structure Conversion
- [ ] **Simple condition**: Verify single condition converts correctly to backend format
- [ ] **Group conversion**: Verify group with children converts to backend `{ op, children }` format
- [ ] **ID stripping**: Verify frontend `id` fields are removed in backend payload

### Field Mapping
- [ ] **Field names**: Verify `name`, `phone`, `created_at` map correctly
- [ ] **Operator mapping**: Verify `eq`, `neq`, `contains`, `gt`, `gte`, `lt`, `lte` map correctly
- [ ] **Tag operator**: Verify `has_tag` operator with `tag` field works

### Unsupported Features
- [ ] **Activity filter warning**: Verify warning shown when activity filter used
- [ ] **Graceful degradation**: Verify activity filters are skipped rather than causing errors

## 4. User Interface Tests

### Loading States
- [ ] **Preview loading**: Show spinner while fetching preview count
- [ ] **Save loading**: Show loading state while saving segment
- [ ] **List loading**: Show skeleton while loading segment list
- [ ] **Materialization loading**: Show progress indicator during materialization

### Error Handling & Messages
- [ ] **Validation errors**: Invalid input shows clear error message
- [ ] **API errors**: Network errors show retry option
- [ ] **Timeout errors**: Long-running operations show timeout message
- [ ] **Error recovery**: Failed requests can be retried

### Retry Functionality
- [ ] **Preview retry**: "Retry" button appears on preview failure → click retries request
- [ ] **Save retry**: Failed save can be retried
- [ ] **Materialization retry**: Failed materialization can be retried

### Optimistic Updates
- [ ] **Segment creation**: New segment appears immediately in list (before confirmation)
- [ ] **Segment deletion**: Deleted segment removed immediately from list

### Pagination
- [ ] **Contact pagination**: Navigate through contacts using pagination controls
- [ ] **Segment list**: Multiple segments shown with proper scrolling/pagination

### Stale Data Handling
- [ ] **Auto-refresh**: Segment counts refresh when switching views
- [ ] **Manual refresh**: "Refresh" button updates data
- [ ] **Cache invalidation**: Creating new segment updates list automatically

## 5. API Integration Tests

### Endpoints
- [ ] `GET /api/segments` - List all segments
- [ ] `POST /api/segments` - Create new segment
- [ ] `POST /api/segments/preview` - Get segment preview count
- [ ] `POST /api/segments/{id}/materialize` - Trigger materialization

### Request/Response Validation
- [ ] **Request body**: Verify correct JSON structure sent
- [ ] **Response parsing**: Verify frontend correctly parses response
- [ ] **Status codes**: Proper handling of 200, 400, 401, 403, 500 responses

### Authentication
- [ ] **Auth required**: Requests without token return 401
- [ ] **Workspace isolation**: Segments only accessible within current workspace

## 6. Data Consistency Tests

### Database Integrity
- [ ] **Segment creation**: New segment appears in database
- [ ] **Segment update**: Modified segment reflected in database
- [ ] **Segment deletion**: Deleted segment removed from database

### Materialized Data
- [ ] **Size accuracy**: Materialized count matches actual contact count
- [ ] **Staleness detection**: Detect when materialization is outdated

## 7. Performance Tests

### Response Times
- [ ] **Preview response**: Preview loads in < 2 seconds for < 1000 contacts
- [ ] **List response**: Segment list loads in < 1 second
- [ ] **Materialization**: Materialization completes in reasonable time

### Large Data Handling
- [ ] **Large segment**: Create segment matching > 10000 contacts
- [ ] **Complex query**: Create segment with 10+ nested conditions

## 8. Browser Compatibility

- [ ] **Chrome**: All features work in latest Chrome
- [ ] **Firefox**: All features work in latest Firefox
- [ ] **Safari**: All features work in latest Safari
- [ ] **Edge**: All features work in latest Edge

## Test Account Setup

For testing, create a test workspace with:

```python
# Create test contacts
Test Contact 1: name="Alice", phone="+1234567890", tags=["vip"]
Test Contact 2: name="Bob", phone="+1234567891", tags=["vip", "newsletter"]
Test Contact 3: name="Charlie", phone="+1234567892", tags=["newsletter"]
Test Contact 4: name="Diana", phone="+1234567893", tags=[]

# Create test attributes
- company: "Acme Inc" (on contacts 1, 2)
- plan: "enterprise" (on contact 1)
- last_purchase: 1500.00 (on contact 2)
```

## Test Execution Notes

1. Always clear browser cache between test runs
2. Use incognito mode to avoid auth conflicts
3. Check browser console for JavaScript errors
4. Verify network tab shows correct API calls
5. Test on mobile viewport sizes

## Known Issues to Watch

- Activity filter shows warning but is silently skipped (not an error, but users may be confused)
- Large segments may timeout - need to implement polling for status
- No pagination on segment list - scrolls indefinitely
- Materialization status may not update in real-time without refresh