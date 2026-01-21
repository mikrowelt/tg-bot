#!/bin/bash
# =============================================================================
# Ban Detection Test Script
# =============================================================================
# This script tests the ban detection feature end-to-end.
#
# Prerequisites:
# 1. A test Telegram channel/group you control (to ban/unban accounts)
# 2. A test account on the staging system
# 3. Access to staging API
#
# Usage:
#   ./test_ban_detection.sh <account_id> <channel_username>
#
# Example:
#   ./test_ban_detection.sh 5 @my_test_channel
# =============================================================================

set -e

# Configuration
API_URL="${API_URL:-https://stage.kingssa.org/api}"
API_USER="${API_USER:-admin}"
API_PASS="${API_PASS:-admin123}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_ok() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

api_call() {
    local method=$1
    local endpoint=$2
    local data=$3

    if [ -n "$data" ]; then
        curl -s -X "$method" -u "$API_USER:$API_PASS" \
            -H "Content-Type: application/json" \
            -d "$data" \
            "$API_URL$endpoint"
    else
        curl -s -X "$method" -u "$API_USER:$API_PASS" \
            "$API_URL$endpoint"
    fi
}

# Check arguments
if [ $# -lt 2 ]; then
    echo "Usage: $0 <account_id> <channel_username>"
    echo ""
    echo "Example:"
    echo "  $0 5 @my_test_channel"
    echo ""
    echo "Environment variables:"
    echo "  API_URL  - API base URL (default: https://stage.kingssa.org/api)"
    echo "  API_USER - API username (default: admin)"
    echo "  API_PASS - API password (default: admin123)"
    exit 1
fi

ACCOUNT_ID=$1
CHANNEL=$2

echo "=============================================="
echo "  Ban Detection Test"
echo "=============================================="
echo ""
log_info "Account ID: $ACCOUNT_ID"
log_info "Channel: $CHANNEL"
log_info "API URL: $API_URL"
echo ""

# Step 1: Get account info
log_info "Step 1: Fetching account info..."
ACCOUNT_INFO=$(api_call GET "/accounts/$ACCOUNT_ID")
PROFILE_NAME=$(echo "$ACCOUNT_INFO" | python3 -c "import sys,json; print(json.load(sys.stdin).get('profile_name','unknown'))" 2>/dev/null || echo "unknown")
ACCOUNT_STATUS=$(echo "$ACCOUNT_INFO" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','unknown'))" 2>/dev/null || echo "unknown")

if [ "$PROFILE_NAME" = "unknown" ]; then
    log_error "Account $ACCOUNT_ID not found"
    exit 1
fi

log_ok "Account: $PROFILE_NAME (status: $ACCOUNT_STATUS)"
echo ""

# Step 2: Check current bans
log_info "Step 2: Checking current bans for this account..."
BANS=$(api_call GET "/bans")
ACCOUNT_BANS=$(echo "$BANS" | python3 -c "
import sys, json
bans = json.load(sys.stdin)
account_bans = [b for b in bans if b.get('account_id') == $ACCOUNT_ID]
print(f'Found {len(account_bans)} existing bans')
for b in account_bans:
    print(f\"  - {b.get('channel_target')} (by: {b.get('banned_by', 'unknown')})\")
" 2>/dev/null || echo "Error fetching bans")
echo "$ACCOUNT_BANS"
echo ""

# Step 3: Check if account is member of channel
log_info "Step 3: Checking channel membership..."
MEMBERSHIP_RESULT=$(api_call POST "/commands/execute" "{\"account_id\": $ACCOUNT_ID, \"command\": \"check_ban\", \"params\": {\"target\": \"$CHANNEL\"}}")
echo "$MEMBERSHIP_RESULT" | python3 -m json.tool 2>/dev/null || echo "$MEMBERSHIP_RESULT"
echo ""

IS_MEMBER=$(echo "$MEMBERSHIP_RESULT" | python3 -c "import sys,json; r=json.load(sys.stdin); print(r.get('result',{}).get('is_member', False))" 2>/dev/null || echo "false")

if [ "$IS_MEMBER" != "True" ] && [ "$IS_MEMBER" != "true" ]; then
    log_warn "Account is not a member of $CHANNEL"
    log_info "Attempting to join channel..."

    JOIN_RESULT=$(api_call POST "/channels/$CHANNEL/join" "{\"account_id\": $ACCOUNT_ID}")
    echo "$JOIN_RESULT" | python3 -m json.tool 2>/dev/null || echo "$JOIN_RESULT"

    sleep 3
fi

# Step 4: Test write access (pre-ban)
log_info "Step 4: Testing write access (should succeed if not banned)..."
WRITE_TEST=$(api_call POST "/commands/execute" "{\"account_id\": $ACCOUNT_ID, \"command\": \"check_ban\", \"params\": {\"target\": \"$CHANNEL\", \"test_message\": true}}")
echo "$WRITE_TEST" | python3 -m json.tool 2>/dev/null || echo "$WRITE_TEST"

IS_BANNED=$(echo "$WRITE_TEST" | python3 -c "import sys,json; r=json.load(sys.stdin); print(r.get('result',{}).get('is_banned', False))" 2>/dev/null || echo "unknown")
CAN_WRITE=$(echo "$WRITE_TEST" | python3 -c "import sys,json; r=json.load(sys.stdin); print(r.get('result',{}).get('can_write', False))" 2>/dev/null || echo "unknown")

echo ""
if [ "$IS_BANNED" = "True" ] || [ "$IS_BANNED" = "true" ]; then
    log_warn "Account is BANNED from $CHANNEL"
else
    log_ok "Account is NOT banned (can_write: $CAN_WRITE)"
fi

echo ""
echo "=============================================="
echo "  Manual Test Instructions"
echo "=============================================="
echo ""
echo "To test ban detection:"
echo ""
echo "1. Go to $CHANNEL in Telegram (as admin)"
echo "2. Find the test account ($PROFILE_NAME) in members"
echo "3. Ban the account (right-click -> Ban)"
echo "4. Run this script again to verify detection"
echo ""
echo "Or send a message that will trigger the ban:"
echo ""
echo "  curl -X POST -u $API_USER:$API_PASS \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"account_id\": $ACCOUNT_ID, \"command\": \"send_message\", \"params\": {\"target\": \"$CHANNEL\", \"text\": \"test\"}}' \\"
echo "    $API_URL/commands/execute"
echo ""
echo "Then check bans:"
echo ""
echo "  curl -s -u $API_USER:$API_PASS $API_URL/bans | python3 -m json.tool"
echo ""
