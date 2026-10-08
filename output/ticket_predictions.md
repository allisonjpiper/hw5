# Problem 6: Predicted agent behavior for the three open tickets

*Tool names below are the original placeholders. Final names: tool_1 = check_order_fulfillment, tool_2 = check_rent_coverage, tool_3 = price_bulk_order, tool_5 = lookup_inventory_pricing, tool_7 = get_cash_position, tool_8 = request_payment_approval, tool_10 = save_message_draft, tool_11 = list_approval_queue, tool_12 = record_ticket_decision.*

Written before the agent run. The Boss reads each ticket's fact sheet (tool_1, tool_2 or tool_3) itself, so it only delegates for work it can't do: queuing money for human approval, which only Accounting can do, and writing to the customer, which is Customer Service's job. Inventory and Facilities shouldn't be needed for any of the three tickets. The run starts from a clean database with $3,400 in checking and works the tickets in order.

## Ticket 101: Tauhid Zaman's Bulldog Tee (size S)

The Boss will read tool_1 and see that size S is out of stock and that the restock is held up by invoice 501, which is $840 and overdue. It will call Accounting first, because the only thing standing between Tauhid and a size S tee is an unpaid invoice, and only Accounting can queue a payment for approval; the reply has to wait until the money step is known. Accounting will check cash with tool_7, confirm nothing is already queued with tool_11, and use tool_8 to queue invoice 501 for human approval. It will note that rent still fits afterward. The Boss will then ask Customer Service to draft a reply. Customer Service will check stock with tool_1 or tool_5 and save the draft with tool_10, saying the tee is out of stock and will arrive about five days after the reprint is confirmed. The Boss will record the ticket as awaiting approval with tool_12.

## Ticket 102: Elm City Properties rent notice

The Boss will read tool_2, which shows $2,400 rent due in two days against $3,400 in checking, and send the ticket straight to Accounting, because paying rent is the whole job and Accounting is the only agent that can queue money. Facilities isn't needed because the fact sheet already covers the lease. Accounting will check tool_7 and tool_11, see that invoice 501 is already queued, and use tool_8 to queue the rent for approval. That leaves $160 if both are paid. No landlord draft will be written. The Boss will record the ticket as awaiting approval.

## Ticket 103: Yale AI Club bulk hoodie order

The Boss will read tool_3, which shows 8 of the 20 hoodies in stock, a $22 cost and a $58 list price, and call Accounting first, because the club is asking about price and the shortfall is a cash question, and Customer Service can't write a quote until Accounting sets the number. Accounting will use tool_3 and tool_7 and find only $160 free after rent and the invoice. That isn't enough for the $264 reprint, so it won't queue a purchase order. It will recommend selling the 8 in stock at a modest bulk discount, around $46 to $52 each, pending owner approval. The Boss will then ask Customer Service to draft the quote with tool_10, and record the ticket as awaiting approval with no approval request created.

## Overall

I expect five specialist runs (Accounting three times, Customer Service twice), no refused hand-offs, and two pending approvals (the $840 invoice and the $2,400 rent). I also expect two customer drafts, all three tickets left awaiting approval, no cash spent, and lower token cost than Problem 5's run.
