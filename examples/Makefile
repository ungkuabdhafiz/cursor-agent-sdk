# Example: plan → implement → follow-up using cursor-agent-sdk
#
# Usage:
#   export CURSOR_API_KEY="cursor_..."
#   make plan PROMPT="Add rate limiting to the API"
#   make implement
#   make follow-up PROMPT="Add tests for the middleware"

CWD ?= $(CURDIR)
SESSION ?=
SDK := cursor-agent-sdk --cwd $(CWD) $(if $(SESSION),--session $(SESSION),)

.PHONY: plan implement follow-up session clear

plan:
	$(SDK) plan "$(PROMPT)"

implement:
	$(SDK) send --mode agent "Implement the plan you proposed"

follow-up:
	$(SDK) send "$(PROMPT)"

session:
	$(SDK) session

clear:
	$(SDK) clear
