# AI Prompts Log — Homework 5

Each section below corresponds to one problem. It contains:
- The prompt(s) I gave the AI, in my own words
- Any follow-up prompt(s) I needed
- My explanation of why the follow-up was needed (filled in by me at the end)

**Rule for the AI assistant:** As I submit prompts to you during this homework, automatically
log each one (and any follow-up prompt) into the matching problem section below as it happens —
don't wait for me to ask. Leave the "why the follow-up was needed" line blank; I fill that in
myself at the end.

---

## Problem 1: Vibe Coder Prompts

**Prompt:**
> we're starting homework 5, run the associated tool to set up the the homework 5 folder with AI_prompts.md

> run the tool without the titles and i'll send the titles that you can populate as we go along

**Follow-up prompt:**
> Problem 1: Vibe Coder Prompts.
> Confirm that you created AI_prompts.md with the same sections as previous homeworks.


**Why the follow-up was needed:**
> I had to specify the problem number and that the task was done. 

---

## Problem 2: Study the Campus Customs database

**Prompt:**
> Problem 2: Study the Campus Customs database.
> Create a copy of campus_customs.db under data/campus_customs_new.db in the virtual environment which will be the main folder we edit in.
> Also create output/harness.md which will describe what each table in the data folder means and why each category in the tables is there and why those matter to the agents

**Follow-up prompt:** N/A


**Why the follow-up was needed:** N/A

---

## Problem 3: Build the MCP server

**Prompt:**
> Problem 3: Build the MCP server
> we'll be building in mcp_server/ using FastMCP. We'll be creating 3 MCP tools that will help resolve the open tickets in the  data file. These tools (to be described in output/harness.md) need to be specific and helpful for the agents that we will be creating. Keep the names empty and don't hallucinate or draw in information from outside the database. Each tool should be clear about which ticket it helps solve (e.g. 101). Make a note in mcp_server/README.md about why we need the MCP server, what database file it uses and the tools created.

**Follow-up prompt:**
> (Clarification) "Keep the names empty" means leave the tool names blank — use placeholders (tool_1, tool_2, tool_3) and I'll choose the real names.

**Why the follow-up was needed:** Had to specify to leave the tool names blank since I had forgotten that detail from the instructions. 

---

## Problem 4: Add the MCP server to vibe coder and test each tool

**Prompt:**
> Problem 4: Add the MCP server to vibe coder and test each tool.
> Add the MCP server you created to this project so that Claude Code can call the tools. Save the connection JSON text in .mcp.json at the project root. Once the vibe coder is connected, test the three tools you created and save what happens in output/mcp_smoke.json
> You should log what prompt stimulates the tool test, the tool name, and the tool output (which should correspond to the values in data/campus_customs_new.db)

**Follow-up prompt:**
> using homework 5 folder.
> Using the campus-customs MCP server, call tool_1 with ticket 101, tool_2 with ticket 102, and tool_3 with ticket 103. Save the results to output/mcp_smoke.json with one entry per tool containing: the prompt that triggered the test, the tool name, the ticket id, and the full tool output. Then check each output against data/campus_customs_new.db and note whether they match. Log this prompt in AI_prompts.md under Problem 4.


**Why the follow-up was needed:** 
> Had to move over to the homework 5 folder to continue working and follow up on the details of the success of running the tools. 

---

## Problem 5: Build the agent team and grow the MCP tools

**Prompt:**
> Problem 5: Build the agent team and grow the MCP tools.
> Using Pydantic AI, build these 5 agents: Boss, Inventory, Accounting, Facilities, and Customer Service. Make sure that each agent can send work to one another as fits with their function. each agent should have their own prompts, models, and agent loops. Once you're done, fill backend/prompts/ with one file per agent including their prompts. The backend/models.py should be filled with data types and the agent files should be in backend/. Use only gpt luna for each agent if you need to use my portkey api key. Prompts should be specific including details of all aspects of the agents work and scope. If the agents need any tools, add them to the MCP server so that the agents can work on the tickets in the data file. I think we need a pay tool.
>
> all facts about the shop should come from the MCP server over data/campus_customs_new.db. No tools layer should bypass MCP. Each agent should record their work in output/audit_trail.json. That means they record loops and append them to the file rather than replacing its contents so that we can check their work later.
> Once you're done, output/harness.md should include a list of each agent and MCP tool that you created along with the tables that each tool pulls from.
> Make sure that the Boss is reading each ticket and deciding who should work on it. Then the boss makes the final decision.
> The inventory agent should check inventory and manage shortfalls while coordinating with vendors to restock.
> The accounting agent should manage cash, invoices, margins, and payments/POs to send for human approval (we will handle the human approval piece in the next problem)
> The facilities agent should handle the shop space, i.e. leases and rent, etc
> Customer Service agent writes the messages that go out to customers about the tickets.
>
> Add in the harness.md the following safety rules and any other safety rules you think are appropriate:
>
> 1. human approval required for any decisions that involve money changing hands
> 2. once payments are made, the corresponding table should be updated
> 3. no work is done by agents without being logged to audit_trail.json
> 4. Pay tool shouldn't pay if there is no remaining cash. we aren't going into debt here.
> 5. no cash is coming in. only going out.
> 6. do not email anyone real or call real vendors, especially not without human approval. all drafts stay logged.

**Follow-up prompt:**
> Also add a rule to harness.md that there needs to be human approval before the agents do anything to use tokens that cost more than $.50

> and make sure the readme matches all the new tools

> fix that discrepancy please (switch every agent from gpt-5.6-luna to gpt-6-luna, the model the assignment requires)

**Why the follow-up was needed:**
>Forgot to specify the details about harness.md about human approvals for cash transactions.

---

## Problem 6: Plan the three tickets

**Prompt:**
> Ok now we're moving to problem 6: Plan the three tickets
> Make a note of what you predict the agent team will do to resolve each open ticket, which should include:
>
> 1. who the boss will call first
> 2. all the agent delegations you expect with specifics
> 3. which MCP tools will be used
>
> Then create output/desk_tickets.html. This page should be able to open and include one tab per ticket. Create a tab for cash and reflections and leave it empty - we'll come back to those.
> For each ticket, create an expected section (where you can paste in your prediction) and an actual section that we'll complete with the actual results. The plan should have some specialization so that each ticket only calls the minimum number of agents to successfully close the ticket. Then have the agents resolve the tickets and describe what was different in the Actual section

**Follow-up prompt:**
> Can you also simplify the predictions in problem 6? They should be shorter and in paragraph form rather than with these numbers and bold typeface


**Why the follow-up was needed:**
> What the AI had written was overly complicated and not clear, so I asked it to edit and simplify. 

---

## Problem 7: Backend routes

**Prompt:**
> Now for Problem 7: Backend routes
> Use FastAPI in backend/main.py and create a backend that can
>
> 1. find the three tickets and report whether each is open or closed
> 2. take a ticket id and run your agent team on that ticket
> 3. report on what agents have done recently and what tools they used
> 4. approve a payment or cash transaction and actually make the cash transfer once human approval has been made
> 5. report the cash_accounts checking balance when asked
> 6. reset the database when you want a fresh run
>
> The backend folder should start with uvicorn main:app --reload --port 8000 so that the frontend dashboard can call the abilities that we listed above
> Then make a note in output/harness.md to list what each route does (including URL)

**Follow-up prompt:**
N/A

**Why the follow-up was needed:**
N/A

---

## Problem 8: Agent dashboard

**Prompt:**
> Problem 8: Agent dashboard
> Now we're building the frontend dashboard with React + Vite + TypeScript which can access the routes that we set up in the previous problem. The board should be able to list the tickets, let the user click into a ticket and start the agent on it, show what the agents are doing, mark a ticket as resolved when the run is done, how a summary of the agent's tasks, let the human approve payments or cash transactions, show the checking balance, and anything else you think would be useful for a company employee to be able to do

**Follow-up prompt:**
> For question 8, Please make it user friendly and well designed.

> For problem 8: also make sure the front end and backend can talk to each other at the localhost number you created. the backend should allow the vite page origin too. start the board with npm run dev so that I can access the frontend and start testing it out.

**Why the follow-up was needed:**
> Asked it to create an html that was more user friendly and clarify how the systems should interact. 

---

## Problem 9: Resolve the tickets

**Prompt:**
> Problem 9: Resolve the tickets
> I reset the database. Please run the agents and make sure the tickets get resolved. Fill output/desk_tickets.html with what happened on each ticket tab. Keep the expected section as is. On the Cash tab of output/desk_tickets.html, itemize the money: Checking balance (and how it changed), each ticket and how that changed the dollar amount, ending checking balance, etc
> Make sure that these tickets were resolved correctly and fix it so that the agents do it right if they aren't.
> Save output/resolved_ticekts.json for each ticket including id, final status, short outcome, what each agent contributed and human approvals
> Save output/resolved_board.html so that there is a place i can click into with a screenshot of the react board for each resolved ticket.
> make sure the runs are added to the end of output/audit_trail.json and finish the harness.md so that it covers tables, MCP tools, five agents, API routes, dashboard, and safety rules

**Follow-up prompt:** n/a


**Why the follow-up was needed:** n/a

---

## Problem 10: Reflection

**Prompt:**
> Problem 10: Reflection
> Next, we're going to input some information in the Reflection tab of output/desk_tickets.html.

**Follow-up prompt:**
n/a 


**Why the follow-up was needed:** n/a

---

## Problem 11: Submit to GitHub

**Prompt:**
> Problem 13: Push to GitHub and submit the URL
> (don't do this yet but please put the prompts and title in the prompts.md file so that i can review everything before we push to github!!!)
> At the end, please put all this code in hw5 and push it to a public github repository under my username. i will then submit the repo URL. make sure that my real .env is not in the file and instead include .env.example. and include the data from this homework in the data/ file so that the graders can access it. This is what the file layout should look like (see screenshot)
> also put the repo URL under output/github_url.txt
>
> here's the repo link: https://github.com/allisonjpiper/hw5
>
> (Screenshot of target layout: hw5/ with AI_prompts.md, requirements.txt, .env.example, .gitignore, .mcp.json, README.md; data/ with campus_customs.db and campus_customs_new.db; mcp_server/ with server.py and README.md; frontend/; backend/ with main.py, models.py, and prompts/ (boss.md, inventory.md, accounting.md, facilities.md, customer_service.md); output/ with harness.md, mcp_smoke.json, desk_tickets.html, design.md, resolved_tickets.json, resolved_board.html, audit_trail.json, github_url.txt)

**Follow-up prompt:**
> (After checking my plan against the assignment pages) and fix all these

> updated the "why" in the prompts and ready to push to github
Please push to the repo so I can submit the URL.


**Why the follow-up was needed:**
Finalize the homework after I reviewed. 

---
