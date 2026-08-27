# Shared application state, populated once by bootstrap.bootstrap() at
# startup and read by all other ssp_* modules. Kept as plain module
# attributes so every module sees the same values via `import ssp_state`.

engine = None
session = None

hierarchy = None
df_wpl_info = None
selected_workplaces_log = None

ifa_wpl_to_forcam_uuid = None
forcam_uuid_to_ifa_wpl = None
df_operating_state_codes = None
