"""
FraudGraph Investigation Agent — Part 2

The investigation agent orchestrates fraud case investigations by:
1. Loading cases from the MCP server
2. Planning investigation steps
3. Gathering graph evidence via MCP tools
4. Analyzing evidence for supporting/contradictory signals
5. Managing fraud hypotheses
6. Assessing evidence sufficiency and uncertainty
7. Requesting additional evidence when needed
8. Applying deterministic policy rules
9. Recommending the next best action
10. Writing case memory for future investigations

This package is built entirely on top of the 8 existing Part 1 MCP tools.
"""
