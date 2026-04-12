Create a context document that captures everything we know about [topic].
Organize by domain.
Use dense, factual prose - no filler.
Target ~50 lines per file. Each file should cover a single focused domain.
If a cdoc exceeds 70 lines or has more than 6 source files after edits, split it. Update manifest.md and any prompts referencing the old filename.
A cdoc should describe the current state of the system only, including all relevant information needed for an agent with no prior context to understand and operate it. It should not include past history, future plans, or speculative changes.
Create it in the ./cdocs folder.
After creating a new cdoc, add a row for it to the routing table in `project_management/prompting.md`.
