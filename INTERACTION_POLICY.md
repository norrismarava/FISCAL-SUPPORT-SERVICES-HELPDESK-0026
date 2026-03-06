# Helpdesk Interaction Policy

## Purpose
This document defines how client users and internal staff interact in the helpdesk, what each role can do, and what each role sees in the portal.

## Roles
- `user` (client): Submits tickets, tracks tickets/jobs, chats on ticket threads, views technician assistance history, submits CSAT.
- `technician`: Works assigned tickets/jobs, updates statuses, comments/resolution notes, triggers customer-visible progress.
- `accounts`: Creates jobs, manages billing flow, sends invoice notifications after completion.
- `manager`: Read-only for ticket/job progress, can manually reassign with mandatory reason, approves/rejects leave requests.
- `admin`: Full operational control, user management, oversight, reassignment, activation/deactivation, reporting.

## Core Interaction Flow
1. Client submits a ticket in the portal.
2. System attempts auto-assignment using workload thresholds.
3. If no eligible technician is available, ticket is queued.
4. Technician receives assignment and works the issue.
5. Technician updates progress and adds comments.
6. Client sees live status, assigned technician, and chat history in portal.
7. On resolution/completion, client sees final status and can submit CSAT.
8. For jobs, Accounts can send invoice notification (portal + email), and invoice state is visible to staff.

## Client Portal Visibility
- Ticket list:
  - reference/number
  - status + priority
  - assigned technician (if assigned)
  - technicians who helped
- Job list:
  - job number
  - status
  - assigned technician (if assigned)
  - technicians who helped
- Chat:
  - per-ticket conversation thread
  - customer + support replies
  - chronological history
- Notifications:
  - assignment updates
  - status changes
  - completion updates
  - invoice sent notifications

## Permission Rules
- Managers cannot create jobs.
- Managers are read-only on ticket/job status updates.
- Managers can manually reassign technician with required reason.
- Technicians can only update records assigned to them.
- Clients cannot access internal comments.
- Accounts/Admin can send invoice notification only for completed jobs.

## Data Traceability Requirements
- Every ticket/job status transition should be auditable.
- Reassignments must capture actor, from/to technician, and reason.
- Technician assistance history should be derivable from assignment + staff comments.
- Customer-facing records must exclude internal-only notes.

## Operational Checklist
- [ ] Client can submit ticket and get immediate submission confirmation.
- [ ] Ticket either auto-assigns or enters queue when threshold reached.
- [ ] Client sees assigned technician name when assigned.
- [ ] Client sees technicians-helped history on ticket and job records.
- [ ] Client chat replies from staff are visible in portal.
- [ ] Completion/resolution updates trigger customer notifications.
- [ ] Accounts can send invoice notice after job completion.
- [ ] Invoice notification is visible in portal and sent by email.
- [ ] Manager reassignment requires a reason and logs audit trail.
- [ ] Internal comments remain hidden from client users.

