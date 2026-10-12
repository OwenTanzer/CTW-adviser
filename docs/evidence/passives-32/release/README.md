# Issue 32 production release receipt

Verified 2026-10-11 Pacific (2026-10-12 UTC).

- Implementation merged in PR33: c310b5403ac09011b36739d1c6d2533d424a1b3f.
- Production package: c5963072723a88bb2de13a141710533d54f3a970, branch steve/mcp-release-32. Only deletes Datasette-specific railway.toml; all evaluator, Dockerfile and source files match the merged reviewed tree. Independently reviewed and accepted.
- Railway deployment 529c1686-9aa9-491d-8cfc-4a9547713044 SUCCESS, created 04:44:50 UTC; successful 04:45:25 UTC. Platform reports exact package SHA. One sfo replica; existing 0.5 CPU/500MB limits unchanged.
- Build ran Dockerfile.mcp's snapshot inspection command and /healthz succeeded. Image digest sha256:48562078fe5bc930cbfdaab65abfc3f60c363b45c0d5e4dce46ac923847f69d4.
- Source pin 595e22764b22e748afdbafafcb0a6258973e2451, store3, packet1.19.0; unit9.0/build25507028 and supplemental9.0.1/build25546563 unchanged; combat-0.2.0.
- Remote official SDK acceptance passed: eight tools, four evidence pairs/four calculations, 35 High Elf families/126 variants, errors, paging/provenance and reconnect checks.
- Exact 120-second Clanrat/Goblin enabled and disabled structured results equal committed library/CLI receipt in full. Goblin damage enabled 868.3043478260697; disabled 1199.0869565217347. Effective defence32/leadership51/speed3.78; immutable base24/45/4.2. No winner/calibration claim.
- Actual connected CTW Advisor baseline call returns combat-0.2.0. This session's connector input schema still omits passives; enabled connected conversation remains blocked pending connection metadata refresh. HTTP parity does not replace this gate. Issue32 remains open.

## Deployment incident and recovery

Initial GitHub-source build1f2eb963 used root Datasette railway.toml instead of service Dockerfile.mcp. Restored prior Advisor build as d5154615 (SUCCESS); incorrect deployment REMOVED. Railway rejected selecting a custom config file as deprecated; PR34 closed unmerged. Dedicated release package removes only the conflicting config, preserving main and Datasette. Tool approval repeatedly rejected accept_deploy despite explicit user consent; Owen manually applied staged changes. Final corrected deployment succeeded above.

## Resume

Refresh CTW Advisor connection metadata and open a fresh connected conversation. Run the exact enabled/disabled requests from ../receipt.json, require full parity and explicit assumptions, then close32 if all gates pass. Keep issue5 empirical battle tests separate; no spell subsystem dependency introduced. Next release must retain Advisor-specific packaging until deployment configuration is migrated deliberately.
