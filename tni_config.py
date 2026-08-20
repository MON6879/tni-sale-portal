# tni_config.py
# Centralized configuration for TNI Telegram Bots and Group mappings

# Telegram group/channel IDs (migrated supergroups have -100 prefix)
TELEGRAM_GROUPS = {
    "T1": -1004215695747,  # TNI TEAM 1 (Dawei)
    "T2": -1004480845549,  # TNI TEAM 2 (Myeik + Team5)
    "T3": -1004369170658,  # TNI TEAM 3 (Bokpyin)
    "T4": -1004293741999,  # TNI TEAM 4 (Kawthoung)
    "CONTROL": -5251698940, # 5 TNI TECHNICA DEP CONTROL SITE
}

# Telegram Construction Groups (T CONS)
CONSTRUCTION_GROUPS = {
    "T1_CONS": -5405599980,  # TEAM 1 CONSTRUCTION
    "T2_CONS": -5006032995,  # TEAM 2 CONSTRUCTION
    "T3_CONS": -5342629411,  # Team 3 CONSTRUCTION
    "T4_CONS": -5473673421,  # TEAM 4 CONSTRUCTION
}

# Team Names (integer key mapping)
TEAM_NAMES = {
    1: "Team 1 Dawei",
    2: "Team 2 Myeik",
    3: "Team 3 Bokpyin",
    4: "Team 4 Kawthoung",
}

# Group Names (string key mapping)
GROUP_NAMES = {
    "T1": "Team1 Dawei",
    "T2": "Team2 Myeik",
    "T3": "Team3 Bokpyin",
    "T4": "Team4 Kawthoung",
    "T1_CONS": "Team 1 Construction",
    "T2_CONS": "Team 2 Construction",
    "T3_CONS": "Team 3 Construction",
    "T4_CONS": "Team 4 Construction",
}
