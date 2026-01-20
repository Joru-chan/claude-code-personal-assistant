# Pantry Tool Enhancement Plan

**Status:** Triaging  
**Priority:** High  
**Estimated Time:** 2-3 hours

## Problem
Receipt tool creates duplicate entries instead of updating existing pantry items when the same item is added from multiple receipts.

## Current State (Commit a230b82)
✅ Extended property map for all Pantry fields  
✅ Helper function: `_fuzzy_match_score(name1, name2)` - calculates similarity (0-1)  
✅ Helper function: `_append_price_to_notes()` - formats price history as JSON  
⏳ Not yet wired up or integrated

## Enhancement Goals

### 1. Advanced Fuzzy Matching
**Goal:** Match "Organic Bananas" with "Bananas Organic", "Almond Milk" with "Milk - Almond"

**Implementation:**
- Use existing `_fuzzy_match_score()` function
- Update `_query_by_title()` to return all items, not just exact matches
- Score each existing item against new item
- Match threshold: 0.7+ (configurable)
- For multiple matches, pick highest score

**Code Location:** `vm_server/tools/receipt_photo_pantry_inventory.py` line ~260

### 2. Smart Quantity Updates
**Goal:** Add to existing quantity instead of creating duplicate

**Implementation:**
- When fuzzy match found (score > threshold):
  - Fetch existing item properties
  - Calculate new quantity = existing + new
  - Update item with PATCH request
  - Return as "updated" not "created"
- Track both created and updated items in response

**Code Location:** ~line 420 in the create loop

### 3. Price History Database
**Goal:** Track price changes over time and across stores

**Option A (Simple):** Store in Notes field as JSON
- Already have `_append_price_to_notes()` helper
- Format: `[{price: 3.99, date: "2026-01-20", store: "Whole Foods"}, ...]`
- Quick to implement, no schema changes

**Option B (Advanced):** Separate Price History database
- Create new database: "Price History"
- Properties:
  - Item (relation to Pantry)
  - Price (number)
  - Date (date)
  - Store (text)
  - Unit (text)
- Benefits: Clean data model, queryable, graphable
- Requires: Database setup, relation handling

**Recommendation:** Start with Option A, migrate to B if needed

### 4. Better Duplicate Detection
**Goal:** Prevent duplicates from same receipt

**Implementation:**
- Check for items with matching:
  - Name (fuzzy match)
  - Store
  - Purchase Date (same day)
- If found, update instead of create
- Add deduplication before API calls

**Code Location:** Before the create loop (~line 410)

## Implementation Steps

1. **Phase 1: Fuzzy Matching (30 min)**
   - Modify `_query_by_title()` to return all items
   - Add fuzzy scoring loop
   - Return best match if score > 0.7

2. **Phase 2: Quantity Updates (30 min)**
   - Add PATCH logic when match found
   - Update existing item quantity
   - Track "updated" items separately from "created"

3. **Phase 3: Price History - Simple (20 min)**
   - Wire up `_append_price_to_notes()` 
   - Extract price from items
   - Append to notes field on create/update

4. **Phase 4: Better Deduplication (20 min)**
   - Add pre-check for same-receipt duplicates
   - Group by name+store+date
   - Merge quantities before API calls

5. **Phase 5: Testing (30 min)**
   - Test with duplicate items
   - Test with similar names
   - Test price history accumulation
   - Verify quantity updates work
   - Deploy and test with Poke

## Testing Scenarios

```bash
# Test 1: Exact duplicate detection
items: ["Bananas", "Bananas"]
expected: 1 item, quantity = 2

# Test 2: Fuzzy match
existing: "Organic Bananas"
new: "Bananas Organic"
expected: Update existing, not create new

# Test 3: Price history
receipt 1: Bananas $3.99 at Whole Foods
receipt 2: Bananas $4.29 at Trader Joes
expected: Notes show both prices

# Test 4: Quantity accumulation
existing: Bananas qty=2
new: Bananas qty=3
expected: Updated qty=5
```

## Success Criteria

✅ No duplicates created for same items  
✅ Fuzzy matching works for common variations  
✅ Quantities accumulate correctly  
✅ Price history tracked over time  
✅ Tool still works with Poke  
✅ Response shows "created" vs "updated" items clearly

## Risks & Mitigation

**Risk:** False positive matches (matching different items)  
**Mitigation:** Adjustable threshold, require high similarity score

**Risk:** Losing price data with simple notes approach  
**Mitigation:** JSON format is parseable, can migrate to DB later

**Risk:** Breaking existing functionality  
**Mitigation:** Preserve backward compatibility, add flags for new features

## Future Enhancements

- Machine learning for better categorization
- Expiration date estimation based on category
- Shopping list generation from pantry levels
- Price comparison across stores
- Nutritional information lookup
