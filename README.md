# Search Ads CLI

A command-line interface for managing Apple Search Ads campaigns.

Built on top of [search-ads-api](https://github.com/SamPetherbridge/search-ads-api).

## Installation

```bash
pip install search-ads-cli
```

## Setup

Set up your Apple Search Ads API credentials:

```bash
export ASA_CLIENT_ID="SEARCHADS.your-client-id"
export ASA_TEAM_ID="SEARCHADS.your-team-id"
export ASA_KEY_ID="your-key-id"
export ASA_ORG_ID="123456"
export ASA_PRIVATE_KEY_PATH="/path/to/private-key.pem"
```

Or use a `.env` file in your working directory.

Test your credentials:

```bash
asa auth test
```

## Commands

### Campaigns

```bash
# List all enabled campaigns
asa campaigns list

# List all campaigns (including paused)
asa campaigns list --all

# List with 7-day spend data
asa campaigns list --with-spend

# Get a specific campaign
asa campaigns get 123456789

# Output as JSON
asa campaigns list --json
```

### Ad Groups

```bash
# List ad groups in a campaign
asa ad-groups list 123456789
```

### Keywords

```bash
# List keywords in an ad group
asa keywords list 123456789 987654321
```

### Reports

```bash
# Campaign performance report
asa reports campaigns --start 2024-01-01 --end 2024-01-31

# Keyword report
asa reports keywords 123456789 --start 2024-01-01 --end 2024-01-31

# Export to CSV
asa reports campaigns --start 2024-01-01 --end 2024-01-31 --output report.csv
```

### Brand Campaigns

Create brand protection campaigns for your app:

```bash
# Interactive mode (recommended)
asa brand

# With arguments
asa brand "My App Name" -v "My App" -c US -c GB

# All standard countries
asa brand "My App Name" --country all

# Preview without creating
asa brand "My App Name" -c US --dry-run
```

### Campaign Expansion

Expand existing campaigns to new markets:

```bash
# Interactive mode
asa optimize expand

# With filters
asa optimize expand --type Generic --match EM

# Preview
asa optimize expand --dry-run
```

### Bid Optimization

Check and fix bid discrepancies:

```bash
# Check bids
asa optimize bid-check

# Auto-fix discrepancies
asa optimize bid-check --auto-fix

# With threshold
asa optimize bid-check --threshold 0.05
```

## License

MIT License - Copyright (c) 2025 Peth Pty Ltd
