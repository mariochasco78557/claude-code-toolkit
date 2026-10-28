# ROUTER — topic → destination (curated; keep the whole file under ~7500 chars)
<!-- Hook injects the 1-2 best lines as [ROUTER]; open ONLY what they name. kb ids → `kb_get`; "text" → `kb_search`.
cc:=docs:anthropic-claude-code-docs: pf:=docs:anthropic-platform-docs: auth can>pra>int (canonical > practice > internal).
No line fits → `kb_search`, then the vault index.md.
Cols: id | topic | keywords (!strong, x* prefix, phrases; stemmed; more in ops/router_synonyms.json) | vault | kb | owner | auth -->

R01 | Claude Code hooks | !hook,UserPromptSubmit,SessionStart,PreToolUse,PostToolUse,Stop hook | [[hooks-overview]] | cc:en/hooks.md cc:en/hooks-guide.md | - | can
R02 | Prompt caching | !caching,prompt cache,cache_control,cache hit,ttl | [[prompt-caching]] | pf:en/build-with-claude/prompt-caching.md | - | can
R03 | MCP servers | !mcp,mcp server,connector,tool server | [[mcp-servers]] | cc:en/mcp.md | - | can
R04 | Subagents | !subagent,delegate,orchestrate,parallel agents,agent teams | [[subagents]] | cc:en/sub-agents.md cc:en/agent-teams.md | - | can
R05 | Evals | !eval,golden set,test cases,regression,grader | [[evals]] | pf:en/test-and-evaluate/develop-tests.md | - | can
R06 | Skills | !skill,SKILL.md,slash command,custom command | [[skills]] | cc:en/skills.md | - | can
R07 | Memory, CLAUDE.md | !claude.md,memory,project instructions,rules file | [[memory]] | cc:en/memory.md | - | can
R08 | Settings, permissions | !settings.json,permission,allowlist,sandbox,managed settings | [[settings-and-permissions]] | cc:en/settings.md cc:en/iam.md | - | can
