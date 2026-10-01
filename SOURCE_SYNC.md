# Valkyrie source synchronization

This repository snapshots the current working Valkyrie Beldin installation on 2026-10-01, including its uncommitted source changes. The running installation was not edited or reloaded.

The six local development commits are retained with their messages, dates, order, and source structure. Their hashes changed because private files were removed throughout history and embedded Windows account identifiers were sanitized. Commit authors use the public creator alias and GitHub noreply address. The existing GitHub history remains a parent of the synchronization commit; its announcement is preserved in docs/PUBLIC_ANNOUNCEMENT.md.

## Privacy exclusions

Excluded throughout imported history and current files: config.* (including all .env contents), coding-projects.json, runtime, private memory, coding data, audits, backups, bundled Python, caches, logs, backup copies, generated inventories, benchmark and health/test result snapshots. .gitignore protects these categories for future work.

Embedded local username paths use BELDIN_USER; Windows account SIDs use REPLACE_WITH_LOCAL_ACCOUNT_SID; concrete LAN addresses use documentation-only 192.0.2.x addresses. These are deliberate publication substitutions, not working deployment values. Deployment/reload scripts and fixed production paths must be reviewed and configured for a target installation; security guards remain in place. Historical claims in source documentation describe their original audits, not a fresh deployment guarantee.

The application source, tests, UI assets, founding documents and development utilities retain their original layout. Apart from the documented substitutions and updated .gitignore, retained source files are copied byte-for-byte. No live credentials or configuration are supplied. This is a sanitized source repository, not a ready-to-run clone of the private installation.

## Verification and limitations

The synchronization checked every retained source file against the live tree, scanned all imported history plus the staged tree for known live credentials and sensitive patterns, checked ignore rules, compiled 71 Python files in memory, and verified founding-document hashes. At synchronization time 85 source files were byte-identical, 11 contained the documented privacy substitutions, and .gitignore was updated; two documentation files were added.

Focused checks: 14 UI tests passed; 8 of 9 Python checks across test_supervise, test_founding, and test_reload_control passed. The reload fixture checksum test fails because private-path redaction changes the exported script bytes. Its production checksum is deliberately retained, as is the runtime production identity guard. This sanitized reload script is not authorized as a production replacement. The full integration suite and deployment were not run. No setup script, live reload, firewall change, or service restart was performed.
