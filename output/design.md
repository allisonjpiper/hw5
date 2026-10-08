# Dashboard design notes (Problem 8)

These notes explain why the Campus Customs desk dashboard (`frontend/`) looks and behaves the way it does. The person using it is a shop employee, not a developer. They need to know what needs their attention, trust what the agents did, and approve money without worrying about getting it wrong. Every choice below serves one of those three goals.

## Start from the work, not the system

The default screen is the ticket list, because tickets are how an employee thinks about their day. Agents, MCP tools, and audit logs matter, but they come second, so they sit inside each ticket and in a separate Agent activity tab. The list shows each ticket's requester, subject, and status, plus small hints like "1 to approve" or "1 draft", so someone can tell at a glance which ticket needs them without opening each one.

Tickets are labeled with plain words ("Customer order", "Awaiting approval") instead of database values like `price_override` or `awaiting_approval`. Tool names are translated the same way: `get_cash_position` shows as "Cash position" and `request_payment_approval` as "Request approval". This keeps the screen readable for someone who has never seen the code.

## Show what happens next

Each ticket has a four-step tracker: agents work the ticket, approve payments, send drafts, resolve. The agent workflow has several hand-offs between the agents and the human, and it's easy to lose track of whose turn it is. The tracker answers that question at a glance: the current step is highlighted and finished steps get a check mark.

Buttons that can't be used yet stay visible but disabled, with a short reason next to them (for example "Approve or reject 1 payment request first" next to Mark resolved). Hiding the button would leave the user wondering where it went. Showing it with a reason teaches the rules of the workflow without any separate instructions.

## Make the agents' work visible and understandable

An agent run takes 20 to 60 seconds. A spinner alone for that long feels broken, so the ticket page shows a live feed while the agents work: "Boss hands work to Accounting", "Accounting calls Cash position", "Customer Service writes its report". Each agent has its own color and initial, so the hand-offs are easy to follow, and nested work is indented under the agent that asked for it. A short banner explains what's happening and reminds the user that nothing is paid or sent without them.

When the run finishes, the summary leads with the Boss's decision in plain language, since that's what the employee needs first. Below it, "Who did what" shows each agent as a card with its own summary, the tools it used, and its cost, laid out left to right in the order the work flowed. Then come the reasons, a checklist titled "What you need to do", and the risks. That order (decision, evidence, action) matches how someone actually reads a report.

Token cost appears on every run and agent card. The shop has a $0.50 approval rule for tokens, so the employee should see what each run costs as a matter of course.

## Make money decisions safe and deliberate

Approving a payment actually moves cash in the shop's books, so it's the one action designed to slow the user down a little. The approve dialog shows who is being paid and why (the agent's memo), then a before-and-after view of the checking balance: "Checking now $3,400 → After payment $2,560". A blue note explains exactly which records will change. If the payment would overdraw the account, the dialog says so in red and the button is disabled, which matches the "no debt" rule the backend enforces.

Every approval, rejection, and resolution asks for the person's name, because the safety rules require a named human, and the name ends up in the database and audit trail. The name is saved after the first entry and prefilled from then on, so the requirement doesn't become a chore. Names of agents are rejected so an agent can never be recorded as the approver.

Reset is the most destructive action, so it is the only one that asks the user to type a word (`RESET`) to confirm. The dialog lists what will happen in plain terms and reassures them that a backup is saved and the audit trail is kept.

## Keep cash in view everywhere

The checking balance and "free after bills" sit in the top bar on every screen, because almost every decision in this shop comes back to cash. "Free after bills" turns amber when it gets low, since the shop has no incoming cash and a low number is the real warning sign. The Cash tab explains the number with a simple stacked bar (rent, open invoices, queued orders, free cash) and a line-by-line breakdown, so the employee can see why the free amount is what it is instead of just trusting it.

## Treat drafts as drafts

Agent-written messages are shown in dashed boxes with a "Draft · not sent" badge, because the rule is that agents never contact anyone. A Copy button makes the next step (sending it yourself) easy. Before closing a ticket that has drafts, the resolve dialog reminds the employee to send them first.

## Clear feedback and recovery

Every action ends with a short toast message that says what happened in shop terms: "Paid $840.00 to Bulldog Print Co. Checking is now $2,560.00." Errors from the backend are shown in plain language, with the technical "Error calling tool…" prefix removed. If the backend isn't running, the page doesn't break or show empty tables. It shows a banner with the exact command to start the backend and a "try again" button. Empty states ("Nothing waiting on you", "No agent run yet for this ticket") tell the user what will appear there and how to make it happen.

## What makes it feel special

A few choices are meant to make the board feel like Campus Customs' own back office rather than a generic admin panel. Each agent has a personality you can see: a colored badge with an initial (navy B for the Boss, amber A for Accounting, red CS for Customer Service), used the same way in the live feed, the "Who did what" cards and the activity log, so you can follow a hand-off at a glance. While a ticket runs, the feed reads like a desk conversation ("Boss hands work to Accounting", "Accounting calls Cash position"), with nested work indented under the agent that asked for it, so the employee watches the team think instead of staring at a spinner. Tool names are translated into shop language ("Order fact sheet", "Request approval", "Pay"), so the board talks about the shop, not the code. A resolved ticket gets a green closing banner quoting who closed it and why, and its full history of runs since the last reset. The cash story is told visually: checking and "free after bills" sit in the header on every screen, the Cash tab's stacked bar shows how much of the balance rent and invoices have already claimed, and every payment row shows the human who approved it. The approve dialog's "Checking now → After payment" preview turns a scary click into an informed one, and it refuses to let you overdraw a shop that has no incoming cash.

## Visual style

The look is deliberately calm: a navy header for the shop identity, a light gray page, white cards, and lots of whitespace. Color carries meaning, used consistently: blue for open and primary actions, amber for anything waiting on approval, green for paid or resolved, red for rejected or risky. That way, color alone tells the user where to look. Numbers use tabular figures, so amounts line up and are easy to compare. Loading uses skeleton shapes instead of blank space, so the layout doesn't jump when data arrives.

## Accessibility and small touches

Tabs and dialogs use proper ARIA roles. Dialogs close with Escape and put focus on the first field, and buttons show a visible focus ring for keyboard users. The layout collapses to one column on narrow screens. Status is never shown by color alone; there's always a text label too. The data refreshes quietly every 15 seconds, so balances and statuses stay current, but this pauses during an agent run so the live feed isn't interrupted.
