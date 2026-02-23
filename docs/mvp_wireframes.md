# Pantheon MVP Wireframes

Low-fidelity wireframes for core MVP user experience.
Scope: solo users + internal admin panel.

---

## 1) App Home

```text
+----------------------------------------------------------------------------------+
| Pantheon                                                         [Usage: 120/495]|
+----------------------------------------------------------------------------------+
| Search rooms...                                                                |
+----------------------------------------------------------------------------------+
| Quick Start Templates                                                          |
| [ Inbox Copilot ] [ Doc Review ] [ Research Digest ] [ KPI Review ] [ + Blank ]|
+----------------------------------------------------------------------------------+
| Recent Rooms                                                                    |
| +----------------------+ +----------------------+ +-----------------------------+ |
| | Weekly Client Memo   | | Contract Review      | | Research Room             | |
| | mode: orchestrator   | | mode: manual         | | mode: roundtable         | |
| | last used: 2h ago    | | last used: yesterday | | last used: 3d ago        | |
| +----------------------+ +----------------------+ +-----------------------------+ |
+----------------------------------------------------------------------------------+
| Plan: Starter ($29)              [Upgrade]                                      |
+----------------------------------------------------------------------------------+
```

---

## 2) Room Setup (Create/Edit)

```text
+----------------------------------------------------------------------------------+
| Create Room                                                                      |
+----------------------------------------------------------------------------------+
| Room Name: [__________________________________________]                         |
| Goal:      [__________________________________________]                         |
| Mode:      ( ) Manual   ( ) Roundtable   ( ) Orchestrator                      |
+----------------------------------------------------------------------------------+
| Agents                                                                           |
| +----+----------------------+-------------------+-------------------------------+ |
| | #1 | Role: Researcher     | Model: DeepSeek  | Tools: search, fetch, files | |
| | #2 | Role: Writer         | Model: GPT-OSS   | Tools: files, code          | |
| | #3 | Role: Reviewer       | Model: Premium   | Tools: files                | |
| +----+----------------------+-------------------+-------------------------------+ |
| [ + Add Agent ]                                                                   |
+----------------------------------------------------------------------------------+
| Room File Access Rules                                                            |
| [x] Uploaded files are readable only by agents with "files" capability           |
| [x] Show tool capability badges in timeline                                       |
+----------------------------------------------------------------------------------+
| Defaults                                                                         |
| [x] Show intermediate agent outputs                                              |
| [x] Show per-turn credit usage                                                   |
+----------------------------------------------------------------------------------+
|                                              [Cancel] [Create Room]             |
+----------------------------------------------------------------------------------+
```

---

## 3) Room Workspace (Main Screen)

```text
+---------------------------+-----------------------------------+------------------+
| Left Panel                | Conversation Timeline             | Right Panel      |
|---------------------------|-----------------------------------|------------------|
| Room: Weekly Memo         | Turn 12                           | Tool Activity    |
| Mode: Orchestrator        | User: "Summarize these files..."  | search: 2 calls  |
|                           |                                   | fetch: 1 call    |
| Agents                    | [Researcher - DeepSeek]           | code: 0 calls    |
| - Researcher (files)      | key findings...                   | files: 2 reads   |
| - Writer                  |                                   |                  |
| - Reviewer (files)        | [Writer - GPT-OSS]                | Uploaded Files   |
|                           | draft summary...                  | - Q1_notes.pdf   |
| Session                   |                                   | - deal_terms.pdf |
| Credits this session: 23  | [Reviewer - Premium]              | - brief.docx     |
| Monthly: 120 / 495        | revised final memo...             | Access: R/W/V OK |
|                           |                                   | Usage            |
| [Room Settings]           | Final Synthesis                   | turn: 3.8 cr     |
|                           | - concise final answer            | session: 23.1 cr |
|                           |                                   | month: 120/495   |
+---------------------------+-----------------------------------+------------------+
| @agent tags...  Ask anything...                               [Send] [Mode v]   |
+------------------------------------------------------------------------------- --+
```

---

## 4) Turn Details Drawer (Transparency/Debug)

```text
+----------------------------------------------------------------------------------+
| Turn #12 Details                                                                 |
+----------------------------------------------------------------------------------+
| Step 1  Researcher (DeepSeek)         status: success     latency: 2.1s         |
| Tokens: prompt 1,120 | output 340 | cached 900 | credits 1.12                    |
+----------------------------------------------------------------------------------+
| Step 2  Writer (GPT-OSS)              status: success     latency: 3.3s          |
| Tokens: prompt 1,870 | output 420 | cached 1,020 | credits 1.74                  |
+----------------------------------------------------------------------------------+
| Step 3  Reviewer (Premium)            status: success     latency: 4.9s          |
| Tokens: prompt 2,020 | output 510 | cached 1,020 | credits 0.94                  |
+----------------------------------------------------------------------------------+
| Tool Calls: search x2, fetch x1   Tool Credits: 0.8                               |
| File Reads: Q1_notes.pdf by Researcher, deal_terms.pdf by Reviewer                |
| Turn Total Credits: 4.60                                                           |
+----------------------------------------------------------------------------------+
```

---

## 5) Billing & Usage

```text
+----------------------------------------------------------------------------------+
| Billing & Usage                                                                   |
+----------------------------------------------------------------------------------+
| Plan: Starter ($29)              Included: 495 credits              [Upgrade]    |
| Used: 120 credits (24%)          Forecast: 340 this month                         |
+----------------------------------------------------------------------------------+
| Usage by Model (this month)                                                       |
| DeepSeek  ██████████████████ 58 cr                                                |
| GPT-OSS   ████████            24 cr                                                |
| Premium   █████               18 cr                                                |
| Qwen      ███                 10 cr                                                |
| Llama     ██                   6 cr                                                |
+----------------------------------------------------------------------------------+
| Usage by Room                                                                      |
| - Weekly Client Memo .......... 54 cr                                             |
| - Contract Review ............. 38 cr                                             |
| - Research Digest ............. 28 cr                                             |
+----------------------------------------------------------------------------------+
| Overage Price: $0.03 / credit                                                     |
+----------------------------------------------------------------------------------+
```

---

## 6) Admin Dashboard (Internal)

```text
+----------------------------------------------------------------------------------+
| Admin Dashboard                                                                    |
+----------------------------------------------------------------------------------+
| DAU: 84 | WAU: 260 | MAU: 910 | Total Credits (30d): 128,220 | Margin: 73.4%     |
+----------------------------------------------------------------------------------+
| Top Users by Cost         | Top Models by Cost          | Alerts                |
| user_122  $142            | Premium      $2,940         | 12 users >90% cap     |
| user_090  $121            | GPT-OSS      $1,220         | 3 failed tool spikes  |
| user_044   $98            | DeepSeek       $840         |                      |
+----------------------------------------------------------------------------------+
| Controls                                                                          |
| User ID: [__________]   New Cap: [____] [Update Cap] [Suspend] [Reactivate]      |
| Model Access Policy: [Starter] [Premium Off v] [Save]                             |
+----------------------------------------------------------------------------------+
| Audit Log                                                                         |
| 2026-02-20 13:44 admin_1 updated cap user_122 -> 900                              |
| 2026-02-20 13:21 admin_2 suspended user_090                                        |
+----------------------------------------------------------------------------------+
```

---

## 7) Mobile Workspace (Condensed)

```text
+--------------------------------------+
| Pantheon         Room: Weekly Memo   |
+--------------------------------------+
| Mode: Orchestrator  120/495 credits  |
+--------------------------------------+
| Timeline                              |
| User: summarize this PDF              |
| [Researcher] ...                      |
| [Writer] ...                          |
| [Final] ...                           |
+--------------------------------------+
| Tabs: [Chat] [Tools] [Uploads] [Cost]|
+--------------------------------------+
| Message...                      [Send]|
+--------------------------------------+
```

---

## 8) Key Interaction Flow

```text
Home -> Manage Agents (assign tool permissions) -> Create Room -> Upload files
-> Ask prompt -> Agent steps stream in (with tool/file traces)
-> Final synthesis -> Review credits
-> Continue session OR save/export output
```

---

### File Tool Behavior by Mode

```text
Orchestrator mode:
- Orchestrator can direct an agent to read a file.
- Only agents with "files" capability can read uploaded files.

Roundtable mode:
- Responding agents with "files" capability read and use the file.

Tag (manual) mode:
- User tags agent(s) to read a file.
- Tagged agent must have "files" capability.
```

---

## Notes for Next Iteration

- Add clickable prototype (Figma or HTML mock) from these layouts.
- Define component library tokens (spacing, type scale, badges, status chips).
- Add empty/error/loading states for uploads, tool calls, and model failures.
