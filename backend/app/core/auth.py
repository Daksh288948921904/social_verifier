import secrets

AUTH_USERNAME = "rig360media"
AUTH_PASSWORD = "worldisDNL"

# There's exactly one hardcoded account, so a single shared session token
# (rather than a per-user token store) is enough. Regenerated on every
# process start, which just means existing browser sessions need to log in
# again after a backend restart.
SESSION_TOKEN = secrets.token_hex(24)
