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
R08 | Settings, permissions | !settings.json,permission,allowlist,sandbox,managed settings,permisos | [[settings-and-permissions]] | cc:en/settings.md cc:en/iam.md | - | can
R09 | Tool use, structured outputs | !tool use,tool_use,function calling,structured output,json schema,tool_choice | [[tool-use]] | pf:en/agents-and-tools/tool-use/overview.md | - | can
R10 | Model choice, cost | !model choice,which model,haiku,sonnet,opus,token cost,rate limit | [[model-selection]] | pf:en/about-claude/models/overview.md | - | can
R11 | Agent SDK | !agent sdk,sdk,query loop,custom agent,agent loop | [[agent-sdk]] | pf:en/agent-sdk/overview.md | - | can
R12 | Context window, compaction | !compact,context window,context limit,/clear,long session,conversation too long | [[context-management]] | cc:en/costs.md | - | can
R13 | Headless, CI | !headless,claude -p,ci pipeline,github actions,non-interactive,print mode | [[headless-and-ci]] | cc:en/headless.md cc:en/github-actions.md | - | can
R14 | Prompt injection, security | !prompt injection,jailbreak,untrusted input,exfiltration,guardrail | [[prompt-injection]] | pf:en/test-and-evaluate/strengthen-guardrails/mitigate-jailbreaks.md | - | can
R15 | RAG, embeddings | !rag,embedding,vector,retrieval,chunking,reranker | [[rag-and-embeddings]] | pf:en/build-with-claude/embeddings.md | - | practice
R16 | Plugins, marketplaces | !plugin,marketplace,plugin.json,bundle commands | [[plugins]] | cc:en/plugins.md | - | can
R17 | Scheduled agents, cron | !cron,schedule,scheduled task,systemd timer,nightly run,recurring | [[scheduled-agents]] | cc:en/headless.md | - | practice
