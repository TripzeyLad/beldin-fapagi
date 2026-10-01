"""Metadata-only policy for future software installation/update adapters."""
INSTALL_POLICY={"version":1,"permission":"SYSTEM_CHANGE","default_policy":"deny","confirmation_required":True,"allowlisted_packages":[],"require_verified_source":True,"require_checksum_or_signature":True,"max_output_bytes":16384,"max_runtime_seconds":60,"arbitrary_urls":False,"arbitrary_commands":False}
